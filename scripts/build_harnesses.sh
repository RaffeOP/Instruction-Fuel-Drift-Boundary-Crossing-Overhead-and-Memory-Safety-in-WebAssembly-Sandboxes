#!/usr/bin/env bash
# Builds every timing harness and the WasmEdge AOT modules from a clean checkout.
set -euo pipefail
cd "$(dirname "$0")/.."

PREFIX=/opt/homebrew
CFLAGS=(-O2 -Wall -Wextra)

(cd rust_harness && cargo build --release)
(cd rust_harness/wasi_guest && cargo build --release --target wasm32-wasip1 && cargo build --release --target wasm32-wasip2)
/opt/homebrew/opt/llvm/bin/clang --target=wasm32 -O2 -c kernels/c_src/host_boundary.c -o kernels/build_obj/host_boundary.o
/opt/homebrew/opt/lld/bin/wasm-ld --no-entry --export-dynamic --export-memory --allow-undefined \
  kernels/build_obj/host_boundary.o -o kernels/build_wasm/host_boundary.wasm
clang "${CFLAGS[@]}" -I"$PREFIX/opt/wamr/include" c_harness/wamr_runner.c \
  "$PREFIX/opt/wamr/lib/libiwasm.a" -lm -lpthread -o c_harness/wamr_runner
clang "${CFLAGS[@]}" -I"$PREFIX/include" c_harness/wasmedge_runner.c \
  -L"$PREFIX/lib" -lwasmedge -Wl,-rpath,"$PREFIX/lib" -o c_harness/wasmedge_runner
clang "${CFLAGS[@]}" -I"$PREFIX/include/node" -bundle -undefined dynamic_lookup \
  c_harness/v8_addon/hwcounters.c -o c_harness/v8_addon/hwcounters.node
clang -O2 c_harness/kpc_validate.c c_harness/kpc_counters.c -o c_harness/kpc_validate
/usr/local/bin/python3 src/build_aot.py
echo "harnesses built"
