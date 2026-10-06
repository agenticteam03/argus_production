FROM python:3.12-alpine

WORKDIR /app
COPY --chown=65532:65532 app.py /app/app.py

USER 65532:65532
EXPOSE 8080

CMD ["python", "-u", "/app/app.py"]
