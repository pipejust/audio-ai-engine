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
        
        project_id = authenticated_project_id or websocket.query_params.get("project_id", "default")
        
        voice_id = websocket.query_params.get("voice", "")
        voice_gender = websocket.query_params.get("voice_gender", "").lower()
        print(f"🗣️ CONFIGURACIÓN DE VOZ FRONTEND -> voice_id: '{voice_id}' | voice_gender: '{voice_gender}'")
        
        if not voice_id:
            if voice_gender == "femenino":
                voice_id = "shimmer"
            elif voice_gender == "masculino":
                voice_id = "echo"
            else:
                voice_id = "alloy"  # Por defecto si no manda nada
                
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

        # Emular evento inicial de OpenAI Realtime para que el Frontend despierte su UI
        await self._send_json(voice_session.ws, {"type": "session.created"})

        # Saludo Proactivo Inmediato (Ultra-Rápido sin pasar por OpenAI)
        try:
            nombre = client_name.split(' ')[0] if client_name and '@' not in client_name else ''
            greeting_text = f"Hola {nombre}, soy tu asesor virtual de Busco Fácil. ¿En qué te puedo ayudar hoy?" if nombre else "Hola, soy tu asesor virtual de Busco Fácil. ¿En qué te puedo ayudar hoy?"
            
            # 1. Anexar al contexto limpio sin gastar tokens
            voice_session.context.add_turn('assistant', greeting_text)
            
            # 2. Iniciar burbuja en el Frontend
            await self._send_json(voice_session.ws, {"type": "response.created"})
            
            # 3. Lanzar ElevenLabs directo (saltando LLM Chain)
            self.current_task = asyncio.create_task(voice_session.tts_chunk(greeting_text))
            
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
        
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    print("🚪 Desconexión nativa del socket detectada desde el frontend.")
                    break
                    
                if "text" in message:
                    text_data = message["text"]
                    if "interruption" in text_data:
                        # Ignorar el inestable "interruption: true" del frontend que detectaba cualquier ruido.
                        # Ahora mandamos a evaluar todo al super-algoritmo matemático del Backend.
                        continue
                        
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
                            if audio_b64:
                                raw_pcm = base64.b64decode(audio_b64)
                                
                                # Acumular para transcripción final
                                audio_buffer.extend(raw_pcm)
                                has_useful_audio = True
                                
                        elif data.get("type") == "input_audio_buffer.commit":
                            if not has_useful_audio or not audio_buffer:
                                print("⚠️ Backend IGNORÓ el commit porque no se guardaron fragmentos útiles.")
                                continue
                            
                            print("✅ Commit aceptado. Evaluando STT (Semantic Barge-in)...")
                            
                            wav_io = io.BytesIO()
                            with wave.open(wav_io, 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
                                wf.writeframes(audio_buffer)
                            
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
            if redis_task: redis_task.cancel()
            if r: await r.close()

    async def _transcribe_and_respond(self, voice_session, audio_bytes: bytes, old_task=None, r=None, session_id=None, filename: str = "audio.wav"):
        try:
            print(f"🎙️ Procesando {len(audio_bytes)} bytes de audio ({filename}) para streaming.")
            
            try:
                transcription = await asyncio.to_thread(self.stt_engine.transcribe_audio, audio_bytes, filename)
            except Exception as e:
                print(f"⚠️ Error STT (ignorado): {e}")
                return

            if not transcription or not transcription.strip():
                return
                
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
            
            # Emitir eventos nativos de OpenAI para que el frontend dibuje las burbujas de chat
            await self._send_json(voice_session.ws, {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": transcription}]
                }
            })
            await self._send_json(voice_session.ws, {"type": "response.created"})
            
            await voice_session.respond(transcription)

        except asyncio.CancelledError:
            print("🚫 Transcripción/Generación cancelada por nuevo Turno (Barge-In).")
        except Exception as e:
            print(f"❌ Error procesando turno: {e}")

