"""OpenAPI metadata used by the FastAPI application.

The descriptions here are intentionally written for teammates and integrators.
They explain how the HTTP surface maps back to the internal layers:

- models: domain entities and SQLAlchemy models
- views: FastAPI routes plus request/response schemas
- controllers: thin HTTP adapters that translate transport details
- services: orchestration and business use cases
- repositories: persistence adapters behind the application layer
"""

OPENAPI_DESCRIPTION = """
TezQR is a layered merchant bot and provider payment orchestration backend.

The API exposes:

- the legacy Telegram merchant bot webhook
- white-label provider bot webhooks for Telegram and WhatsApp
- a provider control plane for clients, templates, payments, reminders, exports, and QR assets

The codebase is organized so that HTTP handlers stay thin, application services own
use-case orchestration, domain models hold business rules, and repositories isolate
database access for scalability and maintainability.
""".strip()


OPENAPI_TAGS = [
    {
        "name": "System",
        "description": (
            "Health and platform-level endpoints used by infrastructure and runtime checks."
        ),
    },
    {
        "name": "Merchant Bot",
        "description": "Legacy Telegram merchant bot webhook used by the original TezQR flow.",
    },
    {
        "name": "Provider Webhooks",
        "description": (
            "White-label inbound webhook handlers for provider Telegram and WhatsApp bots."
        ),
    },
    {
        "name": "Provider API",
        "description": (
            "Provider-facing control-plane APIs for onboarding, payment operations, reminders, "
            "broadcasts, exports, and QR asset retrieval."
        ),
    },
]
