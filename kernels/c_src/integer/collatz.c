/* Branch-dominated Collatz step counting up to a fixed limit. */
#define COLLATZ_LIMIT 200000

__attribute__((export_name("run")))
long long run(int reps) {
    long long longest = 0;
    for (int r = 0; r < reps; r++) {
        longest = 0;
        for (long long n = 1 + r; n < COLLATZ_LIMIT; n++) {
            long long x = n;
            long long steps = 0;
            while (x != 1) {
                if ((x & 1) == 0) {
                    x = x >> 1;
                } else {
                    x = 3 * x + 1;
                }
                steps++;
            }
            if (steps > longest) {
                longest = steps;
            }
        }
    }
    return longest;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
