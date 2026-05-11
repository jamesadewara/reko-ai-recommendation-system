import logging
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from beanie import PydanticObjectId
from app.documents.chat import ChatSession, Message as ChatMessage
from app.core.security import verify_token
from app.core.connections import manager
from app.managers.stream_manager import stream_manager

logger = logging.getLogger(__name__)
router = APIRouter()

@router.websocket("/control/{chat_id}")
async def websocket_control(
    websocket: WebSocket, 
    chat_id: str,
    token: str
):
    """
    Lightweight WebSocket Control Plane.
    Handles signaling, heartbeats, and interrupts.
    """
    user_id = None
    try:
        # 1. Authenticate
        from fastapi.security import HTTPAuthorizationCredentials
        try:
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            payload = await verify_token(creds)
            user_id = payload.get("user_id") or payload.get("sub")
        except Exception as auth_err:
            logger.warning(f"Control WS auth failed: {auth_err}")
            await websocket.close(code=4001)
            return

        # 2. Connect
        await websocket.accept()
        await manager.connect(user_id, websocket)
        
        if not PydanticObjectId.is_valid(chat_id):
            await websocket.close(code=4000, reason="Invalid ID")
            return

        logger.info(f"User {user_id} connected to Control Plane for {chat_id}")
        
        # Trigger background profile synchronization
        from app.documents.user import UserDocument
        async def background_sync():
            try:
                user = await UserDocument.get_or_create_from_token(payload)
                await user.sync_with_auth(token)
            except Exception as e:
                logger.error(f"Background sync failed: {e}")
                
        asyncio.create_task(background_sync())

        # Auto-trigger greeting if it's a new chat
        chat = await ChatSession.get(chat_id)
        if chat and len(chat.messages) == 0:
            user = await UserDocument.get_or_create_from_token(payload)
            is_fresh = not user.taste_profile.interests or len(user.taste_profile.interests) < 3

            trigger_message = None
            if user.should_greet_birthday():
                trigger_message = "[Birthday Initialization]"
                # Stamp now so opening other chats today doesn't re-trigger
                asyncio.create_task(user.record_birthday_greeted())
            elif is_fresh:
                trigger_message = "[System Initialization]"

            if trigger_message:
                session = await stream_manager.create_session(chat_id)
                await websocket.send_json({
                    "type": "stream_init",
                    "stream_id": session.stream_id,
                    "url": f"/api/v1/chats/{chat_id}/stream/{session.stream_id}"
                })
                from app.api.v1.endpoints.chats import process_and_stream, ChatMessageRequest
                init_payload = ChatMessageRequest(message=trigger_message, mode="chat", hybrid=True)
                asyncio.create_task(process_and_stream(chat_id=chat_id, user_id=user_id, payload=init_payload, stream_id=session.stream_id))

        # 3. Control Loop
        while True:
            # Wait for message with a timeout for heartbeats
            try:
                data_text = await asyncio.wait_for(websocket.receive_text(), timeout=35.0)
                data = json.loads(data_text)
                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong", "timestamp": asyncio.get_event_loop().time()})
                
                elif msg_type == "interrupt":
                    await stream_manager.interrupt_chat(chat_id)
                    await manager.send_to_user(user_id, {"type": "control_ack", "action": "interrupted"})

                elif msg_type == "message" or msg_type == "init" or msg_type == "start_flow" or msg_type == "flow_complete":
                    # --- HYBRID FLOW: User sends via WS -> Server triggers SSE ---
                    
                    # Ensure any existing streams for this chat are stopped first
                    await stream_manager.interrupt_chat(chat_id)
                    
                    content = data.get("content") or data.get("message") or ""
                    mode = data.get("mode", "chat")
                    
                    # 1. Save User Message (if not just an init pulse)
                    chat = await ChatSession.get(chat_id)
                    if not chat:
                        await websocket.send_json({"type": "error", "message": "Chat not found"})
                        continue
                        
                    if msg_type == "init" and len(chat.messages) > 0:
                        # Ignore redundant init pulses if chat already has messages
                        continue
                        
                    if msg_type == "message":
                        # Skip saving hidden system triggers to the database
                        HIDDEN_TRIGGERS = ["[Contextual Mode Switch]"]
                        if content not in HIDDEN_TRIGGERS:
                            user_msg = ChatMessage(sender_id=user_id, content=content)
                            chat.messages.append(user_msg)
                            await chat.save()

                    # 2. Initialize SSE Stream Session
                    session = await stream_manager.create_session(chat_id)
                    
                    # 3. Inform Client to open SSE for the AI response
                    await websocket.send_json({
                        "type": "stream_init",
                        "stream_id": session.stream_id,
                        "url": f"/api/v1/chats/{chat_id}/stream/{session.stream_id}"
                    })

                    if msg_type == "start_flow":
                        from app.services.flows import flow_service
                        
                        # Gather history for context
                        history = []
                        for m in chat.messages[-5:]:
                            history.append({"role": "assistant" if m.sender_id == "ai_system" else "user", "content": m.content})
                        
                        steps = await flow_service.get_flow_steps(mode, chat_history=history)
                        await websocket.send_json({
                            "type": "flow_step",
                            "steps": steps
                        })
                        continue # Don't trigger AI processing yet, wait for flow answers
                        
                    # 4. Trigger AI Processing (Imported from chats.py)
                    from app.api.v1.endpoints.chats import process_and_stream, ChatMessageRequest
                    
                    if msg_type == "message":
                        internal_content = content
                    elif msg_type == "flow_complete":
                        internal_content = "[Flow Complete]"
                    else:
                        internal_content = "[System Initialization]"
                        
                    payload = ChatMessageRequest(
                        message=internal_content,
                        mode=mode,
                        hybrid=data.get("hybrid", True),
                        flow_answers=data.get("flow_answers")
                    )
                    
                    # Spawn the background task to push to the SSE queue
                    asyncio.create_task(process_and_stream(
                        chat_id=chat_id,
                        user_id=user_id,
                        payload=payload,
                        stream_id=session.stream_id
                    ))

                elif msg_type == "typing":
                    # Broadcast typing status back (or to other sessions if multi-device)
                    status = data.get("status", "thinking")
                    await manager.send_to_user(user_id, {"type": "typing", "status": status})

                elif msg_type == "edit":
                    # Handle message edit logic: Truncate and re-trigger AI
                    msg_id = data.get("message_id")
                    new_content = data.get("content")
                    mode = data.get("mode", "chat")
                    
                    if msg_id and new_content:
                        chat = await ChatSession.get(chat_id)
                        if chat:
                            idx = next((i for i, m in enumerate(chat.messages) if m.id == msg_id), -1)
                            if idx != -1:
                                # Update content and truncate history
                                chat.messages[idx].content = new_content
                                chat.messages = chat.messages[:idx + 1]
                                await chat.save()
                                
                                # Acknowledge truncation
                                await manager.send_to_user(user_id, {"type": "edit_ack", "message_id": msg_id, "truncated": True})
                                
                                # Stop any existing stream
                                await stream_manager.interrupt_chat(chat_id)
                                
                                # Trigger new AI Response
                                session = await stream_manager.create_session(chat_id)
                                await websocket.send_json({
                                    "type": "stream_init",
                                    "stream_id": session.stream_id,
                                    "url": f"/api/v1/chats/{chat_id}/stream/{session.stream_id}"
                                })

                                from app.api.v1.endpoints.chats import process_and_stream, ChatMessageRequest
                                payload = ChatMessageRequest(
                                    message=new_content,
                                    mode=mode,
                                    hybrid=data.get("hybrid", True),
                                    flow_answers=data.get("flow_answers")
                                )
                                asyncio.create_task(process_and_stream(
                                    chat_id=chat_id,
                                    user_id=user_id,
                                    payload=payload,
                                    stream_id=session.stream_id
                                ))

            except asyncio.TimeoutError:
                # Send a ping to check if client is still there
                try:
                    await websocket.send_json({"type": "ping_check"})
                except:
                    break

    except WebSocketDisconnect:
        if user_id: await manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"Control WS Error: {e}")
        if user_id: await manager.disconnect(user_id, websocket)
