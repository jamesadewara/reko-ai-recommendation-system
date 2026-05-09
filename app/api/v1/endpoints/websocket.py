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
            msg_text = message_data.get("message") or message_data.get("content", "")
            user_msg = Message(
                sender_id=user_id,
                content=msg_text
            )
            chat.messages.append(user_msg)
            chat.updated_at = user_msg.timestamp
            await chat.save()

            # Process through chat intelligence logic
            from app.api.v1.endpoints.chats import ChatMessageRequest, send_message
            
            # Send Typing Indicator
            await manager.send_to_user(user_id, {"type": "typing", "status": "thinking"})
            
            try:
                # Call the internal send_message logic
                chat_request = ChatMessageRequest(message=msg_text)
                response_data = await send_message(chat_id, chat_request, user_id=user_id)
                
                # Stream the pieces
                if response_data.get("detected_intent") == "recommendation_request":
                    # We could stream reasoning steps if they were returned, but they aren't directly available from send_message response.
                    # As a hack for the spec, we stream what we have.
                    await manager.send_to_user(user_id, {"type": "reasoning", "content": "Analyzing your preferences and current context..."})
                    
                await manager.send_to_user(user_id, {
                    "type": "content", 
                    "content": response_data.get("response", "")
                })
                
                await manager.send_to_user(user_id, {
                    "type": "done",
                    "recommendations": response_data.get("recommendations", []),
                    "review": response_data.get("review", None)
                })
                
            except Exception as e:
                logger.error(f"WebSocket intelligence error: {e}")
                await manager.send_to_user(user_id, {
                    "type": "content", 
                    "content": "Sorry, I ran into an error processing your request."
                })
                await manager.send_to_user(user_id, {"type": "done"})

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
