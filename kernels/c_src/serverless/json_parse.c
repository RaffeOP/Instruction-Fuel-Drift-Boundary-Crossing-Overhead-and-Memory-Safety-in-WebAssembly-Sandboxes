/* JSON request parsing: a generated 64 KiB document of objects with string, integer, float,
 * boolean, and nested-array fields is tokenized and its numbers and string hashes are folded
 * into a checksum, as an HTTP handler would before dispatching on the payload. */
#include "common.h"

#define DOC_CAP (64 * 1024)

static char doc[DOC_CAP + 256];
static int doc_len;

static int put(int pos, const char *s) {
    while (*s) doc[pos++] = *s++;
    return pos;
}

static int put_uint(int pos, unsigned int v) {
    char tmp[12];
    int n = 0;
    do { tmp[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) doc[pos++] = tmp[--n];
    return pos;
}

static void build_document(unsigned int seed) {
    sl_seed(seed);
    int pos = put(0, "[");
    int first = 1;
    while (pos < DOC_CAP - 200) {
        if (!first) doc[pos++] = ',';
        first = 0;
        pos = put(pos, "{\"id\":");
        pos = put_uint(pos, sl_next() % 1000000);
        pos = put(pos, ",\"user\":\"u");
        pos = put_uint(pos, sl_next() % 50000);
        pos = put(pos, "\",\"score\":");
        pos = put_uint(pos, sl_next() % 1000);
        doc[pos++] = '.';
        pos = put_uint(pos, sl_next() % 100);
        pos = put(pos, (sl_next() & 1) ? ",\"active\":true" : ",\"active\":false");
        pos = put(pos, ",\"tags\":[");
        int tags = 1 + (int)(sl_next() % 4);
        for (int t = 0; t < tags; t++) {
            if (t) doc[pos++] = ',';
            pos = put(pos, "\"t");
            pos = put_uint(pos, sl_next() % 97);
            doc[pos++] = '"';
        }
        pos = put(pos, "]}");
    }
    pos = put(pos, "]");
    doc_len = pos;
}

/* Single-pass tokenizer with a value stack depth counter; returns a checksum of all values. */
static unsigned long long parse_document(void) {
    unsigned long long h = 1469598103934665603ULL;
    int depth = 0;
    for (int i = 0; i < doc_len; i++) {
        char c = doc[i];
        if (c == '{' || c == '[') {
            depth++;
        } else if (c == '}' || c == ']') {
            depth--;
        } else if (c == '"') {
            unsigned long long s = 5381;
            for (i++; i < doc_len && doc[i] != '"'; i++) {
                if (doc[i] == '\\') i++;
                s = s * 33 + (unsigned char)doc[i];
            }
            h = sl_mix(h, s);
        } else if ((c >= '0' && c <= '9') || c == '-') {
            long long whole = 0;
            long long frac = 0;
            int neg = c == '-';
            if (neg) i++;
            while (i < doc_len && doc[i] >= '0' && doc[i] <= '9') whole = whole * 10 + (doc[i++] - '0');
            if (i < doc_len && doc[i] == '.') {
                for (i++; i < doc_len && doc[i] >= '0' && doc[i] <= '9'; i++) frac = frac * 10 + (doc[i] - '0');
            }
            i--;
            h = sl_mix(h, (unsigned long long)(neg ? -whole : whole) * 1000ULL + (unsigned long long)frac);
        } else if (c == 't' || c == 'f' || c == 'n') {
            h = sl_mix(h, (unsigned long long)c);
            i += (c == 'f') ? 4 : 3;
        }
    }
    return sl_mix(h, (unsigned long long)depth);
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long h = 0;
    for (int r = 0; r < reps; r++) {
        build_document(0x1234u + (unsigned int)(r & 7));
        h ^= parse_document();
    }
    return (long long)h;
}

__attribute__((export_name("check")))
long long check(void) { return run(1); }
