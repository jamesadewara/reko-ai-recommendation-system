"""
Legacy websocket module - imports from connection_manager for backward compatibility.
New code should import directly from app.core.connection_manager.
"""
from app.core.connection_manager import ConnectionManager, manager

__all__ = ["ConnectionManager", "manager"]

