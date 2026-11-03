/* Base64 encode and decode of a 192 KiB binary payload, as an API gateway does for binary
 * request and response bodies. The decode is verified against the original bytes. */
#include "common.h"

#define RAW_BYTES (192 * 1024)
#define ENC_BYTES (RAW_BYTES / 3 * 4)

static unsigned char raw[RAW_BYTES];
static char encoded[ENC_BYTES];
static unsigned char decoded[RAW_BYTES];
static const char ALPHABET[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
static signed char reverse[256];

static void init_tables(void) {
    for (int i = 0; i < 256; i++) reverse[i] = -1;
    for (int i = 0; i < 64; i++) reverse[(unsigned char)ALPHABET[i]] = (signed char)i;
}

static void encode(void) {
    for (int i = 0, o = 0; i < RAW_BYTES; i += 3, o += 4) {
        unsigned int v = ((unsigned int)raw[i] << 16) | ((unsigned int)raw[i + 1] << 8) | raw[i + 2];
        encoded[o] = ALPHABET[(v >> 18) & 63];
        encoded[o + 1] = ALPHABET[(v >> 12) & 63];
        encoded[o + 2] = ALPHABET[(v >> 6) & 63];
        encoded[o + 3] = ALPHABET[v & 63];
    }
}

static int decode(void) {
    for (int i = 0, o = 0; i < ENC_BYTES; i += 4, o += 3) {
        int a = reverse[(unsigned char)encoded[i]], b = reverse[(unsigned char)encoded[i + 1]];
        int c = reverse[(unsigned char)encoded[i + 2]], d = reverse[(unsigned char)encoded[i + 3]];
        if ((a | b | c | d) < 0) return -1;
        unsigned int v = ((unsigned int)a << 18) | ((unsigned int)b << 12) | ((unsigned int)c << 6) | (unsigned int)d;
        decoded[o] = (unsigned char)(v >> 16);
        decoded[o + 1] = (unsigned char)(v >> 8);
        decoded[o + 2] = (unsigned char)v;
    }
    return 0;
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long h = 1469598103934665603ULL;
    init_tables();
    for (int r = 0; r < reps; r++) {
        sl_seed(0x51u + (unsigned int)r);
        for (int i = 0; i < RAW_BYTES; i++) raw[i] = (unsigned char)sl_next();
        encode();
        if (decode() != 0) return -1;
        for (int i = 0; i < RAW_BYTES; i += 61) {
            if (decoded[i] != raw[i]) return -2;
            h = sl_mix(h, (unsigned long long)(unsigned char)encoded[i]);
        }
    }
    return (long long)h;
}

__attribute__((export_name("check")))
long long check(void) { return run(1); }
