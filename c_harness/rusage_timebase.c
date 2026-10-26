#include <libproc.h>
#include <mach/mach_time.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <stdint.h>
static uint64_t wall_ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec;}
int main(void){
  mach_timebase_info_data_t tb; mach_timebase_info(&tb);
  struct rusage_info_v4 a,b; volatile uint64_t s=0;
  proc_pid_rusage(getpid(),RUSAGE_INFO_V4,(rusage_info_t*)&a);
  uint64_t w0=wall_ns();
  for(uint64_t i=0;i<400000000ULL;i++) s+=i*2654435761u;
  uint64_t w1=wall_ns();
  proc_pid_rusage(getpid(),RUSAGE_INFO_V4,(rusage_info_t*)&b);
  double wall=(double)(w1-w0);
  double ut=(double)(b.ri_user_time-a.ri_user_time);
  double cyc=(double)(b.ri_cycles-a.ri_cycles), ins=(double)(b.ri_instructions-a.ri_instructions);
  printf("timebase %u/%u\n",tb.numer,tb.denom);
  printf("wall_ms=%.1f user_time_as_ns=%.1f ratio=%.3f\n",wall/1e6, ut*tb.numer/tb.denom, (ut*tb.numer/tb.denom)/wall);
  printf("cycles=%.0f instructions=%.0f GHz=%.3f IPC=%.3f sink=%llu\n",cyc,ins,cyc/wall,ins/cyc,(unsigned long long)s);
  return 0;}
