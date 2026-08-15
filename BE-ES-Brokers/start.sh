#!/usr/bin/env bash
# Bootstrap script for Replit: apply migrations, seed demo data, then start the server.
# Safe to run on every restart — alembic and seed are both idempotent.
set -e

cd "$(dirname "$0")"

echo "==> Applying database migrations..."
python -m alembic upgrade head

echo "==> Seeding demo data..."
python src/core/seed.py

echo "==> Starting API server..."
exec uvicorn main:app --app-dir src --host 0.0.0.0 --port 4000 --reload
