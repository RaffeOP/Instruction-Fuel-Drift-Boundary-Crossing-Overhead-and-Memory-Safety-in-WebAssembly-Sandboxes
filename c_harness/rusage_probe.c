/* Probe: can an unprivileged process read hardware cycles/instructions via proc_pid_rusage? */
#include <libproc.h>
#include <stdio.h>
#include <unistd.h>
#include <stdint.h>

int main(void) {
    struct rusage_info_v4 before, after;
    volatile uint64_t sink = 0;
    if (proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t *)&before) != 0) {
        perror("before"); return 1;
    }
    for (uint64_t i = 0; i < 200000000ULL; i++) sink += i * 2654435761u;
    if (proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t *)&after) != 0) {
        perror("after"); return 1;
    }
    printf("cycles delta=%llu instructions delta=%llu user_time_delta_ns=%llu sink=%llu\n",
           (unsigned long long)(after.ri_cycles - before.ri_cycles),
           (unsigned long long)(after.ri_instructions - before.ri_instructions),
           (unsigned long long)(after.ri_user_time - before.ri_user_time),
           (unsigned long long)sink);
    printf("absolute ri_cycles=%llu ri_instructions=%llu\n",
           (unsigned long long)after.ri_cycles, (unsigned long long)after.ri_instructions);
    return 0;
}
