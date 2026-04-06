from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from tezqr.infrastructure.container import AppContainer, build_container
from tezqr.presentation.docs import OPENAPI_DESCRIPTION, OPENAPI_TAGS
from tezqr.presentation.router import router
from tezqr.shared.config import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    container: AppContainer | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    app_container = container or build_container(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = app_container
        await app_container.startup()
        try:
            yield
        finally:
            await app_container.shutdown()

    app = FastAPI(
        title=app_settings.app_name,
        description=OPENAPI_DESCRIPTION,
        version="0.1.0",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
