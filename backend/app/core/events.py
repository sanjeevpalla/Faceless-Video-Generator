import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections per project."""

    def __init__(self) -> None:
        # project_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        # Global connections (receive all broadcasts)
        self._global_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, project_id: Optional[str] = None) -> None:
        await websocket.accept()
        async with self._lock:
            if project_id:
                self._connections[project_id].add(websocket)
                logger.info(
                    f"WebSocket connected for project {project_id}. "
                    f"Total: {len(self._connections[project_id])}"
                )
            else:
                self._global_connections.add(websocket)
                logger.info("Global WebSocket connected.")

    async def disconnect(self, websocket: WebSocket, project_id: Optional[str] = None) -> None:
        async with self._lock:
            if project_id and project_id in self._connections:
                self._connections[project_id].discard(websocket)
                if not self._connections[project_id]:
                    del self._connections[project_id]
                logger.info(f"WebSocket disconnected for project {project_id}")
            else:
                self._global_connections.discard(websocket)
                logger.info("Global WebSocket disconnected.")

    async def broadcast_to_project(
        self,
        project_id: str,
        event: str,
        data: Dict[str, Any],
        job_id: Optional[str] = None,
    ) -> None:
        message = json.dumps(
            {
                "event": event,
                "project_id": project_id,
                "job_id": job_id,
                "data": data,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )
        dead_connections: Set[WebSocket] = set()

        connections = set(self._connections.get(project_id, set()))
        for ws in connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception as exc:
                logger.warning(f"Failed to send to WS client: {exc}")
                dead_connections.add(ws)

        # Also broadcast to global subscribers
        for ws in set(self._global_connections):
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception as exc:
                logger.warning(f"Failed to send to global WS client: {exc}")
                dead_connections.add(ws)

        # Cleanup dead connections
        if dead_connections:
            async with self._lock:
                self._connections[project_id] -= dead_connections
                self._global_connections -= dead_connections

    async def broadcast_all(self, event: str, data: Dict[str, Any]) -> None:
        message = json.dumps(
            {
                "event": event,
                "data": data,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        )
        dead: Set[WebSocket] = set()
        all_ws: Set[WebSocket] = set(self._global_connections)
        for project_conns in self._connections.values():
            all_ws.update(project_conns)

        for ws in all_ws:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(message)
            except Exception as exc:
                logger.warning(f"Failed broadcast to WS: {exc}")
                dead.add(ws)

        if dead:
            async with self._lock:
                self._global_connections -= dead
                for pid in list(self._connections.keys()):
                    self._connections[pid] -= dead

    def get_connection_count(self, project_id: Optional[str] = None) -> int:
        if project_id:
            return len(self._connections.get(project_id, set()))
        total = len(self._global_connections)
        for conns in self._connections.values():
            total += len(conns)
        return total


# Singleton instance
connection_manager = ConnectionManager()
