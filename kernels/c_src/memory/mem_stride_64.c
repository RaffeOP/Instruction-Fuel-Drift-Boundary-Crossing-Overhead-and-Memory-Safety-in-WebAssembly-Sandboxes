/* Cache-line stride (64 B) read-modify-write over a 16 MiB array. */
#define LINE_WORDS (1 << 22)

static unsigned int line_buf[LINE_WORDS];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long sum = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < LINE_WORDS; i++) {
            line_buf[i] = (unsigned int)i ^ (unsigned int)r;
        }
        sum = 0;
        for (unsigned int offset = 0; offset < 16; offset++) {
            for (unsigned int i = offset; i < LINE_WORDS; i += 16) {
                line_buf[i] += 3u;
                sum += line_buf[i];
            }
        }
    }
    return (long long)sum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
