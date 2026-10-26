/* SHA-256 over a 256 KiB pseudo-random message. Validated against hashlib in tests. */
#define MSG_BYTES (256 * 1024)

static const unsigned int K[64] = {
    0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u, 0x923f82a4u, 0xab1c5ed5u,
    0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u, 0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u,
    0xe49b69c1u, 0xefbe4786u, 0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
    0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u, 0x06ca6351u, 0x14292967u,
    0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u, 0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u,
    0xa2bfe8a1u, 0xa81a664bu, 0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
    0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au, 0x5b9cca4fu, 0x682e6ff3u,
    0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u, 0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

static unsigned char msg[MSG_BYTES + 128];

static unsigned int rotr(unsigned int x, int n) {
    return (x >> n) | (x << (32 - n));
}

static void compress(unsigned int h[8], const unsigned char *block) {
    unsigned int w[64];
    for (int i = 0; i < 16; i++) {
        w[i] = ((unsigned int)block[4 * i] << 24) | ((unsigned int)block[4 * i + 1] << 16) |
               ((unsigned int)block[4 * i + 2] << 8) | (unsigned int)block[4 * i + 3];
    }
    for (int i = 16; i < 64; i++) {
        unsigned int s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
        unsigned int s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
        w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    unsigned int a = h[0], b = h[1], c = h[2], d = h[3];
    unsigned int e = h[4], f = h[5], g = h[6], hh = h[7];
    for (int i = 0; i < 64; i++) {
        unsigned int s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
        unsigned int ch = (e & f) ^ (~e & g);
        unsigned int t1 = hh + s1 + ch + K[i] + w[i];
        unsigned int s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
        unsigned int maj = (a & b) ^ (a & c) ^ (b & c);
        unsigned int t2 = s0 + maj;
        hh = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d;
    h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

/* Digest of the first message word, exposed for validation against hashlib. */
__attribute__((export_name("digest_word0")))
unsigned int digest_word0(void) {
    unsigned int h[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                         0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    unsigned long long bit_length = (unsigned long long)MSG_BYTES * 8u;
    unsigned int pad = MSG_BYTES;
    msg[pad] = 0x80;
    unsigned int total = MSG_BYTES + 1;
    while (total % 64 != 56) {
        msg[total++] = 0;
    }
    for (int i = 0; i < 8; i++) {
        msg[total++] = (unsigned char)(bit_length >> (56 - 8 * i));
    }
    for (unsigned int off = 0; off < total; off += 64) {
        compress(h, msg + off);
    }
    return h[0];
}

__attribute__((export_name("message_ptr")))
unsigned int message_ptr(void) {
    return (unsigned int)(unsigned long)msg;
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned int word = 0;
    for (int r = 0; r < reps; r++) {
        unsigned int state = 0x13572468u + (unsigned int)r;
        for (int i = 0; i < MSG_BYTES; i++) {
            state = state * 1103515245u + 12345u;
            msg[i] = (unsigned char)(state >> 16);
        }
        word = digest_word0();
    }
    return (long long)word;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
