"""System-level endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    summary="Health Check",
    description="Return the current runtime status and configured application environment.",
)
async def health(request: Request) -> dict[str, str]:
    settings = request.app.state.container.settings
    return {"status": "ok", "environment": settings.app_env}
