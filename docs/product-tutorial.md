# TezQR Product Tutorial

## 1. What TezQR is

TezQR is a FastAPI backend for QR-based payment workflows.

It currently supports two product surfaces:

1. A legacy Telegram merchant bot
   Small merchants message a bot, set a UPI ID, and generate payment QR codes.

2. A provider control plane
   A provider can manage clients, payment destinations, branded bot instances,
   reusable templates, reminders, exports, and QR assets through HTTP APIs.

Think of TezQR as a payment-request and QR-orchestration backend with two entry points:

- chat-first automation for merchants and clients
- API-first control for providers and operators

## 2. Who uses the product

### Merchant

A merchant uses the original Telegram bot to:

- register themselves
- set their UPI VPA
- generate payment QR codes
- request a premium upgrade when free quota is exhausted

### Provider

A provider is a business operating branded payment workflows for clients. A provider can:

- create a workspace
- define team members and roles
- register multiple UPI destinations
- onboard clients
- create branded Telegram or WhatsApp bot instances
- manage payment requests and reminders

### Client

A client is the end recipient of a payment request. A client can:

- be onboarded manually through the API
- be onboarded automatically through a provider Telegram bot
- be onboarded automatically through a provider WhatsApp bot
- receive payment requests, reminders, and broadcasts

### Admin / Owner

The owner is the operator of the original TezQR merchant bot. The owner can:

- view stats
- approve merchant upgrade requests
- broadcast messages to merchants

## 3. High-level product map

```text
Legacy merchant bot
Telegram -> /webhooks/telegram/{secret} -> BotService -> domain + UoW -> QR reply

Provider API
HTTP client -> /api/providers/... -> ControlPlaneService -> repositories + models -> JSON / files

Provider Telegram bot
Telegram -> /webhooks/provider-bots/{secret}/telegram -> ControlPlaneService -> payment/template/client flows

Provider WhatsApp bot
WhatsApp webhook -> /webhooks/provider-bots/{secret}/whatsapp -> ControlPlaneService -> reply + share link
```

## 4. Legacy merchant bot tutorial

This is the simplest way to understand the original product.

### Step 1: Merchant starts the bot

The merchant sends:

```text
/start
```

What happens:

- a merchant record is created if one does not exist
- the Telegram profile is refreshed if it already exists
- the bot sends the welcome message

### Step 2: Merchant configures their UPI ID

The merchant sends:

```text
/setupi myshop@okaxis
```

What happens:

- the VPA is validated
- the merchant record is updated
- future payment requests will use this VPA

### Step 3: Merchant creates a payment QR

The merchant sends:

```text
/pay 499 Website order
```

What happens:

- the amount and description are validated
- a fixed-amount `upi://pay` link is generated
- a QR PNG is generated from that link
- the bot returns the QR image in Telegram

### Step 4: Merchant hits free quota

The legacy merchant flow has a quota model.

When the merchant exhausts free QR generations:

- the bot shows a paywall response
- the owner payment details are used to generate a premium payment QR or link
- the merchant is asked to submit a screenshot

### Step 5: Merchant requests upgrade

The merchant sends a screenshot as a photo or document.

What happens:

- an upgrade request is created
- the bot acknowledges the screenshot
- the owner/admin receives the forwarded message and approval code

### Step 6: Owner approves the upgrade

The owner can approve manually through commands like:

```text
/approve <approval_code>
```

or

```text
/upgrade <telegram_id>
```

What happens:

- the merchant is upgraded to premium
- pending upgrade requests are marked approved
- the merchant receives a confirmation

## 5. Provider control-plane tutorial

The provider surface is more powerful and more representative of a modern backend system.

### Step 1: Create a provider workspace

Call:

```http
POST /api/providers
```

Purpose:

- create the provider workspace
- create provider branding
- return the provider API key
- optionally seed the owner role

Typical request:

```json
{
  "slug": "acme-pay",
  "name": "Acme Pay",
  "logo_text": "AC",
  "owner_actor_code": "OWNER1",
  "owner_display_name": "Owner One"
}
```

### Step 2: Add provider team members

