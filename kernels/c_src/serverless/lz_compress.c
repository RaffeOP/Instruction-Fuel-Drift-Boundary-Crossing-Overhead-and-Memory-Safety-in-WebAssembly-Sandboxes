/* LZ77 compression with a hash table of previous positions (LZ4-style greedy matching) over
 * 128 KiB of generated log text, followed by decompression and verification. */
#include "common.h"

#define TEXT_BYTES (128 * 1024)
#define HASH_BITS 13
#define MIN_MATCH 4
#define MAX_OFFSET 65535

static unsigned char text[TEXT_BYTES];
static unsigned char packed[TEXT_BYTES + TEXT_BYTES / 2 + 16];
static unsigned char unpacked[TEXT_BYTES];
static int table[1 << HASH_BITS];
static const char *WORDS[16] = {"INFO ", "WARN ", "request ", "user=", "latency_ms=", "status=200 ", "path=/api/v1/",
                                "orders ", "items ", "GET ", "POST ", "id=", "region=ap-south-1 ", "trace=", "\n", "ok "};

static void build_text(unsigned int seed) {
    sl_seed(seed);
    int pos = 0;
    while (pos < TEXT_BYTES) {
        unsigned int r = sl_next();
        const char *w = WORDS[r & 15];
        while (*w && pos < TEXT_BYTES) text[pos++] = (unsigned char)*w++;
        if ((r >> 8) % 3 == 0) {
            for (int d = 0; d < 4 && pos < TEXT_BYTES; d++) text[pos++] = (unsigned char)('0' + (sl_next() % 10));
        }
    }
}

static unsigned int read32(const unsigned char *p) {
    return (unsigned int)p[0] | ((unsigned int)p[1] << 8) | ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

/* Token format: literal length byte, literals, then a 2-byte offset and a match length byte. */
static int compress_text(void) {
    for (int i = 0; i < (1 << HASH_BITS); i++) table[i] = -1;
    int out = 0, anchor = 0, i = 0;
    while (i + MIN_MATCH <= TEXT_BYTES) {
        unsigned int key = (read32(text + i) * 2654435761u) >> (32 - HASH_BITS);
        int candidate = table[key];
        table[key] = i;
        int length = 0;
        if (candidate >= 0 && i - candidate <= MAX_OFFSET) {
            while (i + length < TEXT_BYTES && length < 255 && text[candidate + length] == text[i + length]) length++;
        }
        if (length >= MIN_MATCH && i - anchor < 255) {
            packed[out++] = (unsigned char)(i - anchor);
            for (int k = anchor; k < i; k++) packed[out++] = text[k];
            int offset = i - candidate;
            packed[out++] = (unsigned char)offset;
            packed[out++] = (unsigned char)(offset >> 8);
            packed[out++] = (unsigned char)length;
            i += length;
            anchor = i;
        } else {
            i++;
            if (i - anchor == 255) {
                packed[out++] = 255;
                for (int k = anchor; k < i; k++) packed[out++] = text[k];
                packed[out++] = 0; packed[out++] = 0; packed[out++] = 0;
                anchor = i;
            }
        }
    }
    packed[out++] = (unsigned char)(TEXT_BYTES - anchor);
    for (int k = anchor; k < TEXT_BYTES; k++) packed[out++] = text[k];
    packed[out++] = 0; packed[out++] = 0; packed[out++] = 0;
    return out;
}

static int decompress_text(int size) {
    int in = 0, out = 0;
    while (in < size) {
        int literals = packed[in++];
        for (int k = 0; k < literals; k++) unpacked[out++] = packed[in++];
        int offset = packed[in] | (packed[in + 1] << 8);
        int length = packed[in + 2];
        in += 3;
        for (int k = 0; k < length; k++, out++) unpacked[out] = unpacked[out - offset];
    }
    return out;
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long h = 1469598103934665603ULL;
    for (int r = 0; r < reps; r++) {
        build_text(0xC0FFEEu + (unsigned int)(r & 3));
        int size = compress_text();
        if (decompress_text(size) != TEXT_BYTES) return -1;
        for (int i = 0; i < TEXT_BYTES; i += 257) {
            if (unpacked[i] != text[i]) return -2;
        }
        h = sl_mix(h, (unsigned long long)size);
    }
    return (long long)h;
}

__attribute__((export_name("check")))
long long check(void) { return run(1); }
