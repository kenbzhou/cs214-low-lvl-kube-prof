#!/usr/bin/python3
import time
from bcc import BPF
from datetime import datetime
from profiler_string import profiler_program
from prometheus_client import Gauge
from ctypes import Structure, c_ulonglong, c_ulong

LOG_IN_TERMINAL: bool = True

# Profiler code for EBPF
# measured metrics: page faults, mem allocations, context switches (graceful, forced), filesystem read/write cts and sizes.
class EBPF_Profiler:
   def __init__(self, node_id = "TEST_ID_PLACEHOLDER"):
      # Initialize BPF
      self.profiler = BPF(text=profiler_program)

      # Attach kprobes
      self.profiler.attach_kprobe(event="finish_task_switch.isra.0", fn_name="trace_ctx_switches")
      self.profiler.attach_kprobe(event="handle_mm_fault",           fn_name="trace_page_faults")
      self.profiler.attach_kprobe(event="__kmalloc",                 fn_name="trace_memory_allocation")
      self.profiler.attach_kprobe(event="vfs_read",                  fn_name="trace_fs_read")
      self.profiler.attach_kprobe(event="vfs_write",                 fn_name="trace_fs_write")

      # Globally unique node_id
      self.node_id: str = node_id

      # Initialize Prometheus Metrics
      self.initialize_prom_metrics()
      
      print(f"Starting profiler...")
   
   def initialize_prom_metrics(self):
      self.pm_mem_bytes_allocated   = Gauge("mem_bytes_allocated",   "Memory bytes allocated in interval.",    ["node_id"])
      self.pm_page_faults           = Gauge("page_faults",           "Page faults recorded in interval.",      ["node_id"])
      self.pm_ctx_switches_graceful = Gauge("ctx_switches_graceful", "Graceful context switches in interval.", ["node_id"])
      self.pm_ctx_switches_forced   = Gauge("ctx_switches_forced",   "Forced context switches in interval.",   ["node_id"])
      self.pm_fs_read_count         = Gauge("fs_read_count",         "FS Read calls during interval.",         ["node_id"])
      self.pm_fs_read_size_kb       = Gauge("fs_read_size_kb",       "KB read from FS during interval.",       ["node_id"])
      self.pm_fs_write_count        = Gauge("fs_write_count",        "FS Write calls during interval.",        ["node_id"])
      self.pm_fs_write_size_kb      = Gauge("fs_write_size_kb",      "KB written to FS during interval.",      ["node_id"])

   def run_profiler_loop(self):
      self.print_logging_header()
      # Schema: since there's bleed, we're guaranteed that the second to last entry is completed.
      # Print out that 'earliest entry', then delete it from the table to save space.
      # Let Prometheus handle data storage/consistency.
      while True:
         time.sleep(10)
         timestamped_profile = self.profiler.get_table("timestamped_profile")
         # Sort in ascending order, don't know if still necessary
         sorted_entries = sorted([(key, value) for key, value in timestamped_profile.items()], key=lambda x: datetime.strptime(self.decode_timestamp(x[0]), '%H:%M:%S'))
         earliest, val_earliest = sorted_entries[0]
         metrics = ProfiledMetrics.from_buffer_copy(val_earliest)

         # Update prometheus metrics for scraping.
         self.update_prometheus_metrics(metrics)
         # Print metrics if configured to do so.
         self.print_last_metric_log(earliest, metrics)
         # Remove latest map entry: saves space and also makes printing prettier.
         del timestamped_profile[earliest]
      
   def update_prometheus_metrics(self, metrics):
      self.pm_mem_bytes_allocated  .labels(node_id=self.node_id).set(metrics.mem_bytes_allocated)
      self.pm_page_faults          .labels(node_id=self.node_id).set(metrics.page_faults)
      self.pm_ctx_switches_graceful.labels(node_id=self.node_id).set(metrics.ctx_switches_graceful)
      self.pm_ctx_switches_forced  .labels(node_id=self.node_id).set(metrics.ctx_switches_forced)
      self.pm_fs_read_count        .labels(node_id=self.node_id).set(metrics.fs_read_count)
      self.pm_fs_read_size_kb      .labels(node_id=self.node_id).set(metrics.fs_read_size_kb)
      self.pm_fs_write_count       .labels(node_id=self.node_id).set(metrics.fs_write_count)
      self.pm_fs_write_size_kb     .labels(node_id=self.node_id).set(metrics.fs_write_size_kb)

   
   def decode_timestamp(self, timestamp: c_ulong):
      timestamp_ns = timestamp.value * 10000000000 # 10s
      timestamp_sec = timestamp_ns  // 1000000000   # 10s
      return datetime.utcfromtimestamp(timestamp_sec).strftime('%H:%M:%S')

   def print_logging_header(self):
      if LOG_IN_TERMINAL:
         print("\n" + "=" * 100)
         print(f"Profiling start: {datetime.now().strftime('%H:%M:%S')}")
         print("=" * 100)
         print("%-9s %-10s %-10s %-10s %-10s %-10s %-16s %-10s %-16s" % ("TIMESTAMP", "CTX_SW_G", "CTX_SW_F", "MEM_ALLOC", "PAGE_FTS", "FS_READ_CT", "FS_READ_KB", "FS_WRT_CT", "FS_WRT_KB"))

   def print_last_metric_log(self, timestamp, metrics):
      if LOG_IN_TERMINAL:
         print("%-9s %-10s %-10s %-10s %-10s %-10s %-16s %-10s %-16s" % (self.decode_timestamp(timestamp), metrics.ctx_switches_graceful, metrics.ctx_switches_forced, metrics.mem_bytes_allocated, metrics.page_faults, 
                                                                        metrics.fs_read_count, metrics.fs_read_size_kb, metrics.fs_write_count, metrics.fs_write_size_kb))
   


class ProfiledMetrics(Structure):
   _fields_ = [
      # Memory-related allocations
      ("mem_bytes_allocated",     c_ulonglong),
      ("page_faults",             c_ulonglong),
      # Context-switches/interrupts
      ("ctx_switches_graceful",   c_ulonglong),
      ("ctx_switches_forced",     c_ulonglong),
      # Filesystem I/O
      ("fs_read_count",           c_ulonglong),
      ("fs_read_size_kb",         c_ulonglong),
      ("fs_write_count",          c_ulonglong),
      ("fs_write_size_kb",        c_ulonglong),
    ]

if __name__ == '__main__':
   profiler = EBPF_Profiler(node_id="NODE_01")
   profiler.run_profiler_loop()