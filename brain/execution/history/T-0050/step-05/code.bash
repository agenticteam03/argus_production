# STEP T-0050.C5 — Incident integration local verification
# LAPTOP · PowerShell; code-only verification. No VM work.
$pythonPath = Join-Path $env:APPDATA 'uv/python/cpython-3.12-windows-x86_64-none/python.exe'
$env:PYTHONPATH = Join-Path (Get-Location) '.venv/Lib/site-packages'
& $pythonPath -m pytest --basetemp=.pytest-tmp-run -q tests/test_action_preconditions.py tests/test_action_risk.py tests/test_action_cards.py tests/test_action_suggestions.py tests/test_action_incident.py tests/test_evaluation.py tests/test_write_gate_standing.py tests/test_ui_contract.py
& .venv/Scripts/ruff.exe check argus/actions argus/domain/service_card.py argus/adapters/inbound/http.py argus/adapters/outbound/config_adapters.py argus/application/incident_view.py argus/domain/model.py argus/evaluation tests/test_action_cards.py tests/test_action_suggestions.py tests/test_action_incident.py tests/test_evaluation.py
& $pythonPath brain/tools/brain.py lint
git diff --check
