# The Henley enquiry receiver.
#
# Deliberately small: a Python base, three pinned packages, one module and a
# schema. Nothing here needs a compiler, a system library or a package index at
# runtime, and the image holds no credential of any kind — the receiver's whole
# job is to write a row to a file on a bind mount.
FROM python:3.12-slim-bookworm

# Runs as the host's `admin` (uid 1000), not as a fresh container user. The
# SQLite file and its -wal/-shm sidecars live on a bind mount and are read by
# henley-utils running as that same host user; a mismatched uid means the
# nightly job cannot read what the receiver wrote.
RUN groupadd --gid 1000 henley \
 && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin henley

WORKDIR /app

# Dependencies first, so a change to app.py does not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && find /usr/local -name '__pycache__' -type d -prune -exec rm -rf {} +

COPY app.py schema.sql ./

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    INTAKE_DB_PATH=/data/intake.sqlite

# The bind mount lands here. Created and owned up front so the directory exists
# even on a first run against an empty host directory.
RUN mkdir -p /data && chown henley:henley /data
VOLUME ["/data"]

USER henley
EXPOSE 8000

# One worker on purpose. The store is a single SQLite file and the load is a
# handful of enquiries a week; a second worker would add write contention and
# split the in-memory per-IP rate limit in half without buying any throughput.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
