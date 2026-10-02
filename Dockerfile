# argus-v18-agent (vm-095): one process = API (8000) + webhook (8001) + worker. Config is mounted read-only at run
# time; the reviewed runbook library ships inside the package (argus/runbooks, D-002).
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