Call:

```http
POST /api/providers/{provider_slug}/members
```

Headers:

- `x-api-key`
- `x-actor-code`

Roles currently supported:

- `owner`
- `manager`
- `operator`
- `viewer`

Use this when you want separate access levels for support staff, ops staff, or read-only users.

### Step 3: Add payment destinations

Call:

```http
POST /api/providers/{provider_slug}/destinations
```

Why this matters:

- a provider can maintain multiple UPI IDs
- one destination can be marked as default
- templates and payments can target specific destinations

Typical use cases:

- one UPI ID per branch
- one UPI ID for online flows, another for walk-ins
- one fallback destination if the primary is unavailable

### Step 4: Create provider bot instances

Call:

```http
POST /api/providers/{provider_slug}/bots
```

You can create:

- Telegram bot instances
- WhatsApp bot instances

Each bot instance can have:

- its own display name
- public handle
- webhook secret
- optional branding override

Important note:

- Telegram can send directly if a valid bot token is configured.
- WhatsApp is currently provider-agnostic and manual-share based on outbound delivery.

### Step 5: Add or onboard clients

Clients can enter the system in three ways:

1. Manual creation through:

```http
POST /api/providers/{provider_slug}/clients
```

2. Provider Telegram webhook onboarding

- a client messages the provider Telegram bot
- the webhook upserts a client using the Telegram user ID
- `onboarding_source` becomes `telegram_bot`

3. Provider WhatsApp webhook onboarding

- a client messages the provider WhatsApp bot
- the webhook upserts a client using the WhatsApp number
- `onboarding_source` becomes `whatsapp_bot`

### Step 6: Create reusable templates

Call:

```http
POST /api/providers/{provider_slug}/templates
```

Templates are how providers avoid repeating the same payment configuration.

A template can include:

- a name
- description
- item code
- default amount
- destination code
- message template
- custom message
- `pre_generate`

If `pre_generate` is true and there is a default amount, TezQR creates QR assets immediately.

### Step 7: Resolve a QR by item code

Call:

```http
GET /api/providers/{provider_slug}/item-code/{item_code}
```

This is useful for:

- product or service lookup
- cashier workflows
- quick chat-based retrieval

Behavior:

- if a pre-generated asset exists and no custom amount is needed, it returns the asset
- otherwise it creates a payment request on demand

### Step 8: Create a payment request

Call:

```http
POST /api/providers/{provider_slug}/payments
```

A payment request can be linked to:

- a client
- a template
- an item code
- a destination
- a due date
- a preferred delivery channel

Every payment request generates an asset bundle:

- raw QR image
- branded payment card
- print-ready payment image

### Step 9: Share the payment request

Call:

```http
POST /api/providers/{provider_slug}/payments/{payment_reference}/share
```

Supported channels:

- Telegram
- WhatsApp

What happens:

- TezQR resolves the client
- it builds a user-facing payment message
- it selects the preferred asset
- it either sends directly or generates a manual share link
- it records an outbound message audit row

### Step 10: Track payment status

Call:

```http
POST /api/providers/{provider_slug}/payments/{payment_reference}/status
```

Current status values:

- `pending`
- `paid`
- `overdue`

This is currently manual status tracking, which is still very useful for ops and support workflows.

### Step 11: Add notes and review history

Calls:

```http
POST /api/providers/{provider_slug}/payments/{payment_reference}/notes
GET  /api/providers/{provider_slug}/payments/{payment_reference}/history
```

Use this to:

- record a manual payment confirmation
- keep internal context
- review what happened to a payment over time

History includes:

- notes
- payment logs
- sharing events
- status changes
- reminder events

### Step 12: Create reminders

Call:

```http
POST /api/providers/{provider_slug}/reminders
```

Reminder types:

- `scheduled`
- `manual`
- `task`

Typical use cases:

- scheduled follow-ups
- send-now nudges
- task-based collection workflows

Due reminders can be processed with:

```http
POST /api/providers/{provider_slug}/reminders/run-due
```

### Step 13: Broadcast messages to many clients

Call:

```http
POST /api/providers/{provider_slug}/broadcasts
```

