import asyncio
import websockets

async def test_ws():
    uri = "wss://moshwasi-audio-api.onrender.com/voice/stream?token=notoken&voice=echo"
    try:
        async with websockets.connect(uri) as websocket:
            print("Successfully connected to WebSocket!")
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                print(f"Received: {msg}")
            except asyncio.TimeoutError:
                print("No message received within 5 seconds, but connection works.")
    except Exception as e:
        print(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
