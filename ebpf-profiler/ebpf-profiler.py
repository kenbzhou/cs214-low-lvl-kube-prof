#!/usr/bin/python3
from bcc import BPF
import time
import os
import sys
from datetime import datetime
from profiler_string import profiler_program
from ctypes import Structure, c_ulonglong, c_int, c_ulong


# Initialize BPF
b = BPF(text=profiler_program)

# Attach kprobes
b.attach_kprobe(event="finish_task_switch.isra.0", fn_name="trace_ctx_switches")
b.attach_kprobe(event="handle_mm_fault", fn_name="trace_page_faults")
b.attach_kprobe(event="__kmalloc", fn_name="trace_memory_allocation")
# b.attach_kprobe(event="kfree", fn_name="trace_memory_deallocation")

print(f"Starting profiler...")

class ProfiledMetrics(Structure):
    _fields_ = [
        ("mem_bytes_allocated", c_ulonglong),
        ("page_faults", c_ulonglong),
        ("ctx_switches_graceful", c_int),
        ("ctx_switches_forced", c_int),
    ]

def decode_timestamp(timestamp: c_ulong):
    timestamp_ns = timestamp.value * 10000000000 # 10s
    timestamp_sec = timestamp_ns // 1000000000   # 10s
    return datetime.utcfromtimestamp(timestamp_sec).strftime('%H:%M:%S')


try:
    while True:
        time.sleep(10)
        print("\n" + "=" * 80)
        print(f"System Profile at {datetime.now().strftime('%H:%M:%S')}")
        print("=" * 80)
        
        # Process CPU metrics
        timestamped_profile = b.get_table("timestamped_profile")
        sorted_entries = sorted([(key, value) for key, value in timestamped_profile.items()], key=lambda x: datetime.strptime(decode_timestamp(x[0]), '%H:%M:%S'))
        
        print("\nContext Switches:")
        print("%-9s %-10s %-10s %-10s %-10s" % ("TIMESTAMP", "CTX_SW_G", "CTX_SW_F", "MEM_ALLOC", "PAGE_FTS"))
        for key, value in sorted_entries:
            metrics = ProfiledMetrics.from_buffer_copy(value)
            print("%-9s %-10s %-10s %-10s %-10s" % (decode_timestamp(key), metrics.ctx_switches_graceful, metrics.ctx_switches_forced, metrics.mem_bytes_allocated, metrics.page_faults))


except:
   print("Some fault occurred")