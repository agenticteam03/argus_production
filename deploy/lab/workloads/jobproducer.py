"""Push one lab job per second into the shared Redis list."""

import os
import socket
import time
import uuid


def rpush(host, key, value):
    parts = ("RPUSH", key, value)
    request = f"*{len(parts)}\r\n" + "".join(f"${len(part)}\r\n{part}\r\n" for part in parts)
    with socket.create_connection((host, 6379), timeout=3) as sock:
        sock.sendall(request.encode())
        response = sock.makefile("rb").readline()
        if not response.startswith(b":"):
            raise RuntimeError("Redis RPUSH failed")


def main():
    host = os.environ.get("CACHE_HOST", "argus-lab-cache")
    while True:
        rpush(host, "lab:jobs", str(uuid.uuid4()))
        time.sleep(1)


if __name__ == "__main__":
    main()
