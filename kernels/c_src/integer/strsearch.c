/* Naive substring search for a fixed pattern over a 1 MiB text with planted matches. */
#define TEXT_BYTES (1 << 20)
#define PATTERN_LEN 5

static const char pattern[PATTERN_LEN + 1] = "abcab";
static char text[TEXT_BYTES];

__attribute__((export_name("run")))
long long run(int reps) {
    long long matches = 0;
    for (int r = 0; r < reps; r++) {
        unsigned int state = 0x5eed1234u + (unsigned int)r;
        for (int i = 0; i < TEXT_BYTES; i++) {
            state = state * 1664525u + 1013904223u;
            text[i] = (char)('a' + ((state >> 24) % 4u));
        }
        matches = 0;
        for (int i = 0; i + PATTERN_LEN <= TEXT_BYTES; i++) {
            int k = 0;
            while (k < PATTERN_LEN && text[i + k] == pattern[k]) {
                k++;
            }
            if (k == PATTERN_LEN) {
                matches++;
            }
        }
    }
    return matches;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
