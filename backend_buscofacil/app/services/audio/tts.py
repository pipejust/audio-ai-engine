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
                    
                    full_pcm = bytearray()
                    async for chunk in resp.content.iter_chunked(4096):
                        # Si hay un Barge-in mientras decodifica, abortamos rápido.
                        if redis and await redis.exists(f'voice:interrupt:{session_id}'):
                            print("🛑 TTS abortado por interrupción del usuario (Descarga).")
                            return
                        if chunk:
                            full_pcm.extend(chunk)
                            
                    if not full_pcm:
                        return
                        
                    # Pre-empacar TODO el audio como un solo archivo WAV estático para React Native (Fluidez cristalina, cero lluvia/stutter)
                    wav_full = create_wav_header(len(full_pcm)) + full_pcm
                    b64_full = base64.b64encode(wav_full).decode("utf-8")
                    
                    try:
                        await ws.send_json({"type": "response.audio.delta", "delta": b64_full})
                    except Exception as e:
                        print(f"⚠️ WS cerrado antes de mandar audio: {e}")
                        return
                        
                    # Simulamos el tipeo en vivo del transcript sincronizado con la duración total
                    total_audio_seconds = len(full_pcm) / 48000.0
                    chunk_duration = 0.05
                    num_ticks = int(total_audio_seconds / chunk_duration)
                    if num_ticks == 0: num_ticks = 1
                    chars_per_tick = max(1, int(len(chars) / num_ticks))
                    
                    for _ in range(num_ticks):
                        if redis and await redis.exists(f'voice:interrupt:{session_id}'):
                            print("🛑 Tipeo abortado por Barge-In.")
                            break
                        if chars_sent < len(chars):
                            delta_text = chars[chars_sent : chars_sent + chars_per_tick]
                            try:
                                await ws.send_json({"type": "response.audio_transcript.delta", "delta": delta_text})
                            except Exception:
                                return # WS cerrado abruptamente
                            chars_sent += chars_per_tick
                        await asyncio.sleep(chunk_duration)
                    
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
