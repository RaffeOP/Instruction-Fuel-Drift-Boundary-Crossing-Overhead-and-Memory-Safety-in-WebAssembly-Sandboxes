/* Linear-memory growth to a fixed working set on the first call, then reads over the grown region. */
#define GROW_TARGET_PAGES 256
#define PAGE_WORDS (65536 / 4)

static int grown;

__attribute__((export_name("run")))
long long run(int reps) {
    if (!grown) {
        int before = __builtin_wasm_memory_size(0);
        int needed = GROW_TARGET_PAGES - before;
        if (needed > 0) {
            __builtin_wasm_memory_grow(0, needed);
        }
        grown = 1;
    }
    int pages = __builtin_wasm_memory_size(0);
    unsigned long long sum = 0;
    for (int r = 0; r < reps; r++) {
        sum = 0;
        for (int p = 1; p < pages; p++) {
            unsigned int *page = (unsigned int *)(unsigned long)(p * 65536);
            sum += page[(p + r) % PAGE_WORDS];
        }
    }
    return (long long)sum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
