# argus-v18-agent:1 (vm-095): one image for three programs (T-0014): `argus api` (API 8000 + webhook 8001),
# `argus worker` and `argus scheduler`, chosen by the compose `command`. The default CMD `serve` is the single-process
# rollback. Config is mounted read-only at run time; the runbook library ships inside the package (argus/runbooks, D-002).
# T-0021 (§12.6): two users. `argus` runs the agent; `argus-tools` runs the MCP tools process, the only reader of the
# executor tokens. sudo lets argus start exactly the tools-server launcher as argus-tools, without arguments.
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends sudo && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml /app/
COPY argus /app/argus
RUN pip install --no-cache-dir . && useradd -r -u 10010 argus && useradd -r -u 10011 argus-tools \
    && mkdir -p /data && chown argus /data
COPY --chmod=0755 deploy/agent/argus-tools-server /usr/local/bin/argus-tools-server
COPY --chmod=0440 deploy/agent/argus-tools.sudoers /etc/sudoers.d/argus-tools
ENV ARGUS_CONFIG_DIR=/app/config ARGUS_RUNBOOKS_DIR=/app/argus/runbooks ARGUS_DB=/data/argus.db \
    ARGUS_SECRETS_DIR=/run/argus-secrets ARGUS_API=http://127.0.0.1:8000 PYTHONUNBUFFERED=1 \
    ARGUS_TOOLS_COMMAND="sudo -n -u argus-tools /usr/local/bin/argus-tools-server"
USER argus
EXPOSE 8000 8001
CMD ["python", "-m", "argus", "serve"]
