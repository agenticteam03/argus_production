# Two images from one codebase (one role per container, services/target/service.py):
#   target `db`    -> argus-v18-target-db:1, the db_probe only: adds the pinned PostgreSQL driver (requirements-db.txt)
#   default (last) -> argus-v18-target:1, every other role: the standard library only
FROM python:3.12-alpine AS db
COPY requirements-db.txt /app/requirements-db.txt
RUN pip install --no-cache-dir --no-deps --require-hashes -r /app/requirements-db.txt
COPY service.py /app/service.py
EXPOSE 8700
CMD ["python", "-u", "/app/service.py"]

FROM python:3.12-alpine AS base
COPY service.py /app/service.py
EXPOSE 8700
CMD ["python", "-u", "/app/service.py"]
