import os
import requests
from dotenv import load_dotenv

load_dotenv()

class TTSEngine:
    def __init__(self):
        """Inicializa el motor de síntesis de voz con ElevenLabs."""
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        # Voice ID configurable desde el entorno o usa predeterminado
        self.voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") 
        print(f"🎙️ Motor TTS ElevenLabs cargado (Voz ID: {self.voice_id}).")

    def generate_audio(self, text: str, voice_name: str = "alloy") -> bytes:
        """
        Convierte texto a audio binario (MP3) usando ElevenLabs.
        voice_name mapea de OpenAI ('echo', 'alloy', etc) a IDs de ElevenLabs.
        """
        if not text or not self.api_key:
            return None
            
        # Mapeo de voces del frontend a IDs específicos de ElevenLabs
        voice_map = {
            "echo": os.getenv("ELEVENLABS_VOICE_ID", "GpnOed0ndzjm6Pc8JALF"), # Felipe (Latino Masculino)
            "alloy": "EXAVITQu4vr4xnSDxMaL", # Bella (Latina/Neutral Femenina)
            "shimmer": "EXAVITQu4vr4xnSDxMaL",
        }
        
        target_voice_id = voice_map.get(voice_name, self.voice_id)
            
        print(f"🔊 Generando audio en ElevenLabs (Voz: {voice_name}) para: '{text}'...")
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice_id}?output_format=mp3_44100_128"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }

        try:
            response = requests.post(url, json=data, headers=headers)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"❌ Error en TTS ElevenLabs: {e}")
            return None

    async def synthesize_and_stream(self, text: str, ws, session_id: str, redis, voice_name: str = "alloy"):
        """TTS Streaming por chunks con soporte de Barge-In. (Sustituto Async de Kokoro según especificaciones)."""
        import aiohttp
        import asyncio
        if not text or not self.api_key:
            return
            
        voice_map = {
            "echo": os.getenv("ELEVENLABS_VOICE_ID", "GpnOed0ndzjm6Pc8JALF"),
            "alloy": "EXAVITQu4vr4xnSDxMaL",
            "shimmer": "EXAVITQu4vr4xnSDxMaL",
        }
        target_voice_id = voice_map.get(voice_name, self.voice_id)
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice_id}/stream?output_format=mp3_44100_128"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.content.iter_chunked(4096):
                        # Verificar si hubo barge-in antes de enviar cada chunk
                        if redis and await redis.exists(f'voice:interrupt:{session_id}'):
                            print("🛑 TTS abortado por interrupción del usuario.")
                            break
                        if chunk:
                            await ws.send_bytes(chunk)
                            await asyncio.sleep(0.01) # Pequeño sleep para evitar saturar el WebSocket
        except asyncio.CancelledError:
            # Barge-in canceló la tarea — silenciar cliente
            await ws.send_json({'type': 'tts_stop'})
            raise
        except Exception as e:
            print(f"❌ Error en TTS Streaming HTTP: {e}")
