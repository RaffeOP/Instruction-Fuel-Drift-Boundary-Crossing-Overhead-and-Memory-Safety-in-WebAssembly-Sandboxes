/* Pseudo-random indexed read-modify-write over a 4 MiB table (cache-hostile). */
#define THRASH_WORDS (1 << 20)

static unsigned int thrash_buf[THRASH_WORDS];

__attribute__((export_name("run")))
long long run(int reps) {
    long long acc = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < THRASH_WORDS; i++) {
            thrash_buf[i] = (unsigned int)i * 2654435761u;
        }
        acc = 0;
        unsigned int idx = (unsigned int)r;
        for (int i = 0; i < THRASH_WORDS; i++) {
            idx = (idx * 1103515245u + 12345u) & (THRASH_WORDS - 1);
            acc += thrash_buf[idx];
            thrash_buf[idx] ^= (unsigned int)acc;
        }
    }
    return acc;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
