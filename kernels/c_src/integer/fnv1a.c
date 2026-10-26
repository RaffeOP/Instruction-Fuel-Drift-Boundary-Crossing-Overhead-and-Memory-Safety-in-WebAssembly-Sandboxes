/* 64-bit FNV-1a hash over a 2 MiB pseudo-random byte buffer. */
#define FNV_BYTES (2 << 20)

static unsigned char fnv_buf[FNV_BYTES];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long hash = 0;
    for (int r = 0; r < reps; r++) {
        unsigned int state = 0x2545f491u + (unsigned int)r;
        for (int i = 0; i < FNV_BYTES; i++) {
            state = state * 1103515245u + 12345u;
            fnv_buf[i] = (unsigned char)(state >> 16);
        }
        hash = 1469598103934665603ULL;
        for (int i = 0; i < FNV_BYTES; i++) {
            hash ^= fnv_buf[i];
            hash *= 1099511628211ULL;
        }
    }
    return (long long)hash;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
