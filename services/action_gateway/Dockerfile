# Built for offline validation in Phase 19. No compose service, route, socket or token is deployed by this PR.
FROM python:3.12-alpine
WORKDIR /app
COPY services/__init__.py /app/services/__init__.py
COPY services/action_gateway /app/services/action_gateway
# The proxy creates its Unix socket in /run/argus-v18 and the gateway keeps its journal in /var/lib/argus-v18: both owned
# by the service user, so a new named volume mounted there inherits that owner (found by the real-image test).
RUN mkdir -p /run/argus-v18 /var/lib/argus-v18 && chown 65532:65532 /run/argus-v18 /var/lib/argus-v18     && chmod 0700 /var/lib/argus-v18
USER 65532:65532
EXPOSE 8705
CMD ["python", "-m", "services.action_gateway.run"]
