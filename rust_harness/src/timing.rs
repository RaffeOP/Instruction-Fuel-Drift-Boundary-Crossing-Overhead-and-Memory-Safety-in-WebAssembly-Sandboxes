//! Clocks used for every measurement: per-thread CPU time, monotonic wall time, and
//! unprivileged hardware cycles and retired instructions (process-wide, single-threaded run).

use std::time::Instant;

use crate::hwcount;

pub fn thread_cpu_ns() -> u64 {
    let mut spec = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    // SAFETY: clock_gettime writes into the provided timespec; the pointer is valid.
    let status = unsafe { libc::clock_gettime(libc::CLOCK_THREAD_CPUTIME_ID, &mut spec) };
    assert_eq!(status, 0, "clock_gettime(CLOCK_THREAD_CPUTIME_ID) failed");
    spec.tv_sec as u64 * 1_000_000_000 + spec.tv_nsec as u64
}

pub struct Stopwatch {
    wall: Instant,
    cpu_start: u64,
    hw_start: hwcount::Counters,
}

/// One timed interval: CPU ns, wall ns, cycles, retired instructions.
pub struct Measured {
    pub cpu_ns: u64,
    pub wall_ns: u64,
    pub cycles: u64,
    pub instructions: u64,
}

impl Stopwatch {
    pub fn start() -> Self {
        Stopwatch { wall: Instant::now(), cpu_start: thread_cpu_ns(), hw_start: hwcount::read() }
    }

    pub fn stop(self) -> Measured {
        let hw_end = hwcount::read();
        Measured {
            cpu_ns: thread_cpu_ns() - self.cpu_start,
            wall_ns: self.wall.elapsed().as_nanos() as u64,
            cycles: hw_end.cycles - self.hw_start.cycles,
            instructions: hw_end.instructions - self.hw_start.instructions,
        }
    }
}
