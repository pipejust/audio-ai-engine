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
        self.mode = os.getenv("VOICE_ENGINE_MODE", "GROQ_PIPELINE")
        self.current_task = None
        
        # Pre-generar muletillas para enmascarar latencia del LLM
        print("⏳ Generando audios de relleno intermedio...")
        self.filler_audios = [
            self.tts_engine.generate_audio("Déjame revisar..."),
            self.tts_engine.generate_audio("Un segundo, estoy buscando..."),
            self.tts_engine.generate_audio("Vale, miraré qué encuentro...")
        ]
        self.filler_audios = [a for a in self.filler_audios if a is not None]

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

    async def process_audio_stream(self, websocket: WebSocket, authenticated_project_id: str = None):
        """Enruta al bucle adecuado según el modo seleccionado."""
        project_id = authenticated_project_id or websocket.query_params.get("project_id", "default")
        voice_id = websocket.query_params.get("voice", "alloy")
        
        if self.mode == "OPENAI_REALTIME" and self.openai_realtime_manager:
            await self.openai_realtime_manager.handle_connection(websocket, project_id, voice_id)
        else:
            await self._process_groq_pipeline(websocket, project_id)
            
    async def _process_groq_pipeline(self, websocket: WebSocket, project_id: str):
        """Bucle original de Groq + Agent + ElevenLabs"""
        try:
            # Saludo Proactivo Inmediato
            greeting_result = self.agent_manager.process_query("system_greeting_trigger", project_id=project_id)
            text_response = greeting_result.get("response", "Hola.")
            
            print(f"🤖 Agente saluda: {text_response}")
            await self._send_json(websocket, {"status": "speaking", "response": text_response})
            
            audio_response = self.tts_engine.generate_audio(text_response)
            if audio_response:
                await websocket.send_bytes(audio_response)
                
            await self._send_json(websocket, {"status": "listening"})

            while True:
                # Esperar mensajes del frontend (audio crudo o señales de control como interrupción)
                message = await websocket.receive()
                
                if "text" in message:
                    text_data = message["text"]
                    if "interruption" in text_data:
                        print("🛑 Interrupción detectada desde frontend. Cancelando generación actual.")
                        if self.current_task and not self.current_task.done():
                            self.current_task.cancel()
                    continue
                    
                audio_bytes = message.get("bytes")
                if not audio_bytes:
                    continue
                    
                # Si llega nuevo audio, cancelar la meta-tarea anterior si seguía procesando
                if self.current_task and not self.current_task.done():
                    self.current_task.cancel()
                    
                self.current_task = asyncio.create_task(self._process_single_turn(websocket, project_id, audio_bytes))

        except WebSocketDisconnect:
            self.disconnect(websocket)
        except Exception as e:
            print(f"❌ Error en flujo WebSocket Groq Pipeline: {e}")
            self.disconnect(websocket)

    async def _process_single_turn(self, websocket: WebSocket, project_id: str, audio_bytes: bytes):
        try:
            print(f"🎙️ [Opción A] Procesando {len(audio_bytes)} bytes de audio.")
            await self._send_json(websocket, {"status": "transcribing"})
            
            try:
                # STT es sincrónico, lo enviamos a un hilo para no bloquear el WebSocket
                transcription = await asyncio.to_thread(self.stt_engine.transcribe_audio, audio_bytes)
            except Exception as e:
                print(f"⚠️ Error STT (ignorado): {e}")
                await self._send_json(websocket, {"status": "listening"})
                return

            if not transcription or not transcription.strip():
                await self._send_json(websocket, {"status": "listening"})
                return
            
            print(f"🗣️ Usuario dijo: {transcription}")
            await self._send_json(websocket, {"status": "reasoning", "transcription": transcription})
            
            if hasattr(self, 'filler_audios') and self.filler_audios:
                # Enviar audio de "muletilla" aleatorio para rellenar la latencia
                await websocket.send_bytes(random.choice(self.filler_audios))
                await asyncio.sleep(0.01)

            # Validar de nuevo si fuimos cancelados antes de la llamada pesada al LLM
            await asyncio.sleep(0)
            
            agent_result = await asyncio.to_thread(self.agent_manager.process_query, transcription, project_id)
            text_response = agent_result.get("response", "Error procesando")
            
            print(f"🤖 Agente responde: {text_response}")
            await self._send_json(websocket, {"status": "speaking", "response": text_response})
            
            # TTS es sincrónico
            audio_response = await asyncio.to_thread(self.tts_engine.generate_audio, text_response)
            if audio_response:
                await websocket.send_bytes(audio_response)
                
            await self._send_json(websocket, {"status": "listening"})

        except asyncio.CancelledError:
            print("🚫 Tarea de generación abortada por Barge-In.")
            await self._send_json(websocket, {"status": "listening"})
        except Exception as e:
            print(f"❌ Error procesando turno: {e}")
            await self._send_json(websocket, {"status": "listening"})
            self.disconnect(websocket)
        except Exception as e:
            print(f"❌ Error en flujo WebSocket Groq Pipeline: {e}")
            self.disconnect(websocket)

