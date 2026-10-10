#!/bin/sh
set -e

# Apply database migrations once, before any worker starts.
flask --app main db upgrade

# gthread workers: streamed chat replies hold a connection open, so each worker serves several at once.
exec gunicorn main:app \
  --bind "0.0.0.0:${PORT:-5000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --worker-class gthread \
  --threads "${GUNICORN_THREADS:-8}" \
  --timeout 120 \
  --access-logfile -
