/*
 * Host-call boundary kernel for RQ3.
 * The guest issues `calls` invocations of an imported host function, each
 * receiving a pointer into linear memory and a payload length. The host
 * performs the capability-checked lift (copy plus UTF-8 validation) and the
 * guest returns the number of accepted calls.
 */

#define MAX_PAYLOAD_BYTES (16 * 1024 * 1024)

extern int host_consume(const unsigned char *payload, int length);

static unsigned char payload_buffer[MAX_PAYLOAD_BYTES];

__attribute__((export_name("fill")))
void fill_payload(int length) {
    for (int i = 0; i < length; i++) {
        payload_buffer[i] = (unsigned char)(0x41 + (i % 26));
    }
}

__attribute__((export_name("payload_address")))
int payload_address(void) {
    return (int)(unsigned long)payload_buffer;
}

__attribute__((export_name("run")))
int run_calls(int calls, int length) {
    int accepted = 0;
    for (int i = 0; i < calls; i++) {
        accepted += host_consume(payload_buffer, length);
    }
    return accepted;
}
