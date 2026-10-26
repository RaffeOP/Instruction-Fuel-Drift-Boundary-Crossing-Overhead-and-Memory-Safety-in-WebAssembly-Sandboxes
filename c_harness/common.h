#ifndef R3_COMMON_H
#define R3_COMMON_H

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <libproc.h>
#include <unistd.h>

#define R3_LOAD_GATE 4.0
#define R3_GATE_POLL_SECONDS 5

/* Blocks until the 1-minute load average is at most R3_LOAD_GATE. Called before each timed replicate. */
static inline void r3_wait_for_quiet(void) {
    double load[1];
    while (getloadavg(load, 1) == 1 && load[0] > R3_LOAD_GATE) {
        sleep(R3_GATE_POLL_SECONDS);
    }
}

/* Unprivileged process-wide retired instructions and core cycles (proc_pid_rusage). */
static void r3_hw_counters(uint64_t *instructions, uint64_t *cycles) {
    struct rusage_info_v4 info;
    proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t *)&info);
    *instructions = info.ri_instructions;
    *cycles = info.ri_cycles;
}

#define R3_MAX_CELLS 1024
#define R3_LINE_BYTES 1024
#define R3_CSV_HEADER "runtime,opt_level,kernel,group,replicate,reps,fuel,cpu_ns,wall_ns,checksum,cycles,instructions"

typedef struct {
    char key[96];
    char group[16];
    char opt_level[8];
    char path[512];
    unsigned int reps;
} R3Cell;

typedef struct {
    const char *runtime;
    const char *plan;
    const char *out;
    unsigned int replicates;
    unsigned int warmup;
} R3Options;

static uint64_t r3_thread_cpu_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static uint64_t r3_wall_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

/* Parses the shared timing plan (kernel,group,opt_level,path,reps). Returns cell count or -1. */
static int r3_load_plan(const char *path, R3Cell *cells, int capacity) {
    FILE *file = fopen(path, "r");
    if (!file) {
        return -1;
    }
    char line[R3_LINE_BYTES];
    int count = 0;
    int first = 1;
    while (fgets(line, sizeof line, file)) {
        if (first) {
            first = 0;
            continue;
        }
        if (count >= capacity) {
            fclose(file);
            return -1;
        }
        R3Cell *cell = &cells[count];
        if (sscanf(line, "%95[^,],%15[^,],%7[^,],%511[^,],%u", cell->key, cell->group,
                   cell->opt_level, cell->path, &cell->reps) != 5) {
            fclose(file);
            return -1;
        }
        count++;
    }
    fclose(file);
    return count;
}

#endif
