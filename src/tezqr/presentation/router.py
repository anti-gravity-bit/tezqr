"""Route aggregator for the HTTP presentation layer."""

from __future__ import annotations

from fastapi import APIRouter

from tezqr.presentation.controllers.health_controller import router as health_router
from tezqr.presentation.controllers.merchant_webhook_controller import (
    router as merchant_webhook_router,
)
from tezqr.presentation.controllers.provider_api_controller import (
    router as provider_api_router,
)
from tezqr.presentation.controllers.provider_webhook_controller import (
    router as provider_webhook_router,
)

router = APIRouter()
router.include_router(health_router)
router.include_router(merchant_webhook_router)
router.include_router(provider_webhook_router)
router.include_router(provider_api_router)
