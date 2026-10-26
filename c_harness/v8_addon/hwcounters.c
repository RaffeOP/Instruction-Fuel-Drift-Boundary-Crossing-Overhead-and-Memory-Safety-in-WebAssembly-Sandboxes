/* N-API addon: unprivileged retired instructions and core cycles for this Node process. */
#include <node/node_api.h>
#include <libproc.h>
#include <unistd.h>
#include <stdint.h>

static napi_value read_counters(napi_env env, napi_callback_info info) {
    struct rusage_info_v4 ri;
    proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t *)&ri);
    napi_value out;
    napi_create_object(env, &out);
    napi_value cycles, instructions;
    napi_create_bigint_uint64(env, ri.ri_cycles, &cycles);
    napi_create_bigint_uint64(env, ri.ri_instructions, &instructions);
    napi_set_named_property(env, out, "cycles", cycles);
    napi_set_named_property(env, out, "instructions", instructions);
    return out;
}

static napi_value init(napi_env env, napi_value exports) {
    napi_value fn;
    napi_create_function(env, "read", NAPI_AUTO_LENGTH, read_counters, NULL, &fn);
    napi_set_named_property(env, exports, "read", fn);
    return exports;
}

NAPI_MODULE(NODE_GYP_MODULE_NAME, init)
