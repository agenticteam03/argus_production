"""SC-06 (T-0028): a busy loop that wants a whole CPU, run under a small CPU quota, so the container is throttled.

It stops by itself after MAX_S seconds (the scenario stops it earlier). No network, no files: only CPU.
"""
import os
import time


def main() -> int:
    max_s = float(os.environ.get("MAX_S", "1200"))
    print(f"burner: spinning for up to {max_s:g} s", flush=True)
    deadline, n = time.monotonic() + max_s, 0
    while time.monotonic() < deadline:
        n += 1                       # pure CPU work; the quota decides how much of it really runs
    print(f"burner: done after {n} iterations", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
