/* Binary search over a sorted 1M-entry table for 200k probe keys. */
#define SEARCH_N (1 << 20)
#define PROBES 200000

static unsigned int sorted_keys[SEARCH_N];

__attribute__((export_name("run")))
long long run(int reps) {
    long long hits = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < SEARCH_N; i++) {
            sorted_keys[i] = 3u * (unsigned int)i + 1u;
        }
        hits = 0;
        unsigned int state = 0x2468ace0u + (unsigned int)r;
        for (int p = 0; p < PROBES; p++) {
            state = state * 1664525u + 1013904223u;
            unsigned int key = state % (3u * SEARCH_N + 2u);
            int lo = 0;
            int hi = SEARCH_N - 1;
            while (lo <= hi) {
                int mid = lo + (hi - lo) / 2;
                if (sorted_keys[mid] == key) {
                    hits++;
                    break;
                } else if (sorted_keys[mid] < key) {
                    lo = mid + 1;
                } else {
                    hi = mid - 1;
                }
            }
        }
    }
    return hits;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
