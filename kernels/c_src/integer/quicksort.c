/* In-place quicksort (Hoare partition) of 200k pseudo-random 32-bit integers. */
#define SORT_N 200000

static unsigned int sort_data[SORT_N];

static void quicksort_range(int lo, int hi) {
    while (lo < hi) {
        unsigned int pivot = sort_data[lo + (hi - lo) / 2];
        int i = lo;
        int j = hi;
        while (i <= j) {
            while (sort_data[i] < pivot) {
                i++;
            }
            while (sort_data[j] > pivot) {
                j--;
            }
            if (i <= j) {
                unsigned int swap = sort_data[i];
                sort_data[i] = sort_data[j];
                sort_data[j] = swap;
                i++;
                j--;
            }
        }
        if (j - lo < hi - i) {
            quicksort_range(lo, j);
            lo = i;
        } else {
            quicksort_range(i, hi);
            hi = j;
        }
    }
}

__attribute__((export_name("run")))
long long run(int reps) {
    long long checksum = 0;
    for (int r = 0; r < reps; r++) {
        unsigned int state = 0x0badc0deu + (unsigned int)r;
        for (int i = 0; i < SORT_N; i++) {
            state = state * 1664525u + 1013904223u;
            sort_data[i] = state;
        }
        quicksort_range(0, SORT_N - 1);
        checksum = 0;
        for (int i = 0; i < SORT_N; i += 997) {
            checksum = checksum * 31 + (long long)sort_data[i];
        }
    }
    return checksum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
