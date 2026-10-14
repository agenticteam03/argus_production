# argus-v18-ui (ACR-0011, T-0016 step 4): the read-only UI edge on vm-095. Build context: the repository root.
#   docker build -f deploy/ui/Dockerfile -t argus-v18-ui:1 .
# Stage 1 builds the frontend in REAL mode (no mock code, no runbook in the bundle) and the runbook index; stage 2 is
# Nginx without root (uid 101, ports 8080/8443), the static files, the runbooks (served only after login) and the
# configuration templates. Nothing of Argus's core is in this image, and it holds no Argus secret.
FROM node:24.4.1-alpine3.22 AS build
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY argus/runbooks/ /src/argus/runbooks/
ENV VITE_ARGUS_MOCK=0
RUN npm run build \
 && mkdir -p /out/runbooks \
 && cp /src/argus/runbooks/RB-*.md /out/runbooks/ \
 && node -e 'const fs=require("fs");const f=fs.readdirSync("/out/runbooks").filter(n=>/^RB-\d+.*\.md$/.test(n)).sort();fs.writeFileSync("/out/runbooks/index.json",JSON.stringify(f))'

FROM nginxinc/nginx-unprivileged:1.27.5-alpine3.21
COPY --from=build /src/frontend/dist/ /usr/share/nginx/html/
COPY --from=build /out/runbooks/ /usr/share/nginx/runbooks/
COPY deploy/ui/nginx/ /etc/nginx/argus/
COPY deploy/ui/05-argus-mode.envsh /docker-entrypoint.d/05-argus-mode.envsh
USER root
RUN rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /etc/nginx/templates /var/www/acme \
 && chown -R 101:101 /etc/nginx/templates /etc/nginx/conf.d \
 && chmod 0755 /docker-entrypoint.d/05-argus-mode.envsh
USER 101
EXPOSE 8080 8443
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:8080/healthz >/dev/null || exit 1
