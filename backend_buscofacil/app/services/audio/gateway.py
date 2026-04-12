import os
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import json
import random

class VoiceGatewayManager:
    def __init__(self, agent_manager, stt_engine, tts_engine, openai_realtime_manager=None):
        """
        Gateway que maneja la comunicación Full Duplex dual.
        Puede enrutar a Groq Pipeline o a OpenAI Realtime API.
        """
        self.agent_manager = agent_manager
        self.stt_engine = stt_engine
        self.tts_engine = tts_engine
        self.openai_realtime_manager = openai_realtime_manager
        self.active_connections: list[WebSocket] = []
        self.mode = "GROQ"
        self.current_task = None
        
        self.filler_audios = [] # Desactivamos muletillas pregeneradas para evitar acentos gringos incorrectos

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"🔌 Nueva conexión WebSocket de Audio. Modo: {self.mode}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print("🔌 Conexión WebSocket cerrada.")

    async def _send_json(self, websocket: WebSocket, data: dict):
        try:
            await websocket.send_text(json.dumps(data))
        except Exception as e:
            print(f"Error enviando JSON por WS: {e}")

    async def process_audio_stream(self, websocket: WebSocket, authenticated_project_id: str = None, client_name: str = "", client_email: str = "", client_phone: str = "", context_listing_ids: list[str] = None, currency: str = "COP"):
        """Enruta al bucle adecuado según el modo seleccionado."""
        # 1. Logs de validación exigidos para depuración de Frontend
        print(f"------------ INICIO ENRUTAMIENTO WS ------------")
        print(f"🔍 URL QUERY PARAMS RECIBIDOS: {websocket.query_params}")
        print(f"💱 MONEDA LOCAL INYECTADA: {currency}")
        
        project_id = authenticated_project_id or websocket.query_params.get("project_id", "buscofacil")
        
        voice_id = websocket.query_params.get("voice", "")
        
        # Override voice_id with database configuration if it exists
        try:
            from app.db.session import SessionLocal
            from app.db.models import VoiceSettings
            db = SessionLocal()
            try:
                voice_config = db.query(VoiceSettings).filter(VoiceSettings.project_id == project_id).first()
                if voice_config and voice_config.voice_id:
                    voice_id = voice_config.voice_id
                    print(f"✅ Usando voz configurada en BD: {voice_id} para {project_id}")
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️ No se pudo obtener la configuración de voz de la BD: {e}")

        voice_gender = websocket.query_params.get("voice_gender", "").lower()
        print(f"🗣️ CONFIGURACIÓN DE VOZ FRONTEND -> voice_id: '{voice_id}' | voice_gender: '{voice_gender}'")
        
        # El frontend tiene botones explícitos de género. Si el usuario seleccionó uno,
        # este debe tener prioridad sobre la configuración estática de la base de datos.
        if voice_gender == "femenino":
            voice_id = "OUBnvvuqEKdDWtapoJFn"
        elif voice_gender == "masculino":
            voice_id = "ztZBipzb4WQJRDayep3G"
        elif not voice_id:
            voice_id = "OUBnvvuqEKdDWtapoJFn"  # Por defecto voz femenina
                
        print(f"🔊 VOZ FINAL SELECCIONADA PARA TTS: {voice_id}")
        print(f"------------------------------------------------")
                
        if context_listing_ids is None: context_listing_ids = []
        
        if self.mode == "OPENAI_REALTIME" and self.openai_realtime_manager:
            await self.openai_realtime_manager.handle_connection(websocket, project_id, voice_id, client_name, client_email, client_phone, context_listing_ids, currency)
        else:
            await self._process_groq_pipeline(websocket, project_id, voice_id, client_name, client_email, client_phone, context_listing_ids, currency)
            
    async def _process_groq_pipeline(self, websocket: WebSocket, project_id: str, voice_id: str, client_name: str = "", client_email: str = "", client_phone: str = "", context_listing_ids: list[str] = None, currency: str = "COP"):
        import redis.asyncio as aioredis
        from app.services.audio.voice_session import VoiceSession
        
        session_id = f"sess_{id(websocket)}"
        try:
            r = await aioredis.from_url("redis://localhost:6379")
            await r.ping()
        except Exception as e:
            print(f"⚠️ Redis no disponible, barge-in local activado: {e}")
            r = None

        from app.core.prompts import get_agent_instructions
        base_prompt = get_agent_instructions(project_id, "Sol", "Busco Fácil")
        voice_rule = "\n\nREGLA DE FORMATO DE VOZ (CRÍTICO): Prohibido usar listas con viñetas o números. Prohibido usar markdown como asteriscos, guiones o corchetes. Tus respuestas deben ser de máximo 1 a 3 oraciones usando un lenguaje muy coloquial. Si el contexto indica [interrumpido], retoma o confirma el nuevo tema. NUNCA uses la palabra 'inmueble', di 'apartamento', 'casa' o 'propiedad'."
        if client_name: voice_rule += f"\nAtendiendo a: {client_name}. No preguntes su nombre."
        if currency != "COP": voice_rule += f"\nMoneda seleccionada: {currency}. Habla solo en esta moneda."
        
        dynamic_prompt = base_prompt + voice_rule

        voice_session = VoiceSession(session_id, r, websocket, self.agent_manager, self.tts_engine, dynamic_prompt=dynamic_prompt)
        voice_session.current_voice_id = voice_id
        voice_session.project_id = project_id
        voice_session.client_name = client_name
        voice_session.client_email = client_email
        voice_session.client_phone = client_phone
        voice_session.currency = currency
        # Restaurar listing_ids si el frontend los envió (Composer: contextListingIds)
        if context_listing_ids:
            voice_session.context.tool_results['listing_ids'] = [str(lid) for lid in context_listing_ids if lid]

        # Restaurar detail_open_id si el frontend indica que ya hay un detalle abierto (reconexión post-login)
        _detail_open_param = websocket.query_params.get("detail_open_id", "")
        if _detail_open_param:
            voice_session.context.tool_results['detail_open_id'] = _detail_open_param

        # Emular evento inicial de OpenAI Realtime para que el Frontend despierte su UI
        await self._send_json(voice_session.ws, {"type": "session.created"})

        # Leer idioma del frontend para saludo y hints STT.
        # El frontend envía &language=es|en (u otros) en la URL del WebSocket.
        _ui_lang = (websocket.query_params.get("language", "es") or "es").lower()
        # Normalizar: solo "en" o "es" por ahora
        _ui_lang = "en" if _ui_lang.startswith("en") else "es"
        # session_language arranca igual al idioma de la UI para el saludo inicial,
        # pero se actualiza automáticamente con cada transcripción del usuario.
        # Esto permite que si la UI está en español pero el usuario habla inglés,
        # Sol cambie al inglés desde el primer mensaje.
        voice_session.session_language = _ui_lang

        # Saludo Proactivo Inmediato — se omite si es reconexión post-login (rehydrating=1).
        # El frontend enviará conversation.item.create que disparará un saludo inteligente de retoma.
        _has_rehydration = websocket.query_params.get("rehydrating", "0") == "1"
        if not _has_rehydration:
            try:
                nombre = client_name.split(' ')[0] if client_name and '@' not in client_name else ''
                agent_name = "Sol, " if project_id == "buscofacil" else ""
                if _ui_lang == "en":
                    greeting_text = (f"Hello {nombre}, I'm {agent_name}your virtual real estate assistant at Busco Fácil. How can I help you today?"
                                     if nombre else
                                     f"Hello, I'm {agent_name}your virtual real estate assistant at Busco Fácil. How can I help you today?")
                else:
                    greeting_text = (f"Hola {nombre}, soy {agent_name}tu asesor virtual de Busco Fácil. ¿En qué te puedo ayudar hoy?"
                                     if nombre else
                                     f"Hola, soy {agent_name}tu asesor virtual de Busco Fácil. ¿En qué te puedo ayudar hoy?")
                voice_session.context.add_turn('assistant', greeting_text)
                await self._send_json(voice_session.ws, {"type": "response.created"})
                await voice_session.tts_chunk(greeting_text)
                await voice_session.tts_queue.put("[TURN_DONE]")
                print(f"👋 Saludo en '{_ui_lang}': {greeting_text[:80]}")
            except Exception as e:
                print(f"Error en saludo directo: {e}")

        redis_task = None
        if r:
            pubsub = r.pubsub()
            await pubsub.subscribe(f'voice:interrupt:{session_id}')
            async def listen_redis():
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        await voice_session.handle_interruption()
            redis_task = asyncio.create_task(listen_redis())

        audio_buffer = bytearray()
        has_useful_audio = False
        # PRE-BUFFER: audio circular grabado mientras Sol habla.
        # Cuando llega barge-in se inyecta al inicio del próximo commit,
        # recuperando la parte de la frase del usuario que se solapó con Sol.
        # 0.5s × 24000Hz × 2 bytes = 24000 bytes
        # Mantenerlo corto: 1.5s capturaba demasiado eco de Sol → Whisper transcribía basura.
        PRE_BUFFER_MAX = 24000
        pre_buffer = bytearray()

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    print("🚪 Desconexión nativa del socket detectada desde el frontend.")
                    break

                if "text" in message:
                    text_data = message["text"]
                    try:
                        import base64
                        import io
                        import wave
                        import math
                        import struct
                        from app.services.audio.vad import is_human_speech

                        data = json.loads(text_data)
                        if data.get("type") == "input_audio_buffer.append":
                            audio_b64 = data.get("audio", "")
                            if not audio_b64:
                                continue
                            raw_pcm = base64.b64decode(audio_b64)

                            if getattr(voice_session, 'is_audio_playing', False) or getattr(voice_session, 'post_audio_buffer_active', False):
                                # Sol hablando: no acumular en audio_buffer principal,
                                # pero sí en pre_buffer circular para recuperar barge-in.
                                pre_buffer.extend(raw_pcm)
                                if len(pre_buffer) > PRE_BUFFER_MAX:
                                    del pre_buffer[:len(pre_buffer) - PRE_BUFFER_MAX]
                                continue

                            # Acumular para transcripción final
                            audio_buffer.extend(raw_pcm)
                            has_useful_audio = True

                        elif data.get("type") == "conversation.item.create":
                            # Rehidratación post-login: el frontend inyecta el resumen de
                            # la conversación previa para que Sol retome desde el contexto.
                            item = data.get("item", {})
                            rehydration_text = None
                            for c_item in item.get("content", []):
                                if c_item.get("type") == "input_text" and c_item.get("text"):
                                    rehydration_text = c_item["text"]
                                    break
                            if rehydration_text:
                                print(f"📝 [REHYDRATION] Contexto post-login inyectado: {rehydration_text[:120]}")
                                old_task = self.current_task
                                self.current_task = asyncio.create_task(
                                    self._respond_from_text(voice_session, rehydration_text, old_task)
                                )
                            continue

                        elif data.get("type") == "response.create":
                            # OpenAI-compat: ignorar silenciosamente en ruta Groq
                            # (la rehidratación ya la dispara conversation.item.create)
                            continue

                        elif data.get("type") in ("response.cancel", "interruption"):
                            # BARGE-IN INMEDIATO: el usuario habló o clickeó Stop.
                            # Seteamos interrupted=True ANTES de cancelar tasks para que
                            # el TTS corte en el próximo chunk check (~85ms), sin esperar STT.
                            print("🛑 Barge-in recibido — deteniendo AI inmediatamente.")
                            setattr(voice_session, 'interrupted', True)
                            if self.current_task and not self.current_task.done():
                                self.current_task.cancel()
                            if r:
                                await r.publish(f'voice:interrupt:{session_id}', 'barge_in')
                            else:
                                await voice_session.handle_interruption()
                            # Inyectar pre_buffer al audio_buffer para no perder
                            # lo que el usuario dijo mientras Sol hablaba.
                            audio_buffer.clear()
                            if pre_buffer:
                                audio_buffer.extend(pre_buffer)
                                has_useful_audio = True
                                print(f"🔄 Pre-buffer inyectado: {len(pre_buffer)} bytes recuperados tras barge-in")
                            else:
                                has_useful_audio = False
                            pre_buffer.clear()
                            continue
                            
                        elif data.get("type") == "input_audio_buffer.commit":
                            if not has_useful_audio or not audio_buffer:
                                print("⚠️ Backend IGNORÓ el commit porque no se guardaron fragmentos útiles.")
                                # Enviar señal de ready para que el frontend sepa que puede hablar
                                try:
                                    await websocket.send_json({"status": "listening_ready"})
                                except Exception:
                                    pass
                                continue

                            # Nuevo turno del usuario → limpiar flag de interrupción previa.
                            # El eco del saludo puede haber seteado interrupted=True antes de que
                            # el usuario hablara. Al recibir un commit nuevo, ese estado ya no aplica.
                            setattr(voice_session, 'interrupted', False)

                            print("✅ Commit aceptado. Evaluando STT (Semantic Barge-in)...")

                            # Trim: máximo 4 segundos de PCM16@24kHz para STT.
                            # Evita que buffers largos (usuario tardó en responder) confundan a Whisper.
                            # 4s × 24000 Hz × 2 bytes = 192000 bytes
                            MAX_STT_BYTES = 192000
                            pcm_to_send = bytes(audio_buffer[-MAX_STT_BYTES:]) if len(audio_buffer) > MAX_STT_BYTES else bytes(audio_buffer)

                            wav_io = io.BytesIO()
                            with wave.open(wav_io, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
                                wf.writeframes(pcm_to_send)

                            wav_bytes = wav_io.getvalue()
                            audio_buffer.clear()
                            has_useful_audio = False

                            # Pasar el task en curso sin cancelarlo todavía
                            old_task = self.current_task
                            self.current_task = asyncio.create_task(self._transcribe_and_respond(voice_session, wav_bytes, old_task, r, session_id))
                    except Exception as e:
                        print(f"Error procesando JSON de frontend en Groq Pipeline: {e}")
                    continue
                    
                audio_bytes = message.get("bytes")
                if not audio_bytes:
                    continue
                    
                old_task = self.current_task
                self.current_task = asyncio.create_task(self._transcribe_and_respond(voice_session, audio_bytes, old_task, r, session_id, filename="audio.webm"))

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            print(f"❌ Error en flujo WebSocket Groq Pipeline: {e}")
            self.disconnect(websocket)
        finally:
            if voice_session: voice_session.close()
            if redis_task: redis_task.cancel()
            if r: await r.close()

    async def _respond_from_text(self, voice_session, text: str, old_task=None):
        """Responde directamente desde texto sin pasar por STT (rehidratación post-login)."""
        try:
            if old_task and not old_task.done():
                old_task.cancel()
                await voice_session.handle_interruption()
            await voice_session.respond(text)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ [REHYDRATION] Error respondiendo post-login: {e}")

    async def _transcribe_and_respond(self, voice_session, audio_bytes: bytes, old_task=None, r=None, session_id=None, filename: str = "audio.wav"):
        try:
            print(f"🎙️ Procesando {len(audio_bytes)} bytes de audio ({filename}) para streaming.")

            # NO pasar hint de idioma a Whisper: cuando se fuerza un idioma, Whisper
            # traduce el audio al idioma indicado en vez de transcribirlo en el original.
            # Ej: usuario habla inglés + hint "es" → Whisper devuelve texto en español.
            # Se deja auto-detección siempre; el filtro de alucinaciones opera por duración.
            try:
                transcription = await asyncio.to_thread(self.stt_engine.transcribe_audio, audio_bytes, filename, None)
            except Exception as e:
                print(f"⚠️ Error STT (ignorado): {e}")
                return

            if not transcription or not transcription.strip():
                # Si el audio era suficientemente largo (> 1s), el usuario intentó hablar
                # pero STT filtró una alucinación. Avisar para que repita.
                MIN_SPEECH_BYTES = 48000  # 1s × 24kHz × 2 bytes
                if len(audio_bytes) >= MIN_SPEECH_BYTES and not getattr(voice_session, 'interrupted', False):
                    sl = getattr(voice_session, 'session_language', 'es')
                    retry_msg = "No te escuché bien, ¿puedes repetirlo?" if sl != "en" else "I didn't catch that, could you repeat?"
                    await voice_session.tts_chunk(retry_msg)
                    await voice_session.tts_queue.put("[TURN_DONE]")
                return

            # Actualizar idioma de sesión para futuros hints al STT.
            # Usamos langdetect para detectar el idioma real del usuario (cualquier idioma),
            # no solo ES↔EN. El frontend solo envía `language` para el saludo inicial;
            # a partir del primer mensaje, el backend determina el idioma automáticamente.
            if len(transcription.split()) >= 2:
                try:
                    from langdetect import detect as _ld_voice, DetectorFactory as _DFV
                    _DFV.seed = 0  # determinístico
                    _detected_voice_lang = _ld_voice(transcription)
                    # Mapear código ISO → "es" o "en" (ampliable a otros idiomas)
                    if _detected_voice_lang in ("es", "pt", "ca", "gl"):
                        voice_session.session_language = "es"
                    elif _detected_voice_lang in ("en",):
                        voice_session.session_language = "en"
                    else:
                        # Para cualquier otro idioma, guardar el código directamente
                        # para que el LLM reciba el hint correcto en futuros turnos
                        voice_session.session_language = _detected_voice_lang
                    print(f"🌐 [STT] Idioma detectado: {_detected_voice_lang} → session_language={voice_session.session_language}")
                except Exception as _ld_err:
                    # Fallback por wordset si langdetect falla
                    print(f"⚠️ [langdetect voice] Error: {_ld_err}. Usando wordset fallback.")
                    _en_words = {"i", "you", "is", "are", "the", "a", "and", "want", "find", "looking"}
                    _words = set(transcription.lower().split())
                    if len(_words & _en_words) >= 2:
                        voice_session.session_language = "en"
                    else:
                        voice_session.session_language = "es"

            # --- SEMANTIC BARGE-IN ---
            # Si superó STT, es voz genuina y no ruido/alucinación STT. Interrumpimos IA ahora mismo.
            if old_task and not old_task.done():
                print("🛑 SEMANTIC BARGE-IN: Audio real validado. Interrumpiendo IA activa!")
                old_task.cancel()
                if r:
                    await r.publish(f'voice:interrupt:{session_id}', 'barge_in')
                else:
                    await voice_session.handle_interruption()
            
            print(f"🗣️ Usuario dijo: {transcription}")

            # GUARD: si el usuario ya detuvo la conversación mientras el STT procesaba,
            # descartar esta transcripción — no enviar texto viejo al frontend.
            if getattr(voice_session, 'interrupted', False):
                print("🚫 Transcripción descartada: conversación detenida durante STT.")
                return

            # Emitir eventos nativos de OpenAI para que el frontend dibuje las burbujas de chat
            await self._send_json(voice_session.ws, {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": transcription}]
                }
            })

            await voice_session.respond(transcription)

        except asyncio.CancelledError:
            print("🚫 Transcripción/Generación cancelada por nuevo Turno (Barge-In).")
        except Exception as e:
            print(f"❌ Error procesando turno: {e}")

