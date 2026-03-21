# TezQR

TezQR is a headless Telegram bot micro-SaaS for Indian SMBs. Merchants register a UPI VPA, request payment QR codes through Telegram commands, and move to premium through a concierge upgrade flow.

## Core Commands

- `/start`
- `/setupi <vpa_id>`
- `/pay <amount> <desc>`
- `/stats` admin only
- `/upgrade <target_telegram_id>` admin only

## Local Development

1. Copy `.env.example` to `.env` and fill in secrets.
2. Start dependencies with `docker compose -f docker-compose-local.yml up --build`.
3. Run tests with `uv sync --dev && uv run pytest`.

The local stack is webhook-only. Use a tunnel or send webhook payloads directly to `POST /webhooks/telegram/{secret}` for testing.

## Local Production Smoke

1. Copy `.env.local.prod.example` to `.env.local.prod`.
2. Start the production-like stack with `docker compose --env-file .env.local.prod -f docker-compose-prod.yml -f docker-compose-local.prod.yml up -d --build`.
3. Verify the API with `curl http://127.0.0.1:18000/health`.
4. Verify the reverse proxy with `curl http://localhost:18080/health`.

## Production

Use `docker compose -f docker-compose-prod.yml up -d --build` with a real `APP_DOMAIN`. Caddy handles HTTPS termination and proxies to the FastAPI container.

## Subscription Payment Details

The TezQR owner can configure the premium upgrade payment details through environment variables:

- `SUBSCRIPTION_PAYMENT_UPI_ID` for a custom UPI ID
- `SUBSCRIPTION_PAYMENT_LINK` for a hosted payment link
- `SUBSCRIPTION_PAYMENT_QR` for a public QR image URL or Telegram file ID

If no custom subscription UPI ID is provided, TezQR falls back to `ADMIN_UPI_ID`.

## GitHub Actions

CI and CD workflows are included under `.github/workflows`:

- CI runs Ruff, pytest, Docker build, and a local production-style compose smoke test.
- CD builds and publishes the API image to GHCR, then supports an optional SSH-based deploy when production secrets are configured.
