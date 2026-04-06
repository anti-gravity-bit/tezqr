# TezQR Architecture Guide

## 1. Architecture style

TezQR follows a layered backend structure that aims to stay readable while still scaling in
complexity:

- Model
  Domain entities, value objects, enums, SQLAlchemy models, and migrations

- View
  FastAPI request and response schemas plus generated OpenAPI docs

- Controller
  Thin HTTP adapters under `src/tezqr/presentation/controllers`

- Service
  Application orchestration under `src/tezqr/application`

- Repository
  Persistence adapters under `src/tezqr/infrastructure/persistence`

This is not a textbook-pure DDD implementation, but the boundaries are intentional:

- domain code owns business rules and validation
- application code owns use cases
- infrastructure code owns external systems
- presentation code owns transport concerns

## 2. Top-level module map

```text
src/tezqr/
  application/
    commands.py
    control_plane.py
    control_plane_messages.py
    control_plane_presenter.py
    dto.py
    ports.py
    replies.py
    services.py

  domain/
    entities.py
    enums.py
    exceptions.py
    value_objects.py

  infrastructure/
    container.py
    register_webhook.py
    persistence/
      models.py
      provider_control_repository.py
      repositories.py
      uow.py
    qr/
      generator.py
    telegram/
      client.py

  presentation/
    app.py
    dependencies.py
    docs.py
    router.py
    schemas.py
    controllers/
      health_controller.py
      merchant_webhook_controller.py
      provider_api_controller.py
      provider_webhook_controller.py

  shared/
    config.py
    db.py
    time.py
```

## 3. The two bounded product surfaces

### A. Legacy merchant bot

Purpose:

- onboarding merchants
- setting merchant UPI VPA
- generating merchant payment QRs
- handling premium upgrade requests

Main code:

- `application/services.py`
- `application/commands.py`
- `application/replies.py`
- `infrastructure/persistence/repositories.py`
- `infrastructure/persistence/uow.py`

### B. Provider control plane

Purpose:

- workspace management
- branded bot instances
- client management
- template and item-code flows
- payment operations
- reminders, exports, and asset downloads

Main code:

- `application/control_plane.py`
- `application/control_plane_messages.py`
- `application/control_plane_presenter.py`
- `infrastructure/persistence/provider_control_repository.py`
- `presentation/controllers/provider_api_controller.py`
- `presentation/controllers/provider_webhook_controller.py`

## 4. Layer responsibilities

## Domain layer

The domain layer contains:

- entities such as `Merchant`, `PaymentRequest`, `Provider`, `Client`, `PaymentReminder`
- value objects such as `Money`, `UpiVpa`, `PaymentReference`, `PhoneNumber`
- enums such as `PaymentStatus`, `MessageChannel`, `ProviderMemberRole`
- domain exceptions

What belongs here:

- invariants
- input normalization
- business rule validation
- entity state transitions

What should not belong here:

- SQLAlchemy session logic
- FastAPI request objects
- HTTP status handling
- external API calls

## Application layer

The application layer coordinates use cases.

Examples:

- `BotService.handle_message`
- `ControlPlaneService.create_payment_request`
- `ControlPlaneService.share_payment_request`

What belongs here:

- workflow orchestration
- calls across repositories, gateways, and domain objects
- transaction boundaries
- assembling output payloads through presenters

## Infrastructure layer

Infrastructure code connects the app to real systems:

- PostgreSQL through SQLAlchemy
- Alembic migrations
- Telegram HTTP client
- QR generation
- dependency container and app startup

This layer should be replaceable without changing domain rules.

## Presentation layer

The presentation layer converts transport input into application calls.

Examples:

- Telegram webhook JSON -> DTO
- HTTP body -> service arguments
- domain/application exception -> HTTP response

Controllers are intentionally thin and should stay that way.

## 5. Request lifecycle examples

## A. Legacy merchant Telegram webhook

```text
Telegram update
-> presentation/controllers/merchant_webhook_controller.py
-> application/dto.py
-> application/services.py (BotService)
-> domain entities + value objects
-> repositories through Unit of Work
-> QR generator / Telegram gateway
-> Telegram response
```

## B. Provider API payment creation

```text
HTTP POST /api/providers/{provider_slug}/payments
-> provider_api_controller.py
-> presentation/schemas.py validation
-> ControlPlaneService.create_payment_request()
-> provider repository lookups
-> PaymentRequest domain creation
-> SQLAlchemy models persisted
-> QR assets generated
-> presenter serializes payload
-> JSON response
```

## C. Provider Telegram bot `/item-code`

```text
Telegram provider bot webhook
-> provider_webhook_controller.py
-> message DTO conversion
-> ControlPlaneService.handle_provider_telegram_message()
-> client upsert from Telegram identity
-> item-code lookup or payment creation
-> asset download
-> Telegram photo send
```

## D. Provider WhatsApp bot `/item-code`

```text
WhatsApp webhook payload
-> provider_webhook_controller.py
-> ControlPlaneService.handle_provider_whatsapp_message()
-> client upsert from phone number
-> item-code lookup or payment creation
-> manual share URL generation
-> JSON reply with replies + share_url
```

