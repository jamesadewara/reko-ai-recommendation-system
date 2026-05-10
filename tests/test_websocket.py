import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8001/api/v1/ws/chat/test_chat_id?token=mock_token"
    
    # Please note: you need to have a running server and valid chat_id/token.
    # This is a client skeleton.
    try:
        async with websockets.connect(uri) as websocket:
            message = {"message": "suggest a good movie", "type": "text"}
            await websocket.send(json.dumps(message))
            print(f"> Sent: {message}")

            while True:
                response = await websocket.recv()
                data = json.loads(response)
                print(f"< Received: {data['type']}")
                if data['type'] == 'typing':
                    print("  Status:", data.get('status'))
                elif data['type'] == 'reasoning':
                    print("  Reasoning:", data.get('content'))
                elif data['type'] == 'content':
                    print("  Content:", data.get('content'))
                elif data['type'] == 'done':
                    print("  Done processing.")
                    break
    except websockets.exceptions.ConnectionClosedError:
        print("Connection closed. Make sure the server is running and authentication is valid.")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
