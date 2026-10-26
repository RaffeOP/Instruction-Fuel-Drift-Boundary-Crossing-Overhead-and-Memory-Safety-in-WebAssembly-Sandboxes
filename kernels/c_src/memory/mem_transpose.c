/* In-place-style transpose of a 1024 x 1024 int matrix through a second buffer. */
#define T_DIM 1024

static int t_src[T_DIM * T_DIM];
static int t_dst[T_DIM * T_DIM];

__attribute__((export_name("run")))
long long run(int reps) {
    long long checksum = 0;
    for (int r = 0; r < reps; r++) {
        for (int i = 0; i < T_DIM; i++) {
            for (int j = 0; j < T_DIM; j++) {
                t_src[i * T_DIM + j] = i * 31 + j * 7 + r;
            }
        }
        for (int i = 0; i < T_DIM; i++) {
            for (int j = 0; j < T_DIM; j++) {
                t_dst[j * T_DIM + i] = t_src[i * T_DIM + j];
            }
        }
        checksum = 0;
        for (int k = 0; k < T_DIM * T_DIM; k += 17) {
            checksum = checksum * 7 + t_dst[k];
        }
    }
    return checksum;
}

__attribute__((export_name("check")))
long long check(void) {
    return run(1);
}
