import logging
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.documents.chat import ChatSession, Message
from app.core.security import verify_token
from app.core.connections import manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/chat/{chat_id}")
async def websocket_chat(
    websocket: WebSocket, 
    chat_id: str,
    token: str
):
    """
    WebSocket endpoint for real-time chat.
    Uses token from query param or header for authentication.
    """
    try:
        # 1. Verify Token
        # Note: WebSockets often pass tokens via query params because headers can be tricky
        from fastapi.security import HTTPAuthorizationCredentials
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        payload = await verify_token(creds)
        user_id = payload.get("user_id") or payload.get("sub")
        
        # 2. Connect
        await manager.connect(user_id, websocket)
        
        # 3. Load Chat Session
        chat = await ChatSession.get(chat_id)
        if not chat or chat.user_id != user_id:
            await manager.disconnect(user_id, websocket)
            await websocket.close(code=4004) # Not Found
            return

        logger.info(f"User {user_id} joined chat {chat_id}")

        # 4. Message Loop
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Save User Message
            user_msg = Message(
                sender_id=user_id,
                content=message_data.get("content", "")
            )
            chat.messages.append(user_msg)
            chat.updated_at = user_msg.timestamp
            await chat.save()

            # AI response
            ai_msg = Message(
                sender_id="ai_system",
                content=f"Echo: {user_msg.content}"
            )
            chat.messages.append(ai_msg)
            await chat.save()

            await manager.send_to_user(
                user_id,
                {
                    "id": ai_msg.id,
                    "sender": "ai",
                    "content": ai_msg.content,
                    "timestamp": ai_msg.timestamp.isoformat()
                }
            )

    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
        logger.info(f"User {user_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await manager.disconnect(user_id, websocket)
            await websocket.close(code=1011) # Internal Error
        except:
            pass
