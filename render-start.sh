#!/usr/bin/env bash
set -euo pipefail

# Render start command for the Scholar Tracker rebuild.
# Configure SECRET_KEY and SCHOLAR_TRACKER_DB in the service environment first.
: "${SECRET_KEY:?Set a stable SECRET_KEY in the Render environment}"
: "${SCHOLAR_TRACKER_DB:?Set SCHOLAR_TRACKER_DB to a verified persistent database path}"

flask --app app init-db
exec gunicorn --bind "0.0.0.0:${PORT:-10000}" app:app
