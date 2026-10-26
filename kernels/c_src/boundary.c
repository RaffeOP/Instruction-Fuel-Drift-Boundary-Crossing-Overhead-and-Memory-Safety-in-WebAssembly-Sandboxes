/*
 * Linear-memory boundary probes for RQ2.
 * Each export performs exactly one operation so the host can classify the
 * outcome of that operation as a graceful trap, a specification-conformant
 * return, a silent corruption, or a host crash.
 */

__attribute__((export_name("grow")))
int probe_grow(int delta_pages) {
    return __builtin_wasm_memory_grow(0, delta_pages);
}

__attribute__((export_name("size")))
int probe_size(void) {
    return __builtin_wasm_memory_size(0);
}

__attribute__((export_name("store_at")))
int probe_store_at(unsigned int address, int value) {
    volatile int *cell = (volatile int *)address;
    *cell = value;
    return *cell;
}

__attribute__((export_name("load_at")))
int probe_load_at(unsigned int address) {
    volatile int *cell = (volatile int *)address;
    return *cell;
}

