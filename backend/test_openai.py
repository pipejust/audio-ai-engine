import asyncio
import os
import json
import websockets
from app.core.prompts import get_agent_instructions, get_agent_tools

async def test():
    api_key = os.getenv("OPENAI_API_KEY")
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview-2024-12-17"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    tools = get_agent_tools("buscofacil")
    instructions = get_agent_instructions("buscofacil", "Sol", "Busco Fácil")
    
    setup_event = {
        "type": "session.update",
        "session": {
            "instructions": instructions,
            "voice": "alloy",
            "turn_detection": None,
            "input_audio_transcription": {
                "model": "whisper-1"
            },
            "temperature": 0.7,
            "tools": tools,
            "tool_choice": "auto"
        }
    }
    
    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            first_msg = await ws.recv()
            print("Handshake:", first_msg)
            
            await ws.send(json.dumps(setup_event))
            print("Session update sent.")
            
            while True:
                resp = await ws.recv()
                print("Response:", resp)
                # Break to avoid infinite loop for test
                if "error" in resp:
                    break
    except Exception as e:
        print("Exception:", e)

asyncio.run(test())
