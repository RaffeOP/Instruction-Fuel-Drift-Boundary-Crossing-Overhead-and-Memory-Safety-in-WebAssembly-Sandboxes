/* Adversarial integer division and remainder with data-dependent divisors. */
#define DIVREM_ITERS 400000

__attribute__((export_name("run")))
long long run(int reps) {
    long long acc = 0;
    for (int r = 0; r < reps; r++) {
        acc = 0;
        unsigned int state = 0x9e3779b9u + (unsigned int)r;
        for (int i = 0; i < DIVREM_ITERS; i++) {
            state = state * 1664525u + 1013904223u;
            unsigned int divisor = (state & 0xffu) | 1u;
            acc += (long long)(state / divisor) + (long long)(state % divisor);
        }
    }
    return acc;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
