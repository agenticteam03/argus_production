#!/bin/sh
# SC-05 (T-0024), vm-166, TESTING ONLY: the lab filesystem the filler fills, never the root disk.
# A 256M ext4 image under /opt/argus-v18/lab/, loop-mounted at /srv/argus-lab-fill (nodev,nosuid,noexec). Idempotent.
# Not persisted (no host config is edited): after a reboot the mount is absent, and node-exporter, the host-probe and
# the filler all see that (unknown / refused), never the root disk under its name. Run it again to restore it.
#   sudo sh ops/lab-fill-mount.sh            create (if needed) and mount
#   sudo sh ops/lab-fill-mount.sh --remove   unmount and delete the image
set -eu
IMG=/opt/argus-v18/lab/fill.img
MNT=/srv/argus-lab-fill
if [ "${1:-}" = "--remove" ]; then
  if mountpoint -q "$MNT"; then umount "$MNT"; fi
  rm -f "$IMG"
  rmdir "$MNT" 2>/dev/null || true
  echo "lab-fill: removed"
  exit 0
fi
install -d -m 0755 /opt/argus-v18/lab "$MNT"
if [ ! -f "$IMG" ]; then
  fallocate -l 256M "$IMG"
  mkfs.ext4 -q -m 0 -L argus-lab-fill "$IMG"
fi
if ! mountpoint -q "$MNT"; then mount -o loop,nodev,nosuid,noexec "$IMG" "$MNT"; fi
df -h "$MNT" | tail -1 | awk '{print "lab-fill: mounted " $6 " size=" $2 " used=" $5}'
