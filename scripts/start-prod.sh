#!/bin/sh
set -eu

uv run --no-sync alembic upgrade head
uv run --no-sync python -m tezqr.infrastructure.register_webhook

exec uv run --no-sync gunicorn 'tezqr.presentation.app:create_app()' \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  -b 0.0.0.0:8000
