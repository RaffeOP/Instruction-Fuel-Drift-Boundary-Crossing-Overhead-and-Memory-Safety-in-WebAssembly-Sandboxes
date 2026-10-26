/* WAMR runner (interpreter build shipped with the installed libiwasm). WASI is provided by the runtime. */
#include "wasm_export.h"

#include "common.h"

#define WAMR_STACK_BYTES (1u << 20)
#define WAMR_HEAP_BYTES (1u << 24)
#define WAMR_ERR_BYTES 256

static uint8_t *r3_read_file(const char *path, uint32_t *size_out) {
    FILE *file = fopen(path, "rb");
    if (!file) {
        return NULL;
    }
    fseek(file, 0, SEEK_END);
    long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    uint8_t *buffer = malloc((size_t)size);
    if (buffer && fread(buffer, 1, (size_t)size, file) != (size_t)size) {
        free(buffer);
        buffer = NULL;
    }
    fclose(file);
    *size_out = (uint32_t)size;
    return buffer;
}

static int64_t r3_result_i64(const uint32_t *slots) {
    return (int64_t)(((uint64_t)slots[1] << 32) | (uint64_t)slots[0]);
}

static int instantiate_cell(const R3Cell *cell, wasm_module_t *module, wasm_module_inst_t *instance, uint8_t **bytes) {
    char error[WAMR_ERR_BYTES];
    uint32_t size = 0;
    *bytes = r3_read_file(cell->path, &size);
    if (!*bytes) {
        fprintf(stderr, "read %s failed\n", cell->path);
        return 1;
    }
    *module = wasm_runtime_load(*bytes, size, error, sizeof error);
    if (!*module) {
        fprintf(stderr, "load %s: %s\n", cell->key, error);
        return 1;
    }
    wasm_runtime_set_wasi_args(*module, NULL, 0, NULL, 0, NULL, 0, NULL, 0);
    *instance = wasm_runtime_instantiate(*module, WAMR_STACK_BYTES, WAMR_HEAP_BYTES, error, sizeof error);
    if (!*instance) {
        fprintf(stderr, "instantiate %s: %s\n", cell->key, error);
        return 1;
    }
    return 0;
}

/* Runs check() once for the checksum, then the warm-up calls of run(reps). */
static int check_and_warm(const R3Cell *cell, const R3Options *options, wasm_module_inst_t instance,
                          wasm_exec_env_t env, int64_t *checksum) {
    wasm_function_inst_t run = wasm_runtime_lookup_function(instance, "run");
    wasm_function_inst_t check = wasm_runtime_lookup_function(instance, "check");
    if (!run || !check || !env) {
        fprintf(stderr, "missing exports or exec env for %s\n", cell->key);
        return 1;
    }
    uint32_t slots[4] = {0, 0, 0, 0};
    if (!wasm_runtime_call_wasm(env, check, 0, slots)) {
        fprintf(stderr, "check failed for %s: %s\n", cell->key, wasm_runtime_get_exception(instance));
        return 1;
    }
    *checksum = r3_result_i64(slots);
    for (unsigned int w = 0; w < options->warmup; w++) {
        slots[0] = cell->reps;
        wasm_runtime_call_wasm(env, run, 1, slots);
    }
    return 0;
}

/* Times the replicates of run(reps) and writes one CSV row each. */
static int time_replicates(const R3Cell *cell, const R3Options *options, wasm_module_inst_t instance,
                           wasm_exec_env_t env, int64_t checksum, FILE *out) {
    wasm_function_inst_t run = wasm_runtime_lookup_function(instance, "run");
    uint32_t slots[4] = {0, 0, 0, 0};
    for (unsigned int replicate = 0; replicate < options->replicates; replicate++) {
        slots[0] = cell->reps;
        uint64_t instr0, cycles0, instr1, cycles1;
        r3_hw_counters(&instr0, &cycles0);
        uint64_t cpu_start = r3_thread_cpu_ns();
        uint64_t wall_start = r3_wall_ns();
        bool ok = wasm_runtime_call_wasm(env, run, 1, slots);
        uint64_t wall_ns = r3_wall_ns() - wall_start;
        uint64_t cpu_ns = r3_thread_cpu_ns() - cpu_start;
        r3_hw_counters(&instr1, &cycles1);
        if (!ok) {
            fprintf(stderr, "timed run failed for %s: %s\n", cell->key, wasm_runtime_get_exception(instance));
            return 1;
        }
        fprintf(out, "%s,%s,%s,%s,%u,%u,,%llu,%llu,%lld,%llu,%llu\n", options->runtime, cell->opt_level, cell->key,
                cell->group, replicate, cell->reps, (unsigned long long)cpu_ns,
                (unsigned long long)wall_ns, (long long)checksum,
                (unsigned long long)(cycles1 - cycles0), (unsigned long long)(instr1 - instr0));
    }
    return 0;
}

static int run_cell(const R3Cell *cell, const R3Options *options, FILE *out) {
    wasm_module_t module = NULL;
    wasm_module_inst_t instance = NULL;
    uint8_t *bytes = NULL;
    if (instantiate_cell(cell, &module, &instance, &bytes) != 0) {
        return 1;
    }
    wasm_exec_env_t env = wasm_runtime_create_exec_env(instance, WAMR_STACK_BYTES);
    int64_t checksum = 0;
    int status = check_and_warm(cell, options, instance, env, &checksum);
    if (status == 0) {
        status = time_replicates(cell, options, instance, env, checksum, out);
    }
    if (env) {
        wasm_runtime_destroy_exec_env(env);
    }
    wasm_runtime_deinstantiate(instance);
    wasm_runtime_unload(module);
    free(bytes);
    return status;
}

int main(int argc, char **argv) {
    R3Options options = {"wamr", NULL, NULL, 10, 2};
    for (int i = 1; i + 1 < argc; i += 2) {
        if (!strcmp(argv[i], "--runtime")) options.runtime = argv[i + 1];
        else if (!strcmp(argv[i], "--plan")) options.plan = argv[i + 1];
        else if (!strcmp(argv[i], "--out")) options.out = argv[i + 1];
        else if (!strcmp(argv[i], "--replicates")) options.replicates = (unsigned int)atoi(argv[i + 1]);
        else if (!strcmp(argv[i], "--warmup")) options.warmup = (unsigned int)atoi(argv[i + 1]);
    }
    if (!options.plan || !options.out || !options.runtime) {
        fprintf(stderr, "usage: --runtime L --plan P --out O [--replicates N] [--warmup N]\n");
        return 2;
    }
    if (!wasm_runtime_init()) {
        fprintf(stderr, "wasm_runtime_init failed\n");
        return 1;
    }
    static R3Cell cells[R3_MAX_CELLS];
    int count = r3_load_plan(options.plan, cells, R3_MAX_CELLS);
    if (count <= 0) {
        fprintf(stderr, "cannot read plan %s\n", options.plan);
        return 1;
    }
    FILE *out = fopen(options.out, "w");
    if (!out) {
        return 1;
    }
    fprintf(out, "%s\n", R3_CSV_HEADER);
    int status = 0;
    for (int i = 0; i < count && status == 0; i++) {
        status = run_cell(&cells[i], &options, out);
        fflush(out);
        fprintf(stderr, "done %s %s %s\n", options.runtime, cells[i].opt_level, cells[i].key);
    }
    fclose(out);
    wasm_runtime_destroy();
    return status;
}
