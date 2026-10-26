//! Unprivileged hardware counters on macOS: retired instructions and core cycles from
//! proc_pid_rusage(RUSAGE_INFO_V4). Layout copied from the macOS SDK sys/resource.h.
//! Counts are process-wide; the timed run is single-threaded.

use std::os::raw::{c_int, c_void};

const RUSAGE_INFO_V4: c_int = 4;

#[repr(C)]
#[derive(Default)]
pub struct RusageInfoV4 {
    ri_uuid: [u8; 16],
    ri_user_time: u64,
    ri_system_time: u64,
    ri_pkg_idle_wkups: u64,
    ri_interrupt_wkups: u64,
    ri_pageins: u64,
    ri_wired_size: u64,
    ri_resident_size: u64,
    ri_phys_footprint: u64,
    ri_proc_start_abstime: u64,
    ri_proc_exit_abstime: u64,
    ri_child_user_time: u64,
    ri_child_system_time: u64,
    ri_child_pkg_idle_wkups: u64,
    ri_child_interrupt_wkups: u64,
    ri_child_pageins: u64,
    ri_child_elapsed_abstime: u64,
    ri_diskio_bytesread: u64,
    ri_diskio_byteswritten: u64,
    ri_cpu_time_qos_default: u64,
    ri_cpu_time_qos_maintenance: u64,
    ri_cpu_time_qos_background: u64,
    ri_cpu_time_qos_utility: u64,
    ri_cpu_time_qos_legacy: u64,
    ri_cpu_time_qos_user_initiated: u64,
    ri_cpu_time_qos_user_interactive: u64,
    ri_billed_system_time: u64,
    ri_serviced_system_time: u64,
    ri_logical_writes: u64,
    ri_lifetime_max_phys_footprint: u64,
    ri_instructions: u64,
    ri_cycles: u64,
    ri_billed_energy: u64,
    ri_serviced_energy: u64,
    ri_interval_max_phys_footprint: u64,
    ri_runnable_time: u64,
}

extern "C" {
    fn proc_pid_rusage(pid: c_int, flavor: c_int, buffer: *mut c_void) -> c_int;
    fn getpid() -> c_int;
}

/// Snapshot of this process's retired instructions and core cycles.
#[derive(Clone, Copy)]
pub struct Counters {
    pub instructions: u64,
    pub cycles: u64,
}

pub fn read() -> Counters {
    let mut info = RusageInfoV4::default();
    // SAFETY: the buffer matches the kernel's rusage_info_v4 layout for flavor 4.
    let status = unsafe { proc_pid_rusage(getpid(), RUSAGE_INFO_V4, &mut info as *mut RusageInfoV4 as *mut c_void) };
    assert_eq!(status, 0, "proc_pid_rusage failed");
    Counters { instructions: info.ri_instructions, cycles: info.ri_cycles }
}
