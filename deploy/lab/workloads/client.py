"""SC-07: calls its backend by name every 5 s and logs each failure (the backend sits on another network)."""
import os, sys, time, urllib.request
URL = os.environ.get("BACKEND_URL", "http://argus-lab-backend:8080/health")
print(f"client calling {URL} every 5s", flush=True)
while True:
    try:
        with urllib.request.urlopen(URL, timeout=3) as r:
            print(f"OK {URL} -> {r.status}", flush=True)
    except Exception as e:
        print(f"ERROR cannot reach {URL}: {getattr(e, 'reason', e)}", file=sys.stderr, flush=True)
    time.sleep(5)
