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
    
    greeting_event = {
        "type": "conversation.item.create",
        "item": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "El usuario acaba de abrir la aplicación. Saluda."
                }
            ]
        }
    }
    
    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            first_msg = await ws.recv()
            print("Handshake:", json.loads(first_msg).get("type"))
            
            await ws.send(json.dumps(setup_event))
            print("Session update sent.")
            
            await ws.send(json.dumps(greeting_event))
            await ws.send(json.dumps({"type": "response.create"}))
            print("Greeting and response sent.")
            
            for _ in range(5):
                resp = await ws.recv()
                print("Response:", json.loads(resp).get("type"))
                
    except Exception as e:
        print("Exception:", e)

if __name__ == "__main__":
    asyncio.run(test())
