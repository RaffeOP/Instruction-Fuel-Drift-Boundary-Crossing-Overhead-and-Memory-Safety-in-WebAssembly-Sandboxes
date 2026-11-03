// Per-thread configurable PMU counters on Apple silicon through the private kperf and
// kperfdata frameworks. Requires root. The event names come from the kpep database for
// the running CPU (/usr/share/kpep/as3.plist on Apple M3).
//
// The framework entry points are not public API. Their signatures follow the reverse-
// engineered declarations that open-source tools (for example ibireme's kpc_demo) use.

#include <dlfcn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define KPC_MAX_COUNTERS 32
#define KC_MAX_EVENTS 10

typedef struct kpep_db kpep_db;
typedef struct kpep_config kpep_config;
typedef struct kpep_event kpep_event;

static int (*kpc_set_counting)(uint32_t);
static int (*kpc_set_thread_counting)(uint32_t);
static int (*kpc_set_config)(uint32_t, uint64_t *);
static int (*kpc_get_thread_counters)(uint32_t, uint32_t, uint64_t *);
static int (*kpc_force_all_ctrs_set)(int);
static int (*kpep_db_create)(const char *, kpep_db **);
static int (*kpep_db_event)(kpep_db *, const char *, kpep_event **);
static int (*kpep_config_create)(kpep_db *, kpep_config **);
static int (*kpep_config_force_counters)(kpep_config *);
static int (*kpep_config_add_event)(kpep_config *, kpep_event **, uint32_t, uint32_t *);
static int (*kpep_config_kpc_classes)(kpep_config *, uint32_t *);
static int (*kpep_config_kpc_count)(kpep_config *, size_t *);
static int (*kpep_config_kpc_map)(kpep_config *, size_t *, size_t);
static int (*kpep_config_kpc)(kpep_config *, uint64_t *, size_t);

static size_t event_slot[KC_MAX_EVENTS];
static size_t event_count;
static uint32_t active_classes;

#define BIND(handle, name)                                         \
  do {                                                             \
    *(void **)&name = dlsym(handle, #name);                        \
    if (!name) {                                                   \
      fprintf(stderr, "kpc: missing symbol %s\n", #name);          \
      return -1;                                                   \
    }                                                              \
  } while (0)

static int bind_frameworks(void) {
  void *kperf = dlopen("/System/Library/PrivateFrameworks/kperf.framework/kperf", RTLD_LAZY);
  void *kperfdata =
      dlopen("/System/Library/PrivateFrameworks/kperfdata.framework/kperfdata", RTLD_LAZY);
  if (!kperf || !kperfdata) {
    fprintf(stderr, "kpc: cannot load kperf frameworks\n");
    return -1;
  }
  BIND(kperf, kpc_set_counting);
  BIND(kperf, kpc_set_thread_counting);
  BIND(kperf, kpc_set_config);
  BIND(kperf, kpc_get_thread_counters);
  BIND(kperf, kpc_force_all_ctrs_set);
  BIND(kperfdata, kpep_db_create);
  BIND(kperfdata, kpep_db_event);
  BIND(kperfdata, kpep_config_create);
  BIND(kperfdata, kpep_config_force_counters);
  BIND(kperfdata, kpep_config_add_event);
  BIND(kperfdata, kpep_config_kpc_classes);
  BIND(kperfdata, kpep_config_kpc_count);
  BIND(kperfdata, kpep_config_kpc_map);
  BIND(kperfdata, kpep_config_kpc);
  return 0;
}

// Configures the named events for the calling thread. Returns 0 on success.
int kc_init(const char *const *names, size_t count) {
  if (count == 0 || count > KC_MAX_EVENTS || bind_frameworks() != 0) {
    return -1;
  }
  kpep_db *db = NULL;
  kpep_config *config = NULL;
  if (kpep_db_create(NULL, &db) || kpep_config_create(db, &config) ||
      kpep_config_force_counters(config)) {
    fprintf(stderr, "kpc: cannot open the kpep database\n");
    return -1;
  }
  for (size_t i = 0; i < count; i++) {
    kpep_event *event = NULL;
    uint32_t error = 0;
    if (kpep_db_event(db, names[i], &event) || !event) {
      fprintf(stderr, "kpc: unknown event %s\n", names[i]);
      return -1;
    }
    if (kpep_config_add_event(config, &event, 0, &error)) {
      fprintf(stderr, "kpc: cannot schedule event %s (error %u)\n", names[i], error);
      return -1;
    }
  }
  uint64_t registers[KPC_MAX_COUNTERS] = {0};
  size_t map[KPC_MAX_COUNTERS] = {0};
  size_t register_count = 0;
  if (kpep_config_kpc_classes(config, &active_classes) ||
      kpep_config_kpc_count(config, &register_count) ||
      kpep_config_kpc_map(config, map, sizeof(map)) ||
      kpep_config_kpc(config, registers, sizeof(registers))) {
    fprintf(stderr, "kpc: cannot build the counter configuration\n");
    return -1;
  }
  if (kpc_force_all_ctrs_set(1)) {
    fprintf(stderr, "kpc: kpc_force_all_ctrs_set failed (run as root)\n");
    return -1;
  }
  if (kpc_set_config(active_classes, registers) || kpc_set_counting(active_classes) ||
      kpc_set_thread_counting(active_classes)) {
    fprintf(stderr, "kpc: cannot start counting (run as root)\n");
    return -1;
  }
  memcpy(event_slot, map, count * sizeof(size_t));
  event_count = count;
  return 0;
}

// Writes the current per-thread value of each configured event into out[0..count).
int kc_read(uint64_t *out) {
  uint64_t raw[KPC_MAX_COUNTERS] = {0};
  if (kpc_get_thread_counters(0, KPC_MAX_COUNTERS, raw)) {
    return -1;
  }
  for (size_t i = 0; i < event_count; i++) {
    out[i] = raw[event_slot[i]];
  }
  return 0;
}

// Stops counting and releases the counters to the system.
void kc_shutdown(void) {
  if (kpc_set_counting) {
    kpc_set_thread_counting(0);
    kpc_set_counting(0);
    kpc_force_all_ctrs_set(0);
  }
}
