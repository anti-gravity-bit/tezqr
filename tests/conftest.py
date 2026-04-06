from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command

ROOT_DIR = Path(__file__).resolve().parents[1]


def _as_asyncpg_url(url: str) -> str:
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _run_migrations(database_url: str) -> None:
    config = Config(str(ROOT_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    try:
        with PostgresContainer("postgres:15-alpine") as postgres:
            database_url = _as_asyncpg_url(postgres.get_connection_url())
            _run_migrations(database_url)
            yield database_url
    except Exception as exc:  # pragma: no cover - fallback for missing Docker daemon
        pytest.skip(f"Postgres test container unavailable: {exc}")


@pytest_asyncio.fixture
async def db_session_factory(postgres_database_url: str) -> async_sessionmaker:
    engine = create_async_engine(postgres_database_url, pool_pre_ping=True)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE outbound_messages, qr_assets, payment_logs, payment_notes, "
                "payment_reminders, payment_requests, payment_templates, clients, "
                "payment_destinations, provider_bot_instances, provider_members, providers, "
                "upgrade_requests, merchants "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield async_sessionmaker(bind=engine, expire_on_commit=False)
    await engine.dispose()
