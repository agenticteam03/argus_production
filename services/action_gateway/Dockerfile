# Built for offline validation in Phase 19. No compose service, route, socket or token is deployed by this PR.
FROM python:3.12-alpine
WORKDIR /app
COPY services/__init__.py /app/services/__init__.py
COPY services/action_gateway /app/services/action_gateway
USER 65532:65532
EXPOSE 8705
CMD ["python", "-m", "services.action_gateway.run"]
