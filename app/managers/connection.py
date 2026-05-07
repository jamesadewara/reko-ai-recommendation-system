import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Maps user_id -> List of active WebSockets
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(user_id, []).append(websocket)
            logger.info(f"[WebSocket] User {user_id} connected. Total user connections: {len(self._connections[user_id])}")

    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if user_id in self._connections:
                try:
                    self._connections[user_id].remove(websocket)
                except ValueError:
                    pass
                if not self._connections[user_id]:
                    del self._connections[user_id]
            logger.info(f"[WebSocket] User {user_id} disconnected.")

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """Send a message to all active connections for a specific user."""
        if user_id in self._connections:
            # We copy the list to avoid issues if a connection disconnects while iterating
            active_connections = list(self._connections[user_id])
            for websocket in active_connections:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"[WebSocket] Failed to send to user {user_id}: {e}")
                    # We don't remove here; the disconnect handler will handle cleanup

    async def broadcast(self, message: dict) -> None:
        """Send a message to every connected client."""
        async with self._lock:
            for user_id, websockets in self._connections.items():
                for websocket in websockets:
                    try:
                        await websocket.send_json(message)
                    except Exception as e:
                        logger.error(f"[WebSocket] Failed to broadcast to user {user_id}: {e}")

# Global singleton instance
manager = ConnectionManager()
