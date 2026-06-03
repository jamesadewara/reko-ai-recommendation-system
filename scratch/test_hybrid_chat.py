import asyncio
import json
import httpx
import websockets
import sys
from typing import Optional

# Configuration
AUTH_URL = "http://127.0.0.1:8000/api/v1"
BASE_URL = "http://127.0.0.1:8001/api/v1"
WS_URL = "ws://127.0.0.1:8001/api/v1/ws"

async def login(email, password):
    print(f"\n[*] Logging in to {AUTH_URL}/auth/login...")
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.post(
            f"{AUTH_URL}/auth/login", 
            json={"email": email, "password": password}
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} - {resp.text}")
            return None
        data = resp.json()
        print("Login successful.")
        return data["access"]

async def test_chat_flow():
    email = input("Enter email: ").strip() or "jamesadewara3@gmail.com"
    password = input("Enter password: ").strip()
    
    token = await login(email, password)
    if not token:
        return

    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        # 1. Create a Chat
        url = f"{BASE_URL}/chats/"
        print(f"\n[1] Creating new chat at {url}...")
        try:
            resp = await client.post(url)
            if resp.status_code != 201:
                print(f"Failed to create chat: {resp.status_code} - {resp.text}")
                return
        except Exception as e:
            print(f"Network error during chat creation: {e}")
            raise
        
        chat_data = resp.json()
        chat_id = chat_data["id"]
        print(f"Chat Created: {chat_id}")

        # 2. Open Control Plane (WebSocket)
        print(f"\n[2] Connecting to Control Plane: {WS_URL}/control/{chat_id}")
        ws_uri = f"{WS_URL}/control/{chat_id}?token={token}"
        
        async with websockets.connect(ws_uri) as ws:
            print("WebSocket Connected.")

            async def listen_ws():
                try:
                    async for message in ws:
                        data = json.loads(message)
                        if data.get("type") == "stream_init":
                            print(f"\n[AI] Initializing Stream: {data['stream_id']}")
                            asyncio.create_task(consume_sse(data["url"], headers))
                        elif data.get("type") == "typing":
                            print(f"[UI] AI is {data['status']}...")
                        elif data.get("type") == "ping_check":
                            await ws.send(json.dumps({"type": "pong"}))
                except Exception as e:
                    print(f"WS Listener Error: {e}")

            async def consume_sse(url, headers):
                # Fix: Recommendation Engine is usually on port 8001 in our tests
                base = BASE_URL.replace("/api/v1", "")
                full_url = f"{base}{url}"
                print(f"Consuming SSE: {full_url}")
                async with httpx.AsyncClient(headers=headers, timeout=None) as sse_client:
                    async with sse_client.stream("GET", full_url) as response:
                        print("[AI Stream Start]")
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                try:
                                    data = json.loads(line[6:])
                                    event = data.get("event")
                                    payload = data.get("data")
                                    
                                    if event == "token":
                                        print(payload.get("content", ""), end="", flush=True)
                                    elif event == "status":
                                        print(f"\n[Status] {payload}")
                                    elif event == "done":
                                        print("\n[AI Stream End]")
                                        if payload and payload.get("recommendations"):
                                            print(f"Recommendations: {len(payload['recommendations'])} items found.")
                                except Exception as e:
                                    # print(f"Parse Error: {e}")
                                    pass

            async def keyboard_listener():
                import msvcrt
                while True:
                    if msvcrt.kbhit():
                        key = msvcrt.getch()
                        if key.lower() == b'k':
                            await ws.send(json.dumps({"type": "interrupt"}))
                            print("\n[SIGNAL] Interrupt Sent (k pressed)!")
                    await asyncio.sleep(0.1)

            # Start background listeners
            listener_task = asyncio.create_task(listen_ws())
            kb_task = asyncio.create_task(keyboard_listener())

            try:
                print("\n--- Chat Started ---")
                print("Type your message and press Enter.")
                print("Hotkeys: Press 'k' at ANY TIME to INTERRUPT the AI.")
                print("Special: type 'exit' to quit.")

                while True:
                    user_input = await asyncio.get_event_loop().run_in_executor(None, input, "You: ")
                    
                    if user_input.lower() == 'exit':
                        break
                    
                    if user_input.lower() == 'interrupt' or user_input.lower() == 'k':
                        await ws.send(json.dumps({"type": "interrupt"}))
                        print("[Sent Interrupt]")
                        continue

                    # Send via WebSocket (Hybrid flow)
                    await ws.send(json.dumps({
                        "type": "message",
                        "content": user_input,
                        "mode": "chat"
                    }))
                    
            finally:
                listener_task.cancel()
                kb_task.cancel()
                print("\nTest Finished.")

if __name__ == "__main__":
    import traceback
    try:
        asyncio.run(test_chat_flow())
    except KeyboardInterrupt:
        pass
    except Exception:
        print("\n--- FATAL ERROR ---")
        traceback.print_exc()
