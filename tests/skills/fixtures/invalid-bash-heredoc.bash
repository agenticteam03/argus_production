# --------------------------------------------------------------
# VM.1 [VM vm-095 · bash] READ-ONLY deployment marker (ssh argus-vm095)
# Expected: deployment marker; VERDICT: VM.1 PASS.
if grep -qx 'holder=__SESSION_HOLDER__' /opt/argus-v18/SESSION; then
  cat <<'TEXT'
fixture
TEXT
  printf '%s\n' 'VERDICT: VM.1 PASS'
else
  printf '%s\n' 'VERDICT: VM.1 STOP: NOT YOUR SESSION'
fi
