#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static unsigned long long pb_state = 1469598103934665603ULL;

static void pb_mix(unsigned long long bits) {
  pb_state ^= bits;
  pb_state *= 1099511628211ULL;
}

static int pb_fprintf(FILE *stream, const char *format, ...) {
  va_list args;
  va_start(args, format);
  for (const char *p = format; *p; p++) {
    if (*p != '%') {
      continue;
    }
    p++;
    while (*p && strchr("-+ #0123456789.l", *p)) {
      p++;
    }
    if (*p == 'd') {
      pb_mix((unsigned long long)(long long)va_arg(args, int));
    } else if (*p == 'f' || *p == 'e' || *p == 'g') {
      double value = va_arg(args, double);
      unsigned long long bits;
      memcpy(&bits, &value, sizeof bits);
      pb_mix(bits);
    } else if (*p == 's') {
      (void)va_arg(args, const char *);
    }
  }
  va_end(args);
  return 0;
}

#define fprintf pb_fprintf
#include "/Users/raffe/Downloads/R3/kernels/polybench/linear-algebra/blas/gemver/gemver.c"

__attribute__((export_name("run")))
long long run(int reps) {
  long long acc = 0;
  for (int r = 0; r < reps; r++) {
    acc += pb_main(0, 0);
  }
  return acc;
}

__attribute__((export_name("check")))
long long check(void) {
  char *argv[] = {"", 0};
  pb_state = 1469598103934665603ULL;
  pb_main(43, argv);
  return (long long)pb_state;
}
