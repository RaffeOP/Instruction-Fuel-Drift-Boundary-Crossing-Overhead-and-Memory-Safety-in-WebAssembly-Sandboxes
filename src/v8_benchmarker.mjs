#!/usr/bin/env node
/**
 * V8 (Node.js) timing harness over the shared timing plan.
 * V8 exposes no instruction-fuel meter, so the fuel column is left blank. Hardware cycles and
 * retired instructions come from the proc_pid_rusage addon in c_harness/v8_addon.
 * Imports (WASI calls on paths the timed run never reaches) are satisfied by no-op stubs.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { loadavg } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const hardware = require("../c_harness/v8_addon/hwcounters.node");

const PROJECT_ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const PLAN_PATH = join(PROJECT_ROOT, "data", "timing_plan.csv");
const OUT_PATH = join(PROJECT_ROOT, "data", "rq1_v8.csv");
const RUNTIME = "v8";
const REPLICATES = Number(process.env.R3_REPLICATES ?? 100);
const WARMUP_CALLS = 2;
const RANDOM_SEED = 20261022;
const CSV_HEADER = "runtime,opt_level,kernel,group,replicate,reps,fuel,cpu_ns,wall_ns,checksum,cycles,instructions";

function seededRandom(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0x100000000;
  };
}

function loadPlan() {
  const lines = readFileSync(PLAN_PATH, "utf8").trim().split("\n").slice(1);
  return lines.map((line) => {
    const [kernel, group, optLevel, path, reps] = line.split(",");
    return { kernel, group, optLevel, path, reps: Number(reps) };
  });
}

function stubImports(module) {
  const imports = {};
  for (const entry of WebAssembly.Module.imports(module)) {
    if (entry.kind !== "function") {
      throw new Error(`unsupported import kind ${entry.kind} for ${entry.module}.${entry.name}`);
    }
    imports[entry.module] ??= {};
    imports[entry.module][entry.name] = () => 0;
  }
  return imports;
}

function instantiate(path) {
  const module = new WebAssembly.Module(readFileSync(path));
  return new WebAssembly.Instance(module, stubImports(module)).exports;
}

const LOAD_GATE = 4;
const GATE_POLL_MS = 5000;
const gateSleeper = new Int32Array(new SharedArrayBuffer(4));

/** Blocks until the 1-minute load average is at most LOAD_GATE, polling every five seconds. */
function waitForQuiet() {
  while (loadavg()[0] > LOAD_GATE) {
    Atomics.wait(gateSleeper, 0, 0, GATE_POLL_MS);
  }
}

function timedCall(fn, reps) {
  const hwStart = hardware.read();
  const cpuStart = process.cpuUsage();
  const wallStart = process.hrtime.bigint();
  const value = fn(reps);
  const wallNs = Number(process.hrtime.bigint() - wallStart);
  const cpu = process.cpuUsage(cpuStart);
  const hwEnd = hardware.read();
  return {
    cpuNs: (cpu.user + cpu.system) * 1000,
    wallNs,
    value,
    cycles: hwEnd.cycles - hwStart.cycles,
    instructions: hwEnd.instructions - hwStart.instructions,
  };
}

function buildCells(plan) {
  const cells = [];
  for (let replicate = 0; replicate < REPLICATES; replicate++) {
    const repCells = plan.flatMap((cell) => [{ ...cell, replicate }]);
    const rng = seededRandom(RANDOM_SEED + replicate);
    for (let i = repCells.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [repCells[i], repCells[j]] = [repCells[j], repCells[i]];
    }
    cells.push(...repCells);
  }
  return cells;
}

function main() {
  const plan = loadPlan();
  const cells = buildCells(plan);
  const lines = [CSV_HEADER];
  const instances = new Map();
  const checksums = new Map();
  for (const cell of cells) {
    if (!instances.has(cell.path)) {
      const exports = instantiate(cell.path);
      instances.set(cell.path, exports);
      checksums.set(cell.path, String(exports.check()));
    }
    const exports = instances.get(cell.path);
    if (cell.replicate === 0) {
      for (let i = 0; i < WARMUP_CALLS; i++) timedCall(exports.run, cell.reps);
    }
    waitForQuiet();
    const result = timedCall(exports.run, cell.reps);
    lines.push(`${RUNTIME},${cell.optLevel},${cell.kernel},${cell.group},${cell.replicate},${cell.reps},,${result.cpuNs},${result.wallNs},${checksums.get(cell.path)},${result.cycles},${result.instructions}`);
  }
  writeFileSync(OUT_PATH, lines.join("\n") + "\n");
  console.log(`v8 rows: ${lines.length - 1}`);
}

main();
