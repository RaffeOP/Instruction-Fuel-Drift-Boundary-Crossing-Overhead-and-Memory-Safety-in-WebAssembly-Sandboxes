/* Shared helpers for the serverless-style kernels: a deterministic generator and a hash. */
#ifndef SERVERLESS_COMMON_H
#define SERVERLESS_COMMON_H

static unsigned int sl_rng_state;

static void sl_seed(unsigned int seed) { sl_rng_state = seed * 2654435761u + 1u; }

static unsigned int sl_next(void) {
    sl_rng_state ^= sl_rng_state << 13;
    sl_rng_state ^= sl_rng_state >> 17;
    sl_rng_state ^= sl_rng_state << 5;
    return sl_rng_state;
}

static unsigned long long sl_mix(unsigned long long h, unsigned long long v) {
    h ^= v;
    return h * 1099511628211ULL;
}

#endif
