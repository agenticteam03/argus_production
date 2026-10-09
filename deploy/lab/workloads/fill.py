"""SC-05 (T-0024): a workload that fills the lab filesystem mounted at /fill until TARGET_PCT, then holds.

It refuses any filesystem larger than MAX_FS_MIB: if the lab mount is missing, /fill is a directory of the root disk
and nothing is written. Its file is /fill/argus-lab-filler.dat (the reset removes it).
"""
import os
import sys
import time


def check_fs(path: str, max_mib: int) -> int:
    st = os.statvfs(path)
    total_mib = st.f_blocks * st.f_frsize // 2**20
    if total_mib > max_mib:
        raise SystemExit(f"filler: refusing: {path} is {total_mib} MiB (> {max_mib}); is the lab mount missing?")
    return total_mib


def used_pct(path: str) -> float:
    st = os.statvfs(path)
    return 100 * (1 - st.f_bavail / st.f_blocks)


def main() -> None:
    target, chunk = float(os.environ.get("TARGET_PCT", "92")), int(os.environ.get("CHUNK_MIB", "2"))
    every, path = float(os.environ.get("EVERY_S", "3")), "/fill"
    total = check_fs(path, int(os.environ.get("MAX_FS_MIB", "512")))
    print(f"filler: {path} is {total} MiB, {used_pct(path):.1f}% used; writing {chunk} MiB every {every:g} s "
          f"up to {target:g}%", flush=True)
    block, written = b"\0" * 2**20, 0
    with open(f"{path}/argus-lab-filler.dat", "ab") as f:
        while used_pct(path) < target:
            for _ in range(chunk):
                f.write(block)
            f.flush()
            os.fsync(f.fileno())
            written += chunk
            if written % 20 == 0:
                print(f"filler: wrote {written} MiB, {used_pct(path):.1f}% used", flush=True)
            time.sleep(every)
    print(f"filler: reached {used_pct(path):.1f}% after {written} MiB; holding", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    sys.exit(main())
