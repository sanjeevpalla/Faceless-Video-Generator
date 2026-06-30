"""Entry point for the Faceless Video Generator backend server."""
import sys
import os

# Ensure the backend directory is in the Python path
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info",
        ws_ping_interval=20,
        ws_ping_timeout=20,
    )
