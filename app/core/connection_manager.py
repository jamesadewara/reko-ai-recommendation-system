"""
WebSocket connection manager with singleton pattern.
Maintains user_id -> WebSocket mappings with asyncio locks for thread-safe mutations.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections per user with proper cleanup and thread safety.
    """
    
    def __init__(self):
        # Maps user_id to list of active WebSocket connections
        self._active_connections: Dict[str, List[WebSocket]] = {}
        # AsyncIO lock for thread-safe connection map mutations
        self._lock = asyncio.Lock()
    
    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        """
        Register a new WebSocket connection for a user.
        Connection must be pre-accepted before calling this method.
        
        Args:
            user_id: User identifier
            websocket: Accepted WebSocket connection
        """
        async with self._lock:
            if user_id not in self._active_connections:
                self._active_connections[user_id] = []
            self._active_connections[user_id].append(websocket)
            connection_count = len(self._active_connections[user_id])
        
        logger.info(
            f"[WebSocket] User {user_id} connected. "
            f"Active sessions for user: {connection_count}"
        )
    
    async def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        """
        Unregister a WebSocket connection for a user.
        Cleans up empty user entries to prevent memory leaks.
        
        Args:
            user_id: User identifier
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            if user_id in self._active_connections:
                if websocket in self._active_connections[user_id]:
                    self._active_connections[user_id].remove(websocket)
                
                # Clean up empty entries
                if not self._active_connections[user_id]:
                    del self._active_connections[user_id]
                    logger.info(f"[WebSocket] User {user_id} fully disconnected (no active sessions)")
                else:
                    logger.info(
                        f"[WebSocket] User {user_id} disconnected. "
                        f"Remaining sessions: {len(self._active_connections[user_id])}"
                    )
            else:
                logger.warning(f"[WebSocket] Disconnect called for unknown user: {user_id}")
    
    async def send_to_user(self, user_id: str, message: dict) -> None:
        """
        Send a message to all active connections for a user.
        
        Args:
            user_id: User identifier
            message: Message dict to send as JSON
            
        Returns:
            None (logs errors but doesn't raise)
        """
        async with self._lock:
            connections = self._active_connections.get(user_id, []).copy()
        
        if not connections:
            logger.debug(f"[WebSocket] No active connections for user {user_id}")
            return
        
        disconnected = []
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(
                    f"[WebSocket] Failed to send message to user {user_id}: {str(e)}"
                )
                disconnected.append(connection)
        
        # Clean up failed connections
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    if user_id in self._active_connections and conn in self._active_connections[user_id]:
                        self._active_connections[user_id].remove(conn)
    
    async def broadcast(self, message: dict) -> None:
        """
        Broadcast a message to all connected users.
        
        Args:
            message: Message dict to send as JSON
        """
        async with self._lock:
            all_connections = []
            for user_connections in self._active_connections.values():
                all_connections.extend(user_connections)
        
        if not all_connections:
            logger.debug("[WebSocket] No active connections to broadcast to")
            return
        
        logger.info(f"[WebSocket] Broadcasting to {len(all_connections)} connections")
        
        disconnected = []
        for connection in all_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WebSocket] Broadcast send failed: {str(e)}")
                disconnected.append(connection)
        
        # Clean up failed connections
        if disconnected:
            async with self._lock:
                for conn in disconnected:
                    for user_id, user_conns in list(self._active_connections.items()):
                        if conn in user_conns:
                            user_conns.remove(conn)
                            if not user_conns:
                                del self._active_connections[user_id]
    
    async def get_active_user_count(self) -> int:
        """Get count of users with active connections."""
        async with self._lock:
            return len(self._active_connections)
    
    async def get_total_connection_count(self) -> int:
        """Get total count of all active connections."""
        async with self._lock:
            return sum(len(conns) for conns in self._active_connections.values())


# Singleton instance
manager = ConnectionManager()
