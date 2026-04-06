# TezQR

TezQR is a headless Telegram bot micro-SaaS for Indian SMBs. Merchants register a UPI VPA, request payment QR codes through Telegram commands, and move to a paid 1000-QR pack through a concierge upgrade flow.

The codebase now also includes a provider control plane for white-label payment operations. Providers can manage clients, bot instances, templates, payment requests, reminders, exports, and branded QR assets through the HTTP API.

## Core Commands

Legacy TezQR owner and merchant bot:

- `/start`
- `/setupi <vpa_id>`
- `/pay <amount> <desc>`
- `/stats` admin only
- `/upgrade <target_telegram_id>` admin only

Provider bot public/client commands:

- `/start`
- `/item-code <code> [amount]`
- `/pay <amount> <desc>`

Provider bot staff commands after `/login <actor_code> <api_key>`:

- `/whoami`
- `/onboardlink`
- `/dashboard`
- `/clients`
- `/payments <client_code>`
- `/history <payment_reference>`

Operator and above:

- `/charge <client_code> <amount> <description>`
- `/share <payment_reference> [telegram|whatsapp]`
- `/status <payment_reference> <pending|paid|overdue> [notes]`
- `/note <payment_reference> <note>`
- `/remind <payment_reference> <message>`
- `/remindat <payment_reference> <iso_datetime> <message>`
- `/runreminders`

Manager and owner:

- `/memberadd <actor_code> <owner|manager|operator|viewer> <display_name>`

## Local Development

1. Copy `.env.example` to `.env` and fill in secrets.
2. Start dependencies with `docker compose -f docker-compose-local.yml up --build`.
3. Run tests with `uv sync --dev && uv run pytest`.

## Architecture

The project follows a layered structure aimed at readability and incremental scalability:

- Model: domain entities, value objects, enums, and SQLAlchemy persistence models
- View: FastAPI routes plus Pydantic schemas
- Controller: thin HTTP/webhook adapters under `src/tezqr/presentation/controllers`
- Service: application orchestration in `src/tezqr/application`
- Repository: persistence adapters in `src/tezqr/infrastructure/persistence`

Two product surfaces currently coexist:

- the legacy Telegram merchant bot flow
- the provider control plane for white-label Telegram and WhatsApp payment operations

This split keeps historic behavior intact while allowing the provider feature set to scale independently.

## Documentation

Repo documentation now lives under `docs/`:

- `docs/index.md` for the docs hub
- `docs/product-tutorial.md` for the full product walkthrough
- `docs/architecture.md` for the technical architecture guide
- `docs/learning-roadmap.md` for the FastAPI backend learning plan based on this repo
- `docs/deployment.md` for deployment
- `docs/github-actions.md` for CI/CD

## API Docs

FastAPI serves interactive Swagger documentation at `/docs` and ReDoc at `/redoc`.

The Swagger contract includes:

- system endpoints
- the legacy merchant bot webhook
- provider bot webhooks
- provider control-plane APIs for onboarding, payments, reminders, exports, and QR assets

The local stack is webhook-only. Use a tunnel or send webhook payloads directly to `POST /webhooks/telegram/{secret}` for testing.

## Local Production Smoke

1. Copy `.env.local.prod.example` to `.env.local.prod`.
2. Start the production-like stack with `docker compose --env-file .env.local.prod -f docker-compose-prod.yml -f docker-compose-local.prod.yml up -d --build`.
3. Verify the API with `curl http://127.0.0.1:18000/health`.
4. Verify the reverse proxy with `curl http://localhost:18080/health`.

## Production

Use `docker compose -f docker-compose-prod.yml up -d --build` with a real `APP_DOMAIN`. Caddy handles HTTPS termination and proxies to the FastAPI container.

If you prefer Nginx and Certbot on a VPS, use `.env.server.example`, `docker-compose-server.yml`, and the server guide in `docs/deployment.md`.

## Subscription Payment Details

The TezQR owner can configure the premium upgrade payment details through environment variables:

- `SUBSCRIPTION_PAYMENT_UPI_ID` for a custom UPI ID
- `SUBSCRIPTION_PAYMENT_LINK` for a hosted payment link
- `SUBSCRIPTION_PAYMENT_QR` for a public QR image URL or Telegram file ID
- `BOT_PUBLIC_LINK` for the branded share link shown on merchant QR captions

If no custom subscription payment link or QR is provided, TezQR falls back to `ADMIN_UPI_ID` and generates the payment QR automatically for the `Rs 99 / 1000 QR` pack.

## GitHub Actions

CI and CD workflows are included under `.github/workflows`:

- CI runs Ruff, pytest, Docker build, and a local production-style compose smoke test.
- CD builds and publishes the API image to GHCR, then supports an optional SSH-based deploy when production secrets are configured.
