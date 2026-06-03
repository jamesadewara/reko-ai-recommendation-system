import asyncio
import uuid
from typing import Dict, Any, Optional, AsyncGenerator
from loguru import logger

class StreamSession:
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.items = []
        self.interrupted = asyncio.Event()
        self.finished = asyncio.Event()
        self.stream_id = str(uuid.uuid4())
        self._lock = asyncio.Lock()
        self._new_item_event = asyncio.Condition()

    async def push(self, event: str, data: Any):
        item = {"event": event, "data": data}
        async with self._new_item_event:
            self.items.append(item)
            self._new_item_event.notify_all()
        if event == "done":
            self.finished.set()

    async def get_items_after(self, index: int):
        """Returns new items after the given index, or waits for them."""
        async with self._new_item_event:
            while index >= len(self.items):
                if self.finished.is_set() or self.interrupted.is_set():
                    return []
                await self._new_item_event.wait()
            
            return self.items[index:], len(self.items)

class StreamManager:
    def __init__(self):
        # stream_id -> StreamSession
        self._sessions: Dict[str, StreamSession] = {}
        # chat_id -> stream_id (to allow interrupting the latest stream for a chat)
        self._active_chat_streams: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, chat_id: str) -> StreamSession:
        session = StreamSession(chat_id)
        async with self._lock:
            # If there's an existing stream for this chat, we might want to interrupt it
            # but usually, the client handles starting new ones.
            self._sessions[session.stream_id] = session
            self._active_chat_streams[chat_id] = session.stream_id
        return session

    async def get_session(self, stream_id: str) -> Optional[StreamSession]:
        return self._sessions.get(stream_id)

    async def interrupt_chat(self, chat_id: str):
        async with self._lock:
            stream_id = self._active_chat_streams.get(chat_id)
            if stream_id and stream_id in self._sessions:
                self._sessions[stream_id].interrupted.set()
                logger.info(f"Stream {stream_id} for chat {chat_id} interrupted.")

    async def remove_session(self, stream_id: str):
        async with self._lock:
            session = self._sessions.pop(stream_id, None)
            if session and self._active_chat_streams.get(session.chat_id) == stream_id:
                del self._active_chat_streams[session.chat_id]
        logger.info(f"Stream session {stream_id} removed.")

stream_manager = StreamManager()
