/* Address arithmetic near the 32-bit boundary: wrap-around offsets checked against the live memory size. */

__attribute__((export_name("run")))
long long run(int reps) {
    long long in_bounds = 0;
    for (int r = 0; r < reps; r++) {
        in_bounds = 0;
        unsigned int size = (unsigned int)__builtin_wasm_memory_size(0) * 65536u;
        for (unsigned int k = 0; k < 4096; k++) {
            unsigned int base = 0xfffffff0u - k * 3u;
            unsigned int offset = 0x20u + k;
            unsigned int address = base + offset;
            if (address < size - 4u) {
                in_bounds++;
            }
        }
    }
    return in_bounds;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
