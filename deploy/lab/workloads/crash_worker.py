"""SC-02: exits at start because its configuration file is missing (non-OOM crash loop)."""
import os, sys, time
path = "/etc/worker/config.yml"
print("worker starting: loading configuration", flush=True)
if not os.path.exists(path):
    print(f"FATAL: config file not found: {path}", file=sys.stderr, flush=True)
    time.sleep(1)
    sys.exit(1)
