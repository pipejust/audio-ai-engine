import asyncio
import websockets
import json
import os

def get_api_key():
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=")[1].strip().strip('"').strip("'")
    except:
        pass
    return os.getenv("OPENAI_API_KEY")

async def test_realtime():
    api_key = get_api_key()
    if not api_key:
        print("No API Key")
        return
        
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(url, extra_headers=headers) as ws:
            print("Connected to OpenAI.")
            msg = await ws.recv()
            print("Handshake:", json.loads(msg).get("type"))
            
            setup_event = {
                "type": "session.update",
                "session": {
                    "instructions": "Test instructions",
                    "voice": "alloy",
                    "turn_detection": None,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "temperature": 0.7,
                }
            }
            await ws.send(json.dumps(setup_event))
            print("Sent session.update")
            
            greeting_event = {
                "type": "response.create",
                "response": {
                    "instructions": "Say hello!"
                }
            }
            await ws.send(json.dumps(greeting_event))
            print("Sent response.create")
            
            for _ in range(10):
                resp = await ws.recv()
                data = json.loads(resp)
                print("Received:", data.get("type"))
                if data.get("type") == "error":
                    print("ERROR DETAILS:", json.dumps(data, indent=2))
                    break
    except Exception as e:
        print("Exception:", e)

asyncio.run(test_realtime())
