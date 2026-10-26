/* Adversarial branch misprediction: each branch direction is an unpredictable LCG bit. */
#define BRANCH_ITERS 3000000

__attribute__((export_name("run")))
long long run(int reps) {
    long long acc = 0;
    for (int r = 0; r < reps; r++) {
        acc = 0;
        unsigned int state = 0x7f4a7c15u + (unsigned int)r;
        for (int i = 0; i < BRANCH_ITERS; i++) {
            state = state * 1664525u + 1013904223u;
            if ((state >> 17) & 1u) {
                acc += (long long)(state & 0xffu);
            } else {
                acc -= (long long)((state >> 8) & 0xffu);
            }
            if ((state >> 23) & 1u) {
                acc ^= (long long)i;
            }
        }
    }
    return acc;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
