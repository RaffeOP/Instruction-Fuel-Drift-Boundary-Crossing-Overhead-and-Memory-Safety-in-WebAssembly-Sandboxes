/* Strided read-modify-write at a 4 KiB stride over a 16 MiB array (TLB-hostile). */
#define STRIDE_WORDS (1 << 22)
#define STRIDE_BYTES_STEP 4096

static unsigned int stride_buf[STRIDE_WORDS];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long sum = 0;
    unsigned int per_page = STRIDE_BYTES_STEP / sizeof(unsigned int);
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < STRIDE_WORDS; i++) {
            stride_buf[i] = (unsigned int)i + (unsigned int)r;
        }
        sum = 0;
        for (unsigned int offset = 0; offset < per_page; offset++) {
            for (unsigned int i = offset; i < STRIDE_WORDS; i += per_page) {
                stride_buf[i] += 1u;
                sum += stride_buf[i];
            }
        }
    }
    return (long long)sum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
