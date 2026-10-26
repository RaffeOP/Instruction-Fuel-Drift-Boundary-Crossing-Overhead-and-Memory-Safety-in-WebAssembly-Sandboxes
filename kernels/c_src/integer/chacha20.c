/* ChaCha20 keystream over a 1 MiB buffer. Block function validated against RFC 7539 Section 2.3.2. */
#define STREAM_BYTES (1 << 20)

static unsigned int chacha_state[16];
static unsigned char stream_buf[STREAM_BYTES];

static unsigned int rotl(unsigned int x, int n) {
    return (x << n) | (x >> (32 - n));
}

static void quarter_round(unsigned int *s, int a, int b, int c, int d) {
    s[a] += s[b]; s[d] ^= s[a]; s[d] = rotl(s[d], 16);
    s[c] += s[d]; s[b] ^= s[c]; s[b] = rotl(s[b], 12);
    s[a] += s[b]; s[d] ^= s[a]; s[d] = rotl(s[d], 8);
    s[c] += s[d]; s[b] ^= s[c]; s[b] = rotl(s[b], 7);
}

static void chacha_block(const unsigned int *input, unsigned int *output) {
    unsigned int x[16];
    for (int i = 0; i < 16; i++) {
        x[i] = input[i];
    }
    for (int round = 0; round < 10; round++) {
        quarter_round(x, 0, 4, 8, 12);
        quarter_round(x, 1, 5, 9, 13);
        quarter_round(x, 2, 6, 10, 14);
        quarter_round(x, 3, 7, 11, 15);
        quarter_round(x, 0, 5, 10, 15);
        quarter_round(x, 1, 6, 11, 12);
        quarter_round(x, 2, 7, 8, 13);
        quarter_round(x, 3, 4, 9, 14);
    }
    for (int i = 0; i < 16; i++) {
        output[i] = x[i] + input[i];
    }
}

/* Writes the first keystream block for RFC 7539 test key and nonce; returns word 0. */
__attribute__((export_name("rfc7539_word0")))
unsigned int rfc7539_word0(void) {
    static const unsigned int constants[4] = {0x61707865u, 0x3320646eu, 0x79622d32u, 0x6b206574u};
    unsigned int input[16];
    unsigned int output[16];
    for (int i = 0; i < 4; i++) {
        input[i] = constants[i];
    }
    for (int i = 0; i < 8; i++) {
        unsigned int word = 0;
        for (int b = 0; b < 4; b++) {
            word |= (unsigned int)(4 * i + b) << (8 * b);
        }
        input[4 + i] = word;
    }
    input[12] = 1u;
    input[13] = 0x09000000u;
    input[14] = 0x4a000000u;
    input[15] = 0x00000000u;
    chacha_block(input, output);
    return output[0];
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long checksum = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < 16; i++) {
            chacha_state[i] = 0x9e3779b9u * (unsigned int)(i + 1) + (unsigned int)r;
        }
        chacha_state[12] = 0;
        unsigned int block[16];
        for (int off = 0; off < STREAM_BYTES; off += 64) {
            chacha_block(chacha_state, block);
            for (int w = 0; w < 16; w++) {
                stream_buf[off + 4 * w] = (unsigned char)block[w];
                stream_buf[off + 4 * w + 1] = (unsigned char)(block[w] >> 8);
                stream_buf[off + 4 * w + 2] = (unsigned char)(block[w] >> 16);
                stream_buf[off + 4 * w + 3] = (unsigned char)(block[w] >> 24);
            }
            chacha_state[12]++;
        }
        checksum = 0;
        for (int i = 0; i < STREAM_BYTES; i += 61) {
            checksum = checksum * 131u + stream_buf[i];
        }
    }
    return (long long)checksum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
