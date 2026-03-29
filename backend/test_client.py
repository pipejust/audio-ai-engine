import asyncio
import websockets
import json

async def run_client():
    uri = "ws://127.0.0.1:8000/ws/realtime/buscofacil?context_listing_ids="
    try:
        async with websockets.connect(uri) as ws:
            print("Connected to local backend")
            
            # Escuchar mensajes entrantes (Iniciando motor Realtime...)
            msg = await ws.recv()
            print("Server ->", msg)
            
            for _ in range(3):
                msg = await ws.recv()
                # Check if it's text or binary
                if isinstance(msg, bytes):
                    print("Server sent AUDIO BYTES:", len(msg), "bytes")
                else:
                    print("Server ->", msg)
            
            # Ahora simular envío de voz
            print("Client sending dummy webm bytes...")
            await ws.send(b'dummy_webm_bytes_1234')
            
            for _ in range(5):
                msg = await ws.recv()
                if isinstance(msg, bytes):
                    print("Server sent AUDIO BYTES:", len(msg), "bytes")
                else:
                    print("Server ->", msg)

    except Exception as e:
        print("Frontend WebSocket died:", e)

if __name__ == "__main__":
    asyncio.run(run_client())