Broadcasts can be:

- plain text
- template-backed payment requests
- amount-backed payment requests

This supports multi-client campaigns such as:

- payment collection pushes
- service reminders
- promotions

### Step 14: Use dashboard, exports, and asset downloads

Useful endpoints:

- `GET /api/providers/{provider_slug}/dashboard`
- `GET /api/providers/{provider_slug}/exports/payments?format=csv`
- `GET /api/providers/{provider_slug}/qr-assets`
- `GET /api/providers/{provider_slug}/qr-assets/{asset_code}/download`

These cover:

- operator visibility
- basic reporting
- asset retrieval for print or external use

## 6. Provider bot workflows

### Provider Telegram bot

Supported bot commands:

- `/login <actor_code> <api_key>`
- `/whoami`
- `/onboardlink`
- `/item_code <code> [amount]` on Telegram menu, `/item-code <code> [amount]` also works
- `/pay <amount> <description>`
- `/dashboard`
- `/clients`
- `/payments <client_code>`
- `/history <payment_reference>`
- `/charge <client_code> <amount> <description>`
- `/share <payment_reference> [telegram|whatsapp]`
- `/status <payment_reference> <pending|paid|overdue> [notes]`
- `/note <payment_reference> <note>`
- `/remind <payment_reference> <message>`
- `/remindat <payment_reference> <iso_datetime> <message>`
- `/runreminders`
- `/memberadd <actor_code> <owner|manager|operator|viewer> <display_name>`

What the Telegram bot does:

- links provider team members to Telegram identities for RBAC-aware commands
- gives viewer/operator/manager/owner menus after login
- exposes the configured public bot link through `/onboardlink`
- creates or updates the client automatically
- resolves or creates payment requests
- downloads the best asset
- sends the QR/payment card directly through Telegram

### Provider WhatsApp bot

Current behavior:

- supports `/login <actor_code> <api_key>` for provider staff
- supports `/whoami`, `/onboardlink`, `/dashboard`, `/clients`, `/payments`, and `/history`
- supports `/charge`, `/share`, `/status`, `/note`, `/remind`, and `/runreminders` for linked staff
- creates or updates the client automatically
- supports `/item_code <code> [amount]` on Telegram menu, while also accepting `/item-code <code> [amount]`
- supports `/pay <amount> <description>`
- returns payment text plus a `wa.me` share URL

Important limitation:

- outbound WhatsApp delivery is currently manual-share oriented rather than BSP-driven

## 7. QR assets explained

Every provider payment can generate up to three PNG assets:

1. `payment_qr`
   Raw QR image.

2. `payment_card`
   Branded payment card for chat sharing.

3. `print_ready`
   Print-focused version for physical use.

The branding is based on:

- provider branding
- optional bot branding overrides

## 8. Local testing tutorial

### Run the app locally

```bash
docker compose -f docker-compose-local.yml up --build -d
docker compose -f docker-compose-local.yml exec -T api uv run alembic upgrade head
```

Then verify:

```bash
curl http://127.0.0.1:8000/health
```

### Explore the API

Open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

### Run tests

```bash
uv run pytest -q
```

### Test provider flow quickly

Recommended manual sequence:

1. Create a provider
2. Add a destination
3. Add a Telegram bot instance
4. Add a client
5. Create a template
6. Create a payment
7. Share it
8. Mark it paid
9. Add a note
10. Export payments

## 9. Product boundaries and current caveats

### Strongly implemented today

- fixed-amount UPI link generation
- QR generation
- multiple UPI destinations
- provider branding
- white-label Telegram bot flows
- provider client/template/payment/reminder management
- export and asset retrieval

### Intentionally simple today

- payment status is manual
- legacy merchant bot is still Telegram-only
- WhatsApp outbound is manual-share based
- provider authentication is API-key plus actor-code based, not user login based

## 10. How to think about the product

The easiest mental model is:

- the legacy bot is a small merchant self-service product
- the provider control plane is an operator backend for managing many payment workflows

Both surfaces share the same codebase, but they serve different audiences and different
levels of operational complexity.
