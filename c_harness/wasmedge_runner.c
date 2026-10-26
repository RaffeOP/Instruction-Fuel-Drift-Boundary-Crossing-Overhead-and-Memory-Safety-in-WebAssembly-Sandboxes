/* WasmEdge runner: interpreter or AOT (compiled with wasmedgec), instruction-count metering. */
#include <wasmedge/wasmedge.h>

#include "common.h"

static int run_mode_is_aot = 0;

static WasmEdge_VMContext *create_vm(void) {
    WasmEdge_ConfigureContext *conf = WasmEdge_ConfigureCreate();
    WasmEdge_ConfigureSetRunMode(conf, run_mode_is_aot ? WasmEdge_RunMode_AOT : WasmEdge_RunMode_Interpreter);
    WasmEdge_ConfigureAddHostRegistration(conf, WasmEdge_HostRegistration_Wasi);
    WasmEdge_ConfigureStatisticsSetInstructionCounting(conf, true);
    WasmEdge_VMContext *vm = WasmEdge_VMCreate(conf, NULL);
    WasmEdge_ConfigureDelete(conf);
    return vm;
}

static int load_cell(WasmEdge_VMContext *vm, const R3Cell *cell) {
    if (!WasmEdge_ResultOK(WasmEdge_VMLoadWasmFromFile(vm, cell->path))) {
        fprintf(stderr, "load %s failed\n", cell->path);
        return 1;
    }
    if (!WasmEdge_ResultOK(WasmEdge_VMValidate(vm)) || !WasmEdge_ResultOK(WasmEdge_VMInstantiate(vm))) {
        fprintf(stderr, "validate/instantiate %s failed\n", cell->path);
        return 1;
    }
    return 0;
}

/* Runs check() for the checksum, then the warm-up calls of run(reps). */
static int check_and_warm(const R3Cell *cell, const R3Options *options, WasmEdge_VMContext *vm,
                          WasmEdge_String run_name, WasmEdge_Value *reps_param, long long *checksum) {
    WasmEdge_String check_name = WasmEdge_StringCreateByCString("check");
    WasmEdge_Value no_params[1];
    WasmEdge_Value returns[1];
    WasmEdge_Result result = WasmEdge_VMExecute(vm, check_name, no_params, 0, returns, 1);
    WasmEdge_StringDelete(check_name);
    if (!WasmEdge_ResultOK(result)) {
        fprintf(stderr, "check failed for %s\n", cell->key);
        return 1;
    }
    *checksum = WasmEdge_ValueGetI64(returns[0]);
    reps_param[0] = WasmEdge_ValueGenI32((int32_t)cell->reps);
    for (unsigned int w = 0; w < options->warmup; w++) {
        WasmEdge_VMExecute(vm, run_name, reps_param, 1, returns, 1);
    }
    return 0;
}

/* Times the replicates of run(reps) with instruction-count fuel and writes one CSV row each. */
static int time_replicates(const R3Cell *cell, const R3Options *options, WasmEdge_VMContext *vm,
                           WasmEdge_String run_name, WasmEdge_Value *reps_param, long long checksum, FILE *out) {
    WasmEdge_StatisticsContext *stats = WasmEdge_VMGetStatisticsContext(vm);
    WasmEdge_Value returns[1];
    for (unsigned int replicate = 0; replicate < options->replicates; replicate++) {
        r3_wait_for_quiet();
        uint64_t count_before = WasmEdge_StatisticsGetInstrCount(stats);
        uint64_t instr0, cycles0, instr1, cycles1;
        r3_hw_counters(&instr0, &cycles0);
        uint64_t cpu_start = r3_thread_cpu_ns();
        uint64_t wall_start = r3_wall_ns();
        WasmEdge_Result result = WasmEdge_VMExecute(vm, run_name, reps_param, 1, returns, 1);
        uint64_t wall_ns = r3_wall_ns() - wall_start;
        uint64_t cpu_ns = r3_thread_cpu_ns() - cpu_start;
        uint64_t fuel = WasmEdge_StatisticsGetInstrCount(stats) - count_before;
        r3_hw_counters(&instr1, &cycles1);
        if (!WasmEdge_ResultOK(result)) {
            fprintf(stderr, "timed run failed for %s\n", cell->key);
            return 1;
        }
        fprintf(out, "%s,%s,%s,%s,%u,%u,%llu,%llu,%llu,%lld,%llu,%llu\n", options->runtime, cell->opt_level,
                cell->key, cell->group, replicate, cell->reps, (unsigned long long)fuel,
                (unsigned long long)cpu_ns, (unsigned long long)wall_ns, checksum,
                (unsigned long long)(cycles1 - cycles0), (unsigned long long)(instr1 - instr0));
    }
    return 0;
}

static int run_cell(const R3Cell *cell, const R3Options *options, FILE *out) {
    WasmEdge_VMContext *vm = create_vm();
    int status = load_cell(vm, cell);
    if (status == 0) {
        WasmEdge_String run_name = WasmEdge_StringCreateByCString("run");
        WasmEdge_Value reps_param[1];
        long long checksum = 0;
        status = check_and_warm(cell, options, vm, run_name, reps_param, &checksum);
        if (status == 0) {
            status = time_replicates(cell, options, vm, run_name, reps_param, checksum, out);
        }
        WasmEdge_StringDelete(run_name);
    }
    WasmEdge_VMDelete(vm);
    return status;
}

int main(int argc, char **argv) {
    R3Options options = {"wasmedge", NULL, NULL, 10, 2};
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--runtime")) options.runtime = argv[i + 1];
        else if (!strcmp(argv[i], "--plan")) options.plan = argv[i + 1];
        else if (!strcmp(argv[i], "--out")) options.out = argv[i + 1];
        else if (!strcmp(argv[i], "--replicates")) options.replicates = (unsigned int)atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--warmup")) options.warmup = (unsigned int)atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--run-mode")) run_mode_is_aot = !strcmp(argv[i + 1], "aot");
    }
    if (!options.plan || !options.out || !options.runtime) {
        fprintf(stderr, "usage: --runtime L --plan P --out O [--replicates N] [--warmup N] [--run-mode aot|interpreter]\n");
        return 2;
    }
    static R3Cell cells[R3_MAX_CELLS];
    int count = r3_load_plan(options.plan, cells, R3_MAX_CELLS);
    if (count < 0) {
        fprintf(stderr, "cannot read plan %s\n", options.plan);
        return 1;
    }
    FILE *out = fopen(options.out, "w");
    if (!out) {
        return 1;
    }
    fprintf(out, "%s\n", R3_CSV_HEADER);
    for (int i = 0; i < count; i++) {
        if (run_cell(&cells[i], &options, out)) {
            fclose(out);
            return 1;
        }
        fflush(out);
        fprintf(stderr, "done %s %s %s\n", options.runtime, cells[i].opt_level, cells[i].key);
    }
    fclose(out);
    return 0;
}
