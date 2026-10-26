/* Memory fill followed by a wide reduction over a 8 MiB array. */
#define FILL_WORDS (1 << 21)

static unsigned int fill_buf[FILL_WORDS];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long total = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < FILL_WORDS; i++) {
            fill_buf[i] = 0x01010101u * (unsigned int)((i + r) & 0xff);
        }
        unsigned long long sum = 0;
        for (int i = 0; i < FILL_WORDS; i++) {
            sum += fill_buf[i] >> 3;
        }
        total = sum;
    }
    return (long long)total;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
