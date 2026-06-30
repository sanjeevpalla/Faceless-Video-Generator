"""Shared pytest fixtures for all tests."""
import json
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# ── app imports ──
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import create_app
from app.database import Base, get_db
from app.core.dependencies import get_db_session


# ---------------------------------------------------------------------------
# Project directory fixtures (sync — no async needed for mkdir)
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_project_dir(tmp_path: Path) -> Path:
    """Temporary project directory with all required subdirs."""
    pdir = tmp_path / "test_project"
    for sub in [
        "input", "images", "audio", "subtitles", "thumbnail",
        "output", "cache/images", "cache/audio", "cache/subtitles", "cache/thumbnail",
        "logs", "temp", "metadata",
    ]:
        (pdir / sub).mkdir(parents=True, exist_ok=True)
    return pdir


@pytest.fixture()
def scenes_json(tmp_project_dir: Path) -> Path:
    data = {
        "video_title": "Test Video",
        "total_duration": 30,
        "scenes": [
            {"scene_id": 1, "title": "Intro", "image_file": "scene_001.png",
             "duration": 10, "narration": "Hello world, this is scene one.", "visual_description": "intro"},
            {"scene_id": 2, "title": "Middle", "image_file": "scene_002.png",
             "duration": 10, "narration": "This is scene two of the video.", "visual_description": "middle"},
            {"scene_id": 3, "title": "Outro", "image_file": "scene_003.png",
             "duration": 10, "narration": "Goodbye from scene three.", "visual_description": "outro"},
        ],
    }
    path = tmp_project_dir / "input" / "scenes.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture()
def image_prompts_txt(tmp_project_dir: Path) -> Path:
    lines = [
        "Futuristic city at dawn, cinematic, high quality",
        "Close-up of a glowing computer screen, blue tones",
        "Epic mountain landscape, golden hour photography",
    ]
    path = tmp_project_dir / "input" / "image_prompts.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture()
def thumbnail_prompt_txt(tmp_project_dir: Path) -> Path:
    path = tmp_project_dir / "input" / "thumbnail_prompt.txt"
    path.write_text("Professional YouTube thumbnail, vibrant colors, 4K", encoding="utf-8")
    return path


@pytest.fixture()
def seo_json(tmp_project_dir: Path) -> Path:
    data = {
        "title": "Test Video Title Under 100 Chars",
        "description": "This is a test description for the video.",
        "tags": ["ai", "technology", "tutorial"],
        "hashtags": ["#AI", "#Tech"],
        "chapters": [{"timestamp": "0:00", "title": "Introduction"}],
    }
    path = tmp_project_dir / "input" / "seo.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_engine():
    """
    In-memory SQLite engine using StaticPool so all async sessions share
    the same underlying connection — essential for in-memory SQLite to work
    correctly across multiple sessions within a single test.
    """
    # Import models so Base.metadata is populated
    from app.models import project, settings, job, log  # noqa: F401

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# HTTP test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    """
    Full FastAPI test client with DB dependency overridden to use the
    in-memory test engine.
    """
    app = create_app()

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        """Override both get_db and get_db_session with the test engine."""
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    # Override both dependency variants used throughout the app
    app.dependency_overrides[get_db] = override_session
    app.dependency_overrides[get_db_session] = override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
