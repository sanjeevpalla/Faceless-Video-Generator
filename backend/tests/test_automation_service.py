"""Tests for AutomationService — creates a project and enqueues its pipeline job."""
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.project import ProjectStatus


@pytest.fixture()
def patched_session_factory(monkeypatch, db_engine):
    """Point app.database.get_session_factory() at the in-memory test engine,
    and stub out enqueue_pipeline_job so no real queue/pipeline machinery runs."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    import app.database as database_module

    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(database_module, "get_session_factory", lambda: factory)

    enqueued = []

    async def fake_enqueue(project, job_repo, settings_repo):
        enqueued.append(project.id)
        return "fake-job-id"

    import app.services.automation_service as automation_module
    monkeypatch.setattr(automation_module, "enqueue_pipeline_job", fake_enqueue)

    return enqueued


class TestAutomationService:
    @pytest.mark.asyncio
    async def test_create_and_start_deep_dive_creates_project(
        self, patched_session_factory, tmp_path, monkeypatch,
    ):
        from app.config import get_settings
        import app.services.automation_service as automation_module

        cfg = get_settings()
        monkeypatch.setattr(cfg, "PROJECTS_DIR", tmp_path)

        project_id = await automation_module.create_and_start_deep_dive()

        assert project_id is not None
        assert patched_session_factory == [project_id]

        # Directory structure was created
        created_dirs = list(tmp_path.iterdir())
        assert len(created_dirs) == 1
        assert (created_dirs[0] / "input").exists()
        assert (created_dirs[0] / "output").exists()

    @pytest.mark.asyncio
    async def test_create_and_start_ai_news_sets_project_type(
        self, patched_session_factory, tmp_path, monkeypatch,
    ):
        from app.config import get_settings
        import app.database as database_module
        import app.services.automation_service as automation_module
        from app.repositories.project_repo import ProjectRepository

        cfg = get_settings()
        monkeypatch.setattr(cfg, "PROJECTS_DIR", tmp_path)

        project_id = await automation_module.create_and_start_ai_news()

        async with database_module.get_session_factory()() as sess:
            repo = ProjectRepository(sess)
            project = await repo.get_by_id(project_id)

        assert project is not None
        assert project.project_type == "ai_news"
        assert project.status == ProjectStatus.CREATED
