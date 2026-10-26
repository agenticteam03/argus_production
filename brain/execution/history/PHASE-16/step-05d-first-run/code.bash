# =====================================================================================
# PHASE-16 step 5d — the audit digest's first checked run on vm-095 (2026-10-26, run by conantkd's agent over ssh,
# both leases, session 13d7ed009aaa). A record of what ran: the sink's namespace and bucket are omitted (they live only
# in vm-095's hosts.env), so O.1 is not runnable as written.
# MUTATES: hosts.env (one line; a .bak-before-digest-sink copy beside it), the scheduler container (recreated, no build),
#   five objects in the OCI bucket (create-only), five chained audit rows. ROLLBACK: hosts.env from its copy and the
#   scheduler recreated; the objects stay (the bucket's retention).
# =====================================================================================

# --- O.1 [VM vm-095 · bash] the sink in hosts.env; the scheduler recreated (no build) --------------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  H=/opt/argus-v18/hosts.env
  [ -f $H.bak-before-digest-sink ] || sudo cp -p $H $H.bak-before-digest-sink
  # KV='ARGUS_AUDIT_DIGEST_SINK=oci:' + the namespace + '/' + the bucket (omitted here)
  if sudo grep -q '^ARGUS_AUDIT_DIGEST_SINK=' $H; then sudo sed -i "s|^ARGUS_AUDIT_DIGEST_SINK=.*|$KV|" $H; else echo "$KV" | sudo tee -a $H >/dev/null; fi
  echo "sink lines in hosts.env: $(sudo grep -c '^ARGUS_AUDIT_DIGEST_SINK=oci:' $H)"
  cd /opt/argus-v18/app/deploy/vm-095
  sudo docker compose --env-file /opt/argus-v18/hosts.env -f compose.core.yml up -d --no-deps argus-v18-scheduler </dev/null 2>&1 | grep -E "Recreated|Started|rror"
  cd ~
  sleep 8
  echo "scheduler: $(sudo docker inspect -f '{{.State.Status}} restarts={{.RestartCount}}' argus-v18-scheduler </dev/null)"
  echo "sink set in scheduler: $(sudo docker exec argus-v18-scheduler sh -c 'case "$ARGUS_AUDIT_DIGEST_SINK" in oci:*/*) echo yes;; *) echo no;; esac' </dev/null)"
  sudo docker logs --since 1m argus-v18-scheduler 2>&1 </dev/null | grep -E "audit digest|rror" | tail -3
  echo "VERDICT: O.1 DONE"
else
  echo "VERDICT: O.1 STOP: NOT YOUR SESSION"
fi

# --- O.2 [VM vm-095 · bash] the digest key's public half (not secret) to /opt/argus-v18/audit-digest-public.pem ---------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo docker exec -i argus-v18-scheduler python - <<'PY' | sudo tee /opt/argus-v18/audit-digest-public.pem >/dev/null
from cryptography.hazmat.primitives import serialization
from argus.infrastructure.wiring import Settings, ed25519_signing_key
k = ed25519_signing_key(Settings().secret("audit_digest_ed25519_key"), name="audit_digest_ed25519_key")
print(k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(), end="")
PY
  echo "public key lines: $(sudo grep -c . /opt/argus-v18/audit-digest-public.pem) ($(sudo head -1 /opt/argus-v18/audit-digest-public.pem))"
  sudo cat /opt/argus-v18/audit-digest-public.pem
  echo "VERDICT: O.2 DONE"
fi

# --- O.3 [VM vm-095 · bash] one manual run of AuditDigestJob.run_once() in the scheduler -------------------------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo docker exec -i argus-v18-scheduler python - <<'PY'
from argus.infrastructure.wiring import Settings, make_store, ed25519_signing_key, make_digest_sink
from argus.infrastructure.audit_digest import AuditDigestJob
s = Settings()
store = make_store(s)
job = AuditDigestJob(store, ed25519_signing_key(s.secret("audit_digest_ed25519_key"), name="audit_digest_ed25519_key"),
                     make_digest_sink(s))
print("run_once:", job.run_once())
rows = store._q("""SELECT body->>'event', body->'detail' FROM audit WHERE body->>'event' LIKE 'security.audit_digest%%'
                   ORDER BY seq DESC NULLS LAST, at DESC LIMIT 12""")
for e, d in rows:
    d = d or {}
    print("  ", e, {k: d.get(k) for k in ("day", "object", "name", "rows", "reason", "status") if k in d})
PY
  echo "VERDICT: O.3 DONE"
fi

# --- O.4 [VM vm-095 · bash, read-only] each stored object's SHA-256 (HEAD) against the chain's signed digest ------
if grep -q '^holder=conantkd ' /opt/argus-v18/SESSION; then
  sudo docker exec -i argus-v18-scheduler python - <<'PY'
import hashlib
from datetime import date
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from argus.infrastructure.wiring import Settings, make_store, ed25519_signing_key, make_digest_sink
from argus.domain import audit_digest as d
s = Settings(); store = make_store(s); sink = make_digest_sink(s)
key = ed25519_signing_key(s.secret("audit_digest_ed25519_key"), name="audit_digest_ed25519_key")
rows = store.audit_chain()
items, ok = [], 0
for day in [date(2026, 10, n) for n in range(21, 26)]:
    signed = d.sign(d.build_digest(rows, day), key)
    data = d.to_bytes(signed)
    head = sink.client.head_object(sink.namespace, sink.bucket, d.object_name(day))
    stored = head.headers.get("opc-meta-sha256")
    same = stored == hashlib.sha256(data).hexdigest()
    verifies = d.verify_signed(signed, key.public_key())
    chain = d.check_against_chain(signed, rows)
    ok += same and verifies and not chain
    items.append(signed)
    print(day, "stored sha matches the chain's digest:", same, "| signature verifies:", verifies,
          "| chain problems:", len(chain), "| size", head.headers.get("content-length"))
series = d.check_series(items, rows, key.public_key())
print("series problems:", len(series), series[:3])
print(f"VERIFIED {ok}/5")
PY
fi
