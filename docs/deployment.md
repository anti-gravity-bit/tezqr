# TezQR Deployment Guide

## Server runtime model

For a typical Linux VPS with Nginx in front, run only:

- `api`
- `db`

Do not start the `caddy` service if you plan to terminate TLS with Nginx and Certbot.

Use:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose-prod.yml \
  -f docker-compose-server.yml \
  up -d --build api db
```

This keeps:

- FastAPI on `127.0.0.1:8000`
- PostgreSQL on `127.0.0.1:5432`

## Required environment configuration

Copy `.env.server.example` to `.env.server` and set:

- `POSTGRES_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `ADMIN_TELEGRAM_ID`
- `ADMIN_UPI_ID`
- `TELEGRAM_WEBHOOK_SECRET`
- `APP_DOMAIN` after your domain is ready

Optional owner payment settings:

- `SUBSCRIPTION_PAYMENT_UPI_ID`
- `SUBSCRIPTION_PAYMENT_LINK`
- `SUBSCRIPTION_PAYMENT_QR`

If `SUBSCRIPTION_PAYMENT_UPI_ID` is empty, the bot falls back to `ADMIN_UPI_ID`.

## Nginx reverse proxy

Example Nginx server block:

```nginx
server {
    listen 80;
    server_name bot.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

After Nginx is serving your domain correctly, run:

```bash
sudo certbot --nginx -d bot.example.com
```

## Telegram integration

1. Open `@BotFather` in Telegram.
2. Run `/newbot` and complete the setup.
3. Copy the bot token into `TELEGRAM_BOT_TOKEN`.
4. Send at least one message to your bot from the owner account.
5. Get the owner Telegram ID using `@userinfobot` or by calling `getUpdates`.
6. Put that numeric ID into `ADMIN_TELEGRAM_ID`.

Manual webhook setup after your domain is live:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://bot.example.com/webhooks/telegram/<TELEGRAM_WEBHOOK_SECRET>"
```

You can also set:

- `APP_DOMAIN=https://bot.example.com`
- `AUTO_REGISTER_WEBHOOK=true`

and restart the API container so TezQR registers the webhook automatically on startup.

## Owner payment configuration

For TezQR Premium payment instructions:

- `ADMIN_UPI_ID` is the default owner UPI ID.
- `SUBSCRIPTION_PAYMENT_UPI_ID` overrides the default owner UPI ID for premium payment collection.
- `SUBSCRIPTION_PAYMENT_LINK` adds a direct payment URL in the paywall reply.
- `SUBSCRIPTION_PAYMENT_QR` sends a hosted QR image URL or Telegram file ID in the paywall reply.

## Health checks

Direct API health:

```bash
curl http://127.0.0.1:8000/health
```

Container status:

```bash
docker compose \
  --env-file .env.server \
  -f docker-compose-prod.yml \
  -f docker-compose-server.yml \
  ps
```

