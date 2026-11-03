// Validates the kperf counters against microbenchmarks with known expected counts.
// Build: clang -O2 kpc_validate.c kpc_counters.c -o kpc_validate ; run with sudo.
// Output: one CSV row per test with the expected and measured count.

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int kc_init(const char *const *names, size_t count);
int kc_read(uint64_t *out);
void kc_shutdown(void);

enum { EV_CYCLES, EV_INSTR, EV_L1D_MISS, EV_MISPRED, EV_COUNT };
static const char *const EVENTS[EV_COUNT] = {
    "FIXED_CYCLES", "FIXED_INSTRUCTIONS", "L1D_CACHE_MISS_LD_NONSPEC", "BRANCH_MISPRED_NONSPEC"};

#define LOOP_ITERATIONS 100000000ULL
#define BRANCH_COUNT 20000000ULL
#define CHASE_LOADS 20000000ULL
#define LINE_BYTES 128
#define LARGE_SET_BYTES (256ULL << 20)
#define SMALL_SET_BYTES (16ULL << 10)

static uint64_t rng_state = 0x9E3779B97F4A7C15ULL;
static uint64_t next_random(void) {
  rng_state ^= rng_state << 13;
  rng_state ^= rng_state >> 7;
  rng_state ^= rng_state << 17;
  return rng_state;
}

static void measure(uint64_t *delta, void (*body)(void *), void *arg) {
  uint64_t start[EV_COUNT], end[EV_COUNT];
  kc_read(start);
  body(arg);
  kc_read(end);
  for (int i = 0; i < EV_COUNT; i++) delta[i] = end[i] - start[i];
}

// Exactly four instructions per iteration: add, add, subs, b.ne.
static void fixed_loop(void *arg) {
  uint64_t n = *(uint64_t *)arg, a = 0, b = 0;
  __asm__ volatile("1:\n add %0, %0, #1\n add %1, %1, #3\n subs %2, %2, #1\n b.ne 1b\n"
                   : "+r"(a), "+r"(b), "+r"(n)
                   :
                   : "cc");
}

typedef struct {
  const uint8_t *bits;
  uint64_t count;
} branch_args;

// One conditional branch per element, taken when the byte is non-zero.
static void branch_loop(void *arg) {
  branch_args *b = arg;
  uint64_t taken = 0;
  for (uint64_t i = 0; i < b->count; i++) {
    uint64_t v = b->bits[i];
    __asm__ volatile("cbz %1, 2f\n add %0, %0, #1\n2:\n" : "+r"(taken) : "r"(v) : "cc");
  }
  __asm__ volatile("" ::"r"(taken));
}

typedef struct {
  void **start;
  uint64_t loads;
} chase_args;

static void chase_loop(void *arg) {
  chase_args *c = arg;
  void **p = c->start;
  for (uint64_t i = 0; i < c->loads; i++) p = (void **)*p;
  __asm__ volatile("" ::"r"(p));
}

// Links one pointer per cache line into a single random cycle.
static void **build_chase(size_t bytes) {
  size_t lines = bytes / LINE_BYTES;
  char *buffer = aligned_alloc(LINE_BYTES, bytes);
  size_t *order = malloc(lines * sizeof(size_t));
  for (size_t i = 0; i < lines; i++) order[i] = i;
  for (size_t i = lines - 1; i > 0; i--) {
    size_t j = next_random() % (i + 1), t = order[i];
    order[i] = order[j];
    order[j] = t;
  }
  for (size_t i = 0; i < lines; i++) {
    void **slot = (void **)(buffer + order[i] * LINE_BYTES);
    *slot = buffer + order[(i + 1) % lines] * LINE_BYTES;
  }
  void **start = (void **)(buffer + order[0] * LINE_BYTES);
  free(order);
  return start;
}

static void report(const char *test, const char *event, double expected, uint64_t measured) {
  printf("%s,%s,%.0f,%llu,%.4f\n", test, event, expected, (unsigned long long)measured,
         expected > 0 ? measured / expected : 0.0);
}

int main(void) {
  if (kc_init(EVENTS, EV_COUNT) != 0) return 1;
  uint64_t d[EV_COUNT];
  printf("test,event,expected,measured,ratio\n");

  uint64_t n = LOOP_ITERATIONS;
  measure(d, fixed_loop, &n);
  report("fixed_loop_4_per_iter", "FIXED_INSTRUCTIONS", 4.0 * n, d[EV_INSTR]);
  report("fixed_loop_4_per_iter", "BRANCH_MISPRED_NONSPEC", 1, d[EV_MISPRED]);

  uint8_t *bits = malloc(BRANCH_COUNT);
  branch_args b = {bits, BRANCH_COUNT};
  for (uint64_t i = 0; i < BRANCH_COUNT; i++) bits[i] = 0;
  measure(d, branch_loop, &b);
  report("branch_constant", "BRANCH_MISPRED_NONSPEC", 0, d[EV_MISPRED]);
  for (uint64_t i = 0; i < BRANCH_COUNT; i++) bits[i] = next_random() & 1;
  measure(d, branch_loop, &b);
  report("branch_random_half", "BRANCH_MISPRED_NONSPEC", BRANCH_COUNT / 2.0, d[EV_MISPRED]);

  chase_args small = {build_chase(SMALL_SET_BYTES), CHASE_LOADS};
  chase_loop(&small);
  measure(d, chase_loop, &small);
  report("chase_16KiB_resident", "L1D_CACHE_MISS_LD_NONSPEC", 0, d[EV_L1D_MISS]);
  chase_args large = {build_chase(LARGE_SET_BYTES), CHASE_LOADS};
  measure(d, chase_loop, &large);
  report("chase_256MiB_random", "L1D_CACHE_MISS_LD_NONSPEC", (double)CHASE_LOADS, d[EV_L1D_MISS]);
  report("chase_256MiB_random", "cycles_per_load", 0, d[EV_CYCLES] / CHASE_LOADS);

  kc_shutdown();
  return 0;
}
