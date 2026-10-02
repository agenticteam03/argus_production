"""SC-01: grows memory in steps until its cgroup limit OOM-kills it (restart policy brings it back)."""
import time
chunks = []
print("worker starting: processing batch jobs", flush=True)
while True:
    chunks.append(bytearray(4 * 1024 * 1024))          # +4 MiB, touched
    print(f"worker holding {len(chunks) * 4} MiB of cached results", flush=True)
    time.sleep(0.5)
