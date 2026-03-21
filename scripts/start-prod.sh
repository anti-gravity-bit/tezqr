#!/bin/sh
set -eu

uv run --no-sync alembic upgrade head

exec uv run --no-sync gunicorn 'tezqr.presentation.app:create_app()' \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  -b 0.0.0.0:8000
