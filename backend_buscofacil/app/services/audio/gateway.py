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
        self.mode = os.getenv("VOICE_ENGINE_MODE", "GROQ")
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
        project_id = authenticated_project_id or websocket.query_params.get("project_id", "default")
        
        voice_id = websocket.query_params.get("voice", "")
        if not voice_id:
            voice_gender = websocket.query_params.get("voice_gender", "").lower()
            if voice_gender == "femenino":
                voice_id = "shimmer"
            elif voice_gender == "masculino":
                voice_id = "echo"
            else:
                voice_id = "alloy"
                
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
        except Exception as e:
            print(f"⚠️ Redis no disponible, barge-in degradado: {e}")
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

        # Saludo Proactivo Inmediato
        try:
            greeting_result = self.agent_manager.process_query("system_greeting_trigger", project_id=project_id)
            text_response = greeting_result.get("response", "Hola.")
            print(f"🤖 Agente saluda: {text_response}")
            await self._send_json(websocket, {"status": "speaking", "response": text_response})
            audio_response = self.tts_engine.generate_audio(text_response, voice_id)
            if audio_response:
                await websocket.send_bytes(audio_response)
            await self._send_json(websocket, {"status": "listening"})
        except Exception as e:
            print(f"Error en saludo: {e}")

        redis_task = None
        if r:
            pubsub = r.pubsub()
            await pubsub.subscribe(f'voice:interrupt:{session_id}')
            async def listen_redis():
                async for message in pubsub.listen():
                    if message['type'] == 'message':
                        await voice_session.handle_interruption()
            redis_task = asyncio.create_task(listen_redis())

        try:
            while True:
                message = await websocket.receive()
                if "text" in message:
                    text_data = message["text"]
                    if "interruption" in text_data:
                        print("🛑 Interrupción detectada desde frontend. Cancelando generación actual.")
                        if self.current_task and not self.current_task.done():
                            self.current_task.cancel()
                        if r:
                            await r.publish(f'voice:interrupt:{session_id}', 'barge_in')
                        else:
                            await voice_session.handle_interruption()
                    continue
                    
                audio_bytes = message.get("bytes")
                if not audio_bytes:
                    continue
                    
                if self.current_task and not self.current_task.done():
                    self.current_task.cancel()
                    
                self.current_task = asyncio.create_task(self._transcribe_and_respond(voice_session, audio_bytes))

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            print(f"❌ Error en flujo WebSocket Groq Pipeline: {e}")
            self.disconnect(websocket)
        finally:
            if redis_task: redis_task.cancel()
            if r: await r.close()

    async def _transcribe_and_respond(self, voice_session, audio_bytes: bytes):
        try:
            print(f"🎙️ Procesando {len(audio_bytes)} bytes de audio para streaming.")
            await self._send_json(voice_session.ws, {"status": "transcribing"})
            
            try:
                transcription = await asyncio.to_thread(self.stt_engine.transcribe_audio, audio_bytes)
            except Exception as e:
                print(f"⚠️ Error STT (ignorado): {e}")
                await self._send_json(voice_session.ws, {"status": "listening"})
                return

            if not transcription or not transcription.strip():
                await self._send_json(voice_session.ws, {"status": "listening"})
                return
            
            print(f"🗣️ Usuario dijo: {transcription}")
            await self._send_json(voice_session.ws, {"status": "reasoning", "transcription": transcription})
            
            await voice_session.respond(transcription)

        except asyncio.CancelledError:
            print("🚫 Transcripción/Generación cancelada por Barge-In local.")
            await self._send_json(voice_session.ws, {"status": "listening"})
        except Exception as e:
            print(f"❌ Error procesando turno: {e}")
            await self._send_json(voice_session.ws, {"status": "listening"})

