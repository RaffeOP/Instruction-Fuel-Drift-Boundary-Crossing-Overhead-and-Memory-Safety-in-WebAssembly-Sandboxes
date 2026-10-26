//! Guest for the WASI Preview 1 versus Preview 2 write-cost comparison.
//! Usage: wasi_guest <payload_bytes> <writes>. Each write is one stdout write followed by a flush,
//! so every payload reaches the WASI host as its own call (fd_write in Preview 1, the wasi:io
//! blocking-write-and-flush stream call in Preview 2).

use std::io::Write;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let size: usize = args[1].parse().expect("payload bytes");
    let writes: usize = args[2].parse().expect("write count");
    let payload = vec![b'x'; size];
    let mut out = std::io::stdout().lock();
    for _ in 0..writes {
        out.write_all(&payload).expect("write payload");
        out.flush().expect("flush payload");
    }
}
