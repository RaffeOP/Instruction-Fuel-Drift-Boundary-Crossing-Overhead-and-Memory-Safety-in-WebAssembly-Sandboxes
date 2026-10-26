/* Open-addressing hash table: 262144 inserts and 262144 lookups with linear probing. */
#define HT_SLOTS (1 << 19)
#define HT_OPS (1 << 18)

static unsigned int ht_keys[HT_SLOTS];
static unsigned int ht_vals[HT_SLOTS];

static unsigned int ht_hash(unsigned int key) {
    key ^= key >> 16;
    key *= 0x7feb352du;
    key ^= key >> 15;
    key *= 0x846ca68bu;
    key ^= key >> 16;
    return key & (HT_SLOTS - 1);
}

__attribute__((export_name("run")))
long long run(int reps) {
    long long found = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < HT_SLOTS; i++) {
            ht_keys[i] = 0;
            ht_vals[i] = 0;
        }
        unsigned int state = 0x0f0f1234u + (unsigned int)r;
        for (int op = 0; op < HT_OPS; op++) {
            state = state * 1664525u + 1013904223u;
            unsigned int key = state | 1u;
            unsigned int slot = ht_hash(key);
            while (ht_keys[slot] != 0 && ht_keys[slot] != key) {
                slot = (slot + 1) & (HT_SLOTS - 1);
            }
            ht_keys[slot] = key;
            ht_vals[slot] = (unsigned int)op;
        }
        found = 0;
        state = 0x0f0f1234u + (unsigned int)r;
        for (int op = 0; op < HT_OPS; op++) {
            state = state * 1664525u + 1013904223u;
            unsigned int key = state | 1u;
            unsigned int slot = ht_hash(key);
            while (ht_keys[slot] != 0) {
                if (ht_keys[slot] == key) {
                    found += ht_vals[slot] & 1u;
                    break;
                }
                slot = (slot + 1) & (HT_SLOTS - 1);
            }
        }
    }
    return found;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
