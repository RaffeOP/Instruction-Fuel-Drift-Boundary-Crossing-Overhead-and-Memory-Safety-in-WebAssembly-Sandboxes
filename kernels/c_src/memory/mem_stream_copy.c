/* Sequential copy of a 4 MiB buffer through three alternating arrays. */
#define STREAM_WORDS (1 << 20)

static unsigned int stream_a[STREAM_WORDS];
static unsigned int stream_b[STREAM_WORDS];
static unsigned int stream_c[STREAM_WORDS];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long sum = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < STREAM_WORDS; i++) {
            stream_a[i] = (unsigned int)i * 2654435761u + (unsigned int)r;
        }
        for (int i = 0; i < STREAM_WORDS; i++) {
            stream_b[i] = stream_a[i];
        }
        for (int i = 0; i < STREAM_WORDS; i++) {
            stream_c[i] = stream_b[i] ^ 0x5a5a5a5au;
        }
        sum = 0;
        for (int i = 0; i < STREAM_WORDS; i += 1024) {
            sum += stream_c[i];
        }
    }
    return (long long)sum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
