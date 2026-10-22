# ---------------------------------------------------------------------------------------------------------
# CB.1 [VM vm-095 · bash] Read the deployment marker and Argus container status (ssh argus-vm095)
# READ-ONLY. Replace the VM tag/alias together if targeting vm-166; use the current lease holder.
# Expected: deployed commit, Argus container names/status; VERDICT: CB.1 PASS.
# ---------------------------------------------------------------------------------------------------------
if grep -Fxq 'holder=__SESSION_HOLDER__' /opt/argus-v18/SESSION; then
  if cat /opt/argus-v18/DEPLOYED && sudo docker ps --filter 'name=argus-v18-' --format '{{.Names}} {{.Status}}'; then
    printf '%s\n' 'VERDICT: CB.1 PASS'
  else
    printf '%s\n' 'VERDICT: CB.1 STOP: read failed'
  fi
else
  printf '%s\n' 'VERDICT: CB.1 STOP: NOT YOUR SESSION'
fi
