/* Pointer chasing through a 1M-entry single-cycle permutation (latency-bound loads). */
#define CHASE_N (1 << 20)

static unsigned int next_index[CHASE_N];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long sum = 0;
    for (int r = 0; r < reps; r++) {
        /* Affine map i -> i + step (mod N) with odd step is one cycle covering all N entries. */
        unsigned int step = 611953u + (unsigned int)r * 2u;
        step |= 1u;
        for (unsigned int i = 0; i < CHASE_N; i++) {
            next_index[i] = (i + step) & (CHASE_N - 1);
        }
        unsigned int cursor = 0;
        sum = 0;
        for (int hop = 0; hop < CHASE_N; hop++) {
            cursor = next_index[cursor];
            sum += cursor;
        }
    }
    return (long long)sum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
