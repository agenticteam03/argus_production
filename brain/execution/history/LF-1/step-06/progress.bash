#!/usr/bin/env bash
# READ-ONLY: sanitized logs of the synthetic Langfuse containers only.
sudo -n python3 - <<'PY'
import json, re, subprocess
from pathlib import Path
p=Path('/opt/argus-v18/lab/lf-1-dc432c3ff537/trial.env')
values=[s.partition('=')[2] for s in p.read_text().splitlines() if '=' in s] if p.exists() else []
for service in ('web','worker'):
 r=subprocess.run(['docker','logs','--tail','18','argus-lab-lf1-'+service],capture_output=True)
 t=(r.stdout+r.stderr).decode(errors='replace')
 for v in values:
  t=t.replace(v,'[redacted]')
 t=re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b','[address]',t)
 print(json.dumps({'service':service,'log_tail':t.splitlines()[-12:]},indent=2))
PY