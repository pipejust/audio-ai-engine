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
            "echo": os.getenv("ELEVENLABS_VOICE_MALE", "GpnOed0ndzjm6Pc8JALF"), # Felipe (Latino Masculino)
            "alloy": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"), # Latina/Neutral Femenina
            "shimmer": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"),
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
            "echo": os.getenv("ELEVENLABS_VOICE_MALE", "GpnOed0ndzjm6Pc8JALF"),
            "alloy": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"),
            "shimmer": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"),
        }
        target_voice_id = voice_map.get(voice_name, self.voice_id)
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice_id}/stream?output_format=pcm_24000"
        headers = {
            "Accept": "audio/pcm",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        data = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.5}
        }
        
        try:
            import base64
            chars = text
            chars_sent = 0
            
            def create_wav_header(data_size: int) -> bytes:
                import struct
                header = bytearray(44)
                header[0:4] = b'RIFF'
                header[4:8] = struct.pack('<I', 36 + data_size)
                header[8:12] = b'WAVE'
                header[12:16] = b'fmt '
                header[16:20] = struct.pack('<I', 16)
                header[20:22] = struct.pack('<H', 1) # PCM
                header[22:24] = struct.pack('<H', 1)   # Mono
                header[24:28] = struct.pack('<I', 24000) # Sample rate
                header[28:32] = struct.pack('<I', 24000 * 2) # Byte rate
                header[32:34] = struct.pack('<H', 2) # Block align
                header[34:36] = struct.pack('<H', 16) # Bits per sample
                header[36:40] = b'data'
                header[40:44] = struct.pack('<I', data_size)
                return bytes(header)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.content.iter_chunked(4096):
                        # Verificar si hubo barge-in antes de enviar cada chunk
                        if redis and await redis.exists(f'voice:interrupt:{session_id}'):
                            print("🛑 TTS abortado por interrupción del usuario.")
                            break
                        if chunk:
                            # Inyectar cabecera WAV al vuelo para que el Frontend (React Native 'decodeAudioData') pueda leerlo como archivo independiente sin fallar
                            wav_chunk = create_wav_header(len(chunk)) + chunk
                            b64_chunk = base64.b64encode(wav_chunk).decode("utf-8")
                            await ws.send_json({"type": "response.audio.delta", "delta": b64_chunk})
                            
                            # Mantener sincronizado el Backend con la reproducción de audio (Half-Duplex sync)
                            chunk_seconds = len(chunk) / 48000.0
                            
                            # Sincronizar el texto (UI) para que salga a la misma velocidad que el audio (15 caracteres/seg)
                            chars_to_send = int(chunk_seconds * 17) # 17 chars/sec avg
                            if chars_to_send < 1: chars_to_send = 1
                            if chars_sent < len(chars):
                                delta_text = chars[chars_sent : chars_sent + chars_to_send]
                                if delta_text:
                                    try:
                                        await ws.send_json({"type": "response.audio_transcript.delta", "delta": delta_text})
                                    except Exception: pass
                                chars_sent += chars_to_send
                            
                            # Dormimos ligeramente menos que el tiempo real para mantener el streaming fluyendo sin pausas
                            await asyncio.sleep(chunk_seconds * 0.8)
                    
                    # Vaciar cualquier caracter faltante al final
                    if chars_sent < len(chars):
                        try:
                            await ws.send_json({"type": "response.audio_transcript.delta", "delta": chars[chars_sent:]})
                        except Exception: pass

                    # Sellar oficialmente la caja de texto en la vista UI para demarcar el final completo
                    try:
                        await ws.send_json({"type": "response.audio_transcript.done"})
                    except Exception: pass
                        
        except asyncio.CancelledError:
            # Barge-in canceló la tarea — silenciar cliente cerrando el transcript de urgencia
            try:
                await ws.send_json({'type': 'response.audio_transcript.done'})
            except Exception: pass
            raise
        except Exception as e:
            print(f"❌ Error en TTS Streaming HTTP: {e}")
