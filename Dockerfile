# argus-v18-agent:1 (vm-095): one image for three programs (T-0014): `argus api` (API 8000 + webhook 8001),
# `argus worker` and `argus scheduler`, chosen by the compose `command`. The default CMD `serve` is the single-process
# rollback. Config is mounted read-only at run time; the runbook library ships inside the package (argus/runbooks, D-002).
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
COPY argus /app/argus
RUN pip install --no-cache-dir . && useradd -r -u 10010 argus && mkdir -p /data && chown argus /data
ENV ARGUS_CONFIG_DIR=/app/config ARGUS_RUNBOOKS_DIR=/app/argus/runbooks ARGUS_DB=/data/argus.db \
    ARGUS_SECRETS_DIR=/run/argus-secrets ARGUS_API=http://127.0.0.1:8000 PYTHONUNBUFFERED=1
USER argus
EXPOSE 8000 8001
CMD ["python", "-m", "argus", "serve"]
