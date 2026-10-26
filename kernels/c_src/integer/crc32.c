/* Bytewise CRC-32 over a 1 MiB buffer, bit-serial inner loop. */
#define CRC_BYTES (1 << 20)

static unsigned char crc_buf[CRC_BYTES];

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned int result = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < CRC_BYTES; i++) {
            crc_buf[i] = (unsigned char)((i * 131 + 7) & 0xff);
        }
        unsigned int crc = 0xffffffffu;
        for (int i = 0; i < CRC_BYTES; i++) {
            crc ^= crc_buf[i];
            for (int b = 0; b < 8; b++) {
                unsigned int mask = 0u - (crc & 1u);
                crc = (crc >> 1) ^ (0xedb88320u & mask);
            }
        }
        result = ~crc;
    }
    return (long long)result;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
