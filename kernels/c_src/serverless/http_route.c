/* HTTP request routing: request lines with paths and query strings are parsed and matched
 * against a 64-route table with path parameters, as a function-as-a-service front end does. */
#include "common.h"

#define ROUTES 64
#define REQUESTS 4096
#define LINE_CAP 128

static char routes[ROUTES][48];
static char lines[REQUESTS][LINE_CAP];
static const char *METHODS[4] = {"GET", "POST", "PUT", "DELETE"};
static const char *SEGMENTS[8] = {"users", "orders", "items", "carts", "auth", "files", "events", "search"};

static int append(char *dst, int pos, const char *s) {
    while (*s) dst[pos++] = *s++;
    return pos;
}

static int append_uint(char *dst, int pos, unsigned int v) {
    char tmp[12];
    int n = 0;
    do { tmp[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) dst[pos++] = tmp[--n];
    return pos;
}

static void build_tables(void) {
    sl_seed(0xBEEFu);
    for (int r = 0; r < ROUTES; r++) {
        int pos = append(routes[r], 0, "/");
        pos = append(routes[r], pos, SEGMENTS[r % 8]);
        if (r & 8) pos = append(routes[r], pos, "/:id");
        if (r & 16) { pos = append(routes[r], pos, "/"); pos = append(routes[r], pos, SEGMENTS[(r / 8) % 8]); }
        if (r & 32) pos = append(routes[r], pos, "/:sub");
        routes[r][pos] = 0;
    }
    for (int q = 0; q < REQUESTS; q++) {
        int r = (int)(sl_next() % ROUTES);
        int pos = append(lines[q], 0, METHODS[sl_next() % 4]);
        lines[q][pos++] = ' ';
        for (const char *p = routes[r]; *p; p++) {
            if (*p == ':') {
                pos = append_uint(lines[q], pos, sl_next() % 100000);
                while (p[1] && p[1] != '/') p++;
            } else {
                lines[q][pos++] = *p;
            }
        }
        pos = append(lines[q], pos, "?page=");
        pos = append_uint(lines[q], pos, sl_next() % 50);
        pos = append(lines[q], pos, " HTTP/1.1");
        lines[q][pos] = 0;
    }
}

/* Matches a path (up to '?' or ' ') against a route pattern; ':' segments match one segment. */
static int matches(const char *path, const char *pattern, unsigned int *param_hash) {
    unsigned int h = 0;
    while (*pattern) {
        if (*pattern == ':') {
            while (*pattern && *pattern != '/') pattern++;
            if (!*path || *path == '/' || *path == '?' || *path == ' ') return 0;
            while (*path && *path != '/' && *path != '?' && *path != ' ') h = h * 31u + (unsigned char)*path++;
        } else {
            if (*pattern != *path) return 0;
            pattern++;
            path++;
        }
    }
    *param_hash = h;
    return *path == '?' || *path == ' ' || *path == 0;
}

__attribute__((export_name("run")))
long long run(int reps) {
    unsigned long long h = 1469598103934665603ULL;
    build_tables();
    for (int r = 0; r < reps; r++) {
        for (int q = 0; q < REQUESTS; q++) {
            const char *line = lines[q];
            int method = 0;
            while (*line != ' ') method = method * 7 + *line++;
            line++;
            int hit = -1;
            unsigned int params = 0;
            for (int k = 0; k < ROUTES && hit < 0; k++) {
                if (matches(line, routes[k], &params)) hit = k;
            }
            const char *query = line;
            while (*query && *query != '?') query++;
            unsigned int page = 0;
            if (*query == '?') {
                while (*query && *query != '=') query++;
                for (query++; *query >= '0' && *query <= '9'; query++) page = page * 10 + (unsigned int)(*query - '0');
            }
            h = sl_mix(h, ((unsigned long long)(unsigned int)hit << 40) ^ ((unsigned long long)params << 8) ^ page ^ (unsigned long long)method);
        }
    }
    return (long long)h;
}

__attribute__((export_name("check")))
long long check(void) { return run(1); }
