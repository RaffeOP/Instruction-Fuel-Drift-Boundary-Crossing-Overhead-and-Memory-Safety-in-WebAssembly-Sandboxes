/*
 * Sandbox lifecycle kernel for RQ4.
 * Each instantiated sandbox grows its linear memory by the requested number of
 * pages and writes one byte per page, so every recycled sandbox leaves a known
 * amount of private dirty memory behind for the host to reclaim.
 */

#define WASM_PAGE_BYTES 65536

__attribute__((export_name("dirty")))
int dirty_pages(int pages) {
    int previous = __builtin_wasm_memory_grow(0, pages);
    if (previous < 0) {
        return -1;
    }
    unsigned char *base = (unsigned char *)((unsigned long)previous * WASM_PAGE_BYTES);
    for (int page = 0; page < pages; page++) {
        base[page * WASM_PAGE_BYTES] = (unsigned char)(page + 1);
    }
    return previous;
}
