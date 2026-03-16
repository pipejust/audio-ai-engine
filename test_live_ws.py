import asyncio
import websockets
import json
import httpx

async def main():
    # 1. Get Token
    print("Obtaining token...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/auth/token",
            data={"username": "admin_buscofacil", "password": "secreto123"}
        )
        token = resp.json()["access_token"]
        
    print(f"Token obtained. Connecting to WS...")
    # 2. Connect WS
    uri = f"ws://localhost:8000/voice/stream?token={token}&voice=alloy"
    try:
        async with websockets.connect(uri) as ws:
            print("Connected! Waiting for messages...")
            while True:
                msg = await ws.recv()
                try:
                    data = json.loads(msg)
                    print(f"Server -> {data}")
                except Exception:
                    print(f"Server -> [Binary Audio Data: {len(msg)} bytes]")
    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed by server: {e.code} - {e.reason}")
    except Exception as e:
        print(f"WS Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
