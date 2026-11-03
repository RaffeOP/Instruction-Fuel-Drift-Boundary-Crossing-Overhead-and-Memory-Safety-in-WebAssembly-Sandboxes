//! Compiles the kperf counter shim (c_harness/kpc_counters.c) into a static library.

use std::env;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let source = PathBuf::from("../c_harness/kpc_counters.c");
    let out_dir = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR"));
    let object = out_dir.join("kpc_counters.o");
    let archive = out_dir.join("libkpc_counters.a");
    let status = Command::new("clang")
        .args(["-O2", "-c", "-fPIC", "-Wall", "-Wextra"])
        .arg(&source)
        .arg("-o")
        .arg(&object)
        .status()
        .expect("run clang");
    assert!(status.success(), "clang failed on {}", source.display());
    let status = Command::new("ar").arg("crs").arg(&archive).arg(&object).status().expect("run ar");
    assert!(status.success(), "ar failed");
    println!("cargo:rustc-link-search=native={}", out_dir.display());
    println!("cargo:rustc-link-lib=static=kpc_counters");
    println!("cargo:rerun-if-changed={}", source.display());
}
