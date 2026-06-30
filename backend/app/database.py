from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_async_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.get_db_url()
        _engine = create_async_engine(
            db_url,
            echo=settings.DEBUG,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,  # wait up to 30s for a lock instead of failing immediately
            },
        )
    return _engine


async def enable_wal_mode() -> None:
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(__import__("sqlalchemy").text("PRAGMA journal_mode=WAL"))
        await conn.execute(__import__("sqlalchemy").text("PRAGMA synchronous=NORMAL"))
        await conn.commit()


def get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def init_db() -> None:
    from app.models import project, settings, job, log  # noqa: F401
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_migrations(conn)


async def _apply_migrations(conn) -> None:
    """Add new columns to existing tables without dropping data."""
    import sqlalchemy as sa
    for table, column, col_def in [
        ("projects", "language", "VARCHAR(16) DEFAULT 'en'"),
        ("projects", "project_type", "VARCHAR(32) DEFAULT 'deep_dive'"),
    ]:
        try:
            await conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"))
        except Exception:
            pass  # Column already exists


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
