from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.exceptions import register_exception_handlers
from app.api.router import api_router
from app.api import ws as ws_module


setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Database: {settings.DB_PATH}")
    logger.info(f"Projects dir: {settings.PROJECTS_DIR}")
    logger.info(f"ComfyUI URL: {settings.COMFYUI_URL}")

    # Initialize database
    from app.database import init_db, enable_wal_mode
    await init_db()
    await enable_wal_mode()
    logger.info("Database initialized (WAL mode)")

    # Initialize default settings
    from app.database import get_db
    from app.repositories.settings_repo import SettingsRepository
    async for db in get_db():
        repo = SettingsRepository(db)
        await repo.init_defaults()
        break
    logger.info("Settings defaults loaded")

    # Start queue manager
    from app.workers.queue_manager import queue_manager
    await queue_manager.start()
    logger.info("Queue manager started")

    logger.info(f"Server ready at http://{settings.HOST}:{settings.PORT}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await queue_manager.stop()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Backend API for Faceless Video Generator",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS - allow Tauri and dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "tauri://localhost",
            "https://tauri.localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register exception handlers
    register_exception_handlers(app)

    # Mount REST API routers
    app.include_router(api_router, prefix="/api/v1")

    # Mount WebSocket routes (no prefix, at root level)
    app.include_router(ws_module.router, tags=["websocket"])

    @app.get("/health")
    async def health_check():
        return JSONResponse({"status": "ok", "version": settings.APP_VERSION})

    @app.get("/")
    async def root():
        return JSONResponse({
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
        })

    return app


app = create_app()
