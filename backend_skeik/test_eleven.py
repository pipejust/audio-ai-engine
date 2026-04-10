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
    "text": "Hola, probando audio PCM.",
    "model_id": "eleven_turbo_v2_5",
}

print("Pidiendo a:", url)
res = requests.post(url, json=data, headers=headers)
print("Status:", res.status_code)

if res.status_code == 200:
    print("Length in bytes:", len(res.content))
    with open("test.pcm", "wb") as f:
        f.write(res.content)
else:
    print("Error:", res.text)
