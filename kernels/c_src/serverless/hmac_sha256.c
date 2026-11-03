/* HMAC-SHA256 verification of 2048 JWT-sized tokens (header.payload of 120 to 260 bytes) under
 * a 32-byte key, as an authentication middleware does on every request. The implementation is
 * checked against RFC 4231 test case 2 through the rfc4231_case2_word0 export. */
#include "common.h"

#define TOKENS 2048
#define TOKEN_CAP 320

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

typedef struct {
    unsigned int h[8];
    unsigned char block[64];
    unsigned int fill;
    unsigned long long length;
} Sha256;

static void sha_init(Sha256 *s) {
    static const unsigned int IV[8] = {0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
                                       0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u};
    for (int i = 0; i < 8; i++) s->h[i] = IV[i];
    s->fill = 0;
    s->length = 0;
}

static void sha_update(Sha256 *s, const unsigned char *data, unsigned int n) {
    for (unsigned int i = 0; i < n; i++) {
        s->block[s->fill++] = data[i];
        if (s->fill == 64) { compress(s->h, s->block); s->fill = 0; }
    }
    s->length += n;
}

static void sha_final(Sha256 *s, unsigned char out[32]) {
    unsigned long long bits = s->length * 8u;
    unsigned char pad = 0x80;
    sha_update(s, &pad, 1);
    unsigned char zero = 0;
    while (s->fill != 56) sha_update(s, &zero, 1);
    for (int i = 0; i < 8; i++) { unsigned char b = (unsigned char)(bits >> (56 - 8 * i)); sha_update(s, &b, 1); }
    for (int i = 0; i < 8; i++) {
        out[4 * i] = (unsigned char)(s->h[i] >> 24); out[4 * i + 1] = (unsigned char)(s->h[i] >> 16);
        out[4 * i + 2] = (unsigned char)(s->h[i] >> 8); out[4 * i + 3] = (unsigned char)s->h[i];
    }
}

static void hmac_sha256(const unsigned char *key, unsigned int key_len, const unsigned char *msg, unsigned int n,
                        unsigned char out[32]) {
    unsigned char pad[64];
    unsigned char inner[32];
    Sha256 s;
    for (int i = 0; i < 64; i++) pad[i] = (unsigned char)(((unsigned int)i < key_len ? key[i] : 0) ^ 0x36);
    sha_init(&s); sha_update(&s, pad, 64); sha_update(&s, msg, n); sha_final(&s, inner);
    for (int i = 0; i < 64; i++) pad[i] ^= 0x36 ^ 0x5c;
    sha_init(&s); sha_update(&s, pad, 64); sha_update(&s, inner, 32); sha_final(&s, out);
}

static unsigned char tokens[TOKENS][TOKEN_CAP];
static unsigned int token_len[TOKENS];
static unsigned char key[32];

static void build_tokens(void) {
    sl_seed(0xA11CEu);
    for (int i = 0; i < 32; i++) key[i] = (unsigned char)sl_next();
    for (int t = 0; t < TOKENS; t++) {
        token_len[t] = 120 + sl_next() % 141;
        for (unsigned int i = 0; i < token_len[t]; i++) tokens[t][i] = (unsigned char)('A' + sl_next() % 58);
    }
}

/* First 32-bit word of HMAC-SHA256("Jefe", "what do ya want for nothing?"); RFC 4231 gives 0x5bdcc146. */
__attribute__((export_name("rfc4231_case2_word0")))
unsigned int rfc4231_case2_word0(void) {
    static const unsigned char k[] = "Jefe";
    static const unsigned char m[] = "what do ya want for nothing?";
    unsigned char out[32];
    hmac_sha256(k, 4, m, 28, out);
    return ((unsigned int)out[0] << 24) | ((unsigned int)out[1] << 16) | ((unsigned int)out[2] << 8) | out[3];
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long h = 1469598103934665603ULL;
    build_tokens();
    unsigned char mac[32];
    for (int r = 0; r < reps; r++) {
        for (int t = 0; t < TOKENS; t++) {
            hmac_sha256(key, 32, tokens[t], token_len[t], mac);
            h = sl_mix(h, ((unsigned long long)mac[0] << 24) | ((unsigned long long)mac[1] << 16) | mac[31]);
        }
    }
    return (long long)h;
}

__attribute__((export_name("check")))
long long check(void) { return run(1); }
