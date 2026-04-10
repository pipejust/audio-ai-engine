import asyncio
import websockets

async def test():
    uri = "wss://moshwasi-audio-api.onrender.com/voice/stream?project_id=buscofacil"
    try:
        async with websockets.connect(uri, extra_headers={"Origin": "https://audioaiproject.vercel.app"}) as ws:
            print("Connected!")
    except Exception as e:
        print(f"Failed: {e}")

asyncio.run(test())
