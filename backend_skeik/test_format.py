import os
import requests
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path)

api_key = os.getenv("ELEVENLABS_API_KEY")
voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=pcm_24000"
headers = {"Accept": "audio/pcm", "Content-Type": "application/json", "xi-api-key": api_key}
data = {
    "text": "Hola, esto es una prueba.",
    "model_id": "eleven_turbo_v2_5",
}

print("Pidiendo a ElevenLabs...")
res = requests.post(url, json=data, headers=headers)
print("Status:", res.status_code)
print("Content-Type:", res.headers.get("Content-Type"))
if res.status_code == 200:
    content = res.content
    print("Length in bytes:", len(content))
    print("First 20 bytes:", content[:20])
else:
    print("Error:", res.text)
