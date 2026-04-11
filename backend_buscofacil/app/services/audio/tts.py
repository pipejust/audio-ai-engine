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
            "echo": os.getenv("ELEVENLABS_VOICE_MALE", "pNInz6obpgDQGcFmaJcg"), # Adam (Masculino)
            "alloy": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"), # Latina/Neutral Femenina
            "shimmer": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"),
        }
        
        if voice_name not in voice_map and len(voice_name) > 10:
            target_voice_id = voice_name
        else:
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

    async def synthesize_and_stream(self, text: str, voice_session, voice_name: str = "alloy"):
        """TTS Streaming por chunks con soporte de Barge-In. (Sustituto Async de Kokoro según especificaciones)."""
        import aiohttp
        import asyncio
        if not text or not self.api_key:
            return
            
        ws = voice_session.ws
        session_id = voice_session.id
        redis = voice_session.redis

        voice_map = {
            "echo": os.getenv("ELEVENLABS_VOICE_MALE", "cjVigY5qzO86Hvf0A3Tq"),
            "alloy": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"),
            "shimmer": os.getenv("ELEVENLABS_VOICE_FEMALE", "VmejBeYhbrcTPwDniox7"),
        }
        
        # Si voice_name parece un ID directo de ElevenLabs (ej. 21m00Tcm4...), lo usamos directo
        if voice_name not in voice_map and len(voice_name) > 10:
            target_voice_id = voice_name
        else:
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
            import asyncio
            chars = text

            def create_wav_header(data_size: int) -> bytes:
                import struct
                header = bytearray(44)
                header[0:4] = b'RIFF'
                header[4:8] = struct.pack('<I', 36 + data_size)
                header[8:12] = b'WAVE'
                header[12:16] = b'fmt '
                header[16:20] = struct.pack('<I', 16)
                header[20:22] = struct.pack('<H', 1)    # PCM
                header[22:24] = struct.pack('<H', 1)    # Mono
                header[24:28] = struct.pack('<I', 24000) # Sample rate
                header[28:32] = struct.pack('<I', 24000 * 2) # Byte rate
                header[32:34] = struct.pack('<H', 2)    # Block align
                header[34:36] = struct.pack('<H', 16)   # Bits per sample
                header[36:40] = b'data'
                header[40:44] = struct.pack('<I', data_size)
                return bytes(header)

            # TTS FIRST-BYTE STREAMING: enviar chunks de audio cada ~500ms en vez de
            # esperar la descarga completa. El usuario escucha la primera sílaba en ~300ms.
            # Tamaño de chunk: 24000 muestras/s × 2 bytes × 0.5s = 24000 bytes
            CHUNK_BYTES = 24000  # 500ms de audio PCM16 @ 24kHz

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, headers=headers) as resp:
                    resp.raise_for_status()

                    pcm_buffer = bytearray()
                    full_pcm = bytearray()
                    first_chunk_sent = False

                    async for raw_chunk in resp.content.iter_chunked(4096):
                        if getattr(voice_session, 'interrupted', False):
                            print("🛑 TTS abortado por interrupción (descarga).")
                            return
                        if not raw_chunk:
                            continue

                        pcm_buffer.extend(raw_chunk)
                        full_pcm.extend(raw_chunk)

                        # Enviar en cuanto tengamos 500ms de audio acumulado
                        while len(pcm_buffer) >= CHUNK_BYTES:
                            if getattr(voice_session, 'interrupted', False):
                                return
                            chunk_pcm = bytes(pcm_buffer[:CHUNK_BYTES])
                            pcm_buffer = pcm_buffer[CHUNK_BYTES:]
                            wav_chunk = create_wav_header(len(chunk_pcm)) + chunk_pcm
                            b64_chunk = base64.b64encode(wav_chunk).decode("utf-8")
                            if not first_chunk_sent:
                                # Activar mute del micrófono en el primer chunk
                                setattr(voice_session, 'is_audio_playing', True)
                                first_chunk_sent = True
                            try:
                                await ws.send_json({"type": "response.audio.delta", "delta": b64_chunk})
                            except Exception as e:
                                print(f"⚠️ WS cerrado enviando chunk: {e}")
                                return

                    # Enviar resto (tail) si no fue interrumpido
                    if pcm_buffer and not getattr(voice_session, 'interrupted', False):
                        wav_tail = create_wav_header(len(pcm_buffer)) + bytes(pcm_buffer)
                        b64_tail = base64.b64encode(wav_tail).decode("utf-8")
                        if not first_chunk_sent:
                            setattr(voice_session, 'is_audio_playing', True)
                            first_chunk_sent = True
                        try:
                            await ws.send_json({"type": "response.audio.delta", "delta": b64_tail})
                        except Exception as e:
                            print(f"⚠️ WS cerrado enviando tail: {e}")
                            return

                    if not full_pcm or not first_chunk_sent:
                        return

                    if getattr(voice_session, 'interrupted', False):
                        print("🛑 TTS abortado justo antes del tipeo.")
                        setattr(voice_session, 'is_audio_playing', False)
                        return

                    # Iniciar tipeo sincronizado con audio total
                    await self._simulate_typing(chars, len(full_pcm), ws, session_id, redis, voice_session)

                    # POST-TTS COOLDOWN: mantener el micrófono muteado 400ms después
                    # de que el audio termina, para absorber el eco del speaker en la sala.
                    # Usamos call_later para no bloquear el event loop con await sleep.
                    if not getattr(voice_session, 'interrupted', False):
                        loop = asyncio.get_event_loop()
                        loop.call_later(0.4, lambda: setattr(voice_session, 'post_audio_buffer_active', False))
                        setattr(voice_session, 'post_audio_buffer_active', True)
                    setattr(voice_session, 'is_audio_playing', False)
                        
        except asyncio.CancelledError:
            try: await ws.send_json({'type': 'response.audio_transcript.done'})
            except Exception: pass
            raise
        except Exception as e:
            print(f"❌ Error en TTS Streaming HTTP: {e}")

    async def _simulate_typing(self, chars, pcm_len, ws, session_id, redis, voice_session):
        import asyncio
        chars = " " + chars
        total_audio_seconds = pcm_len / 48000.0
        chunk_duration = 0.05
        num_ticks = int(total_audio_seconds / chunk_duration)
        if num_ticks == 0: num_ticks = 1
        chars_per_tick = max(1, int(len(chars) / num_ticks))
        chars_sent = 0
        
        try:
            for _ in range(num_ticks):
                if (redis and await redis.exists(f'voice:interrupt:{session_id}')) or getattr(voice_session, 'interrupted', False):
                    print("🛑 Tipeo abortado por Barge-In.")
                    try: await ws.send_json({"type": "response.cancel"})
                    except: pass
                    # Enviar clear para frontend
                    try: await ws.send_json({"type": "response.audio.clear"})
                    except: pass
                    break
                if chars_sent < len(chars):
                    delta_text = chars[chars_sent : chars_sent + chars_per_tick]
                    try: await ws.send_json({"type": "response.audio_transcript.delta", "delta": delta_text})
                    except Exception: return # WS cerrado
                    chars_sent += chars_per_tick
                await asyncio.sleep(chunk_duration)
            
            # Vaciar faltantes
            if chars_sent < len(chars):
                try: await ws.send_json({"type": "response.audio_transcript.delta", "delta": chars[chars_sent:]})
                except Exception: pass
            
        except asyncio.CancelledError:
            raise
        finally:
            setattr(voice_session, 'is_audio_playing', False)