## 6. Data model relationships

The persistence models live in `infrastructure/persistence/models.py`.

### Legacy side

- `MerchantModel`
  A merchant account from the original Telegram bot.

- `PaymentRequestModel`
  Shared table now used by both merchant and provider flows.

- `UpgradeRequestModel`
  Screenshot-based premium upgrade request.

Relationships:

- one merchant -> many payment requests
- one merchant -> many upgrade requests

### Provider side

- `ProviderModel`
  Root workspace.

- `ProviderMemberModel`
  Team member with role-based access.

- `ProviderBotInstanceModel`
  White-label Telegram or WhatsApp bot.

- `PaymentDestinationModel`
  Named UPI destination.

- `ClientModel`
  Saved client record.

- `PaymentTemplateModel`
  Reusable product/service template.

- `PaymentRequestModel`
  Concrete payment operation.

- `PaymentLogModel`
  Append-only events.

- `PaymentNoteModel`
  Manual note entries.

- `PaymentReminderModel`
  Reminder definitions and state.

- `QrAssetModel`
  Raw QR / payment card / print-ready files.

- `OutboundMessageModel`
  Delivery audit row for shares, reminders, and broadcasts.

Relationships:

- one provider -> many members
- one provider -> many bot instances
- one provider -> many destinations
- one provider -> many clients
- one provider -> many templates
- one provider -> many reminders
- one provider -> many QR assets

- one client -> many payment requests
- one template -> many payment requests
- one payment request -> many logs
- one payment request -> many notes
- one payment request -> many QR assets
- one payment request -> many outbound messages

## 7. Persistence patterns

TezQR uses two persistence patterns:

### Unit of Work on the legacy side

Used by the merchant bot flow.

Why:

- the legacy feature set is aggregate-centric
- it benefits from explicit repository interfaces

Files:

- `application/ports.py`
- `infrastructure/persistence/repositories.py`
- `infrastructure/persistence/uow.py`

### Session-bound repository on the provider side

Used by the provider control plane.

Why:

- the provider side has many query combinations
- the service needs richer lookups and reporting queries
- a session-bound repository keeps SQL out of orchestration methods

File:

- `infrastructure/persistence/provider_control_repository.py`

## 8. OpenAPI and HTTP design

FastAPI app setup is in `presentation/app.py`.

Important supporting pieces:

- `presentation/docs.py`
  OpenAPI title, description, and tags

- `presentation/schemas.py`
  request models and transport payload validation

- `presentation/dependencies.py`
  error translation, DTO conversion, shared helper functions

The route aggregator is:

- `presentation/router.py`

Controllers are grouped by responsibility:

- health
- legacy merchant webhook
- provider webhooks
- provider API

## 9. Service support collaborators

The provider service was split to improve readability.

### `control_plane_messages.py`

Responsible for:

- payment message composition
- WhatsApp share URL creation
- provider bot caption and welcome text

### `control_plane_presenter.py`

Responsible for:

- converting internal models into API payload dictionaries
- keeping response shaping out of orchestration methods

These helpers make `ControlPlaneService` easier to read and safer to extend.

## 10. Testing strategy

Test layout:

- `tests/unit/domain`
  Pure domain rules

- `tests/unit/application`
  Bot service orchestration with fakes

- `tests/unit/infrastructure`
  container behavior and startup behavior

- `tests/unit/presentation`
  OpenAPI contract and docs

- `tests/integration`
  persistence interactions

- `tests/e2e`
  full provider and webhook flows

Why this matters:

- unit tests protect business rules
- e2e tests protect the public product surface
- OpenAPI tests protect docs and schema drift

## 11. How to add a feature safely

Use this order:

1. Start with the user workflow
   What should the actor be able to do?

2. Add or update domain rules
   New status, new entity behavior, new validation, and so on.

3. Add persistence support
   Model change, migration, repository query.

4. Add or extend application service methods
   Keep orchestration readable.

5. Expose it through controllers and schemas
   Transport details should stay thin.

6. Add tests at the right level
   Domain, application, persistence, and e2e as needed.

## 12. Current architectural strengths

- strong separation between transport and orchestration
- clear domain validation objects
- practical layering
- thorough end-to-end coverage of the provider surface
- good leverage from OpenAPI docs

## 13. Current architectural limitations

These are reasonable next-step refactors, not failures.

- `ControlPlaneService` is still a large orchestration class
- provider API auth is API-key plus actor-code based, not user/session based
- WhatsApp delivery is manual-share oriented
- reporting is still basic

## 14. Recommended next refactors

If the project grows, the next useful moves are:

1. Split `ControlPlaneService` into domain-focused services
   Example: provider setup, client management, payments, reminders, messaging.

2. Introduce typed response models for provider APIs
   This will improve contract clarity even more.

3. Separate provider and legacy bounded contexts further
   Especially if teams begin working on them independently.

4. Add background job infrastructure
   Useful for scheduled reminders, exports, and delivery retries.
