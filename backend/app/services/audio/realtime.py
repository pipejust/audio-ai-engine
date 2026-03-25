import os
import json
import asyncio
import websockets
from fastapi import WebSocket, WebSocketDisconnect
from app.core.prompts import get_agent_instructions, get_agent_tools

class OpenAIRealtimeManager:
    def __init__(self, agent_manager):
        """
        Manejador para la Opción B: OpenAI Realtime API (Speech-to-Speech)
        Actúa como un relay entre el cliente (HTML) y OpenAI.
        """
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.agent_manager = agent_manager
        self.model = "gpt-4o-realtime-preview-2024-12-17"
        self.url = f"wss://api.openai.com/v1/realtime?model={self.model}"

    async def handle_connection(self, websocket: WebSocket, project_id: str = "default", voice_id: str = "alloy", client_name: str = "", client_email: str = "", context_listing_ids: list[str] = None):
        """
        Gestiona la conexión WebSocket para un cliente específico usando OpenAI Realtime API.
        """
        await websocket.send_text(json.dumps({"status": "connecting", "message": "Iniciando motor Realtime..."}))
        if not self.api_key:
            print("❌ Falta OPENAI_API_KEY")
            await websocket.close()
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1"
        }

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

        try:
            # Conexión persistente hacia OpenAI
            async with websockets.connect(self.url, additional_headers=headers) as openai_ws:
                print("✅ [Opción B] Conectado a OpenAI Realtime API")
                
                # OBLIGATORIO: Leer el evento `session.created` antes de inundar el socket
                # Esto soluciona un race condition mortal que OpenAI ignora si se envían eventos muy rápido
                try:
                    first_msg = await asyncio.wait_for(openai_ws.recv(), timeout=3.0)
                    print(f"✅ Handshake Realtime completado: {json.loads(first_msg).get('type')}")
                except Exception as ex:
                    print(f"⚠️ Aviso inicial de handshake demorado: {ex}")
                
                # Configurar Instrucciones de OpenAI al inicio de la sesión
                base_instructions = get_agent_instructions(project_id, self.agent_manager.bot_name, self.agent_manager.company_name)
                
                if client_name or client_email:
                    base_instructions += f"\n\n[CONTEXTO DE AUTENTICACIÓN]:\nEl sistema ya te envía los datos reales y autenticados del usuario en el payload. Su nombre es '{client_name}' y su correo es '{client_email}'. ASUME automáticamente esta información para armar tus Tools. NUNCA le pidas nombre, correo NI TELÉFONO al usuario para agendar; procesa el json de inmediato usando los datos de tu sistema."

                if context_listing_ids:
                    mapping_text = "\n".join([f"Propiedad #{i+1}: ID [{pid}]" for i, pid in enumerate(context_listing_ids)])
                    base_instructions += f"\n\n[MAPEO VISUAL EN PANTALLA]:\nEste es el orden cronológico exacto de las casas que el cliente está viendo ahora mismo:\n{mapping_text}\n(Usa estrictamente estos IDs referenciales si el usuario te pide ver 'la primera', 'la 3', 'esa última', etc.)."
                
                instructions = base_instructions + "\n\nREGLA CRÍTICA INQUEBRANTABLE SOBRE EL IDIOMA: Por defecto el usuario habla español de Colombia, PERO si el usuario te habla en INGLÉS o en otro idioma, DEBES responderle inmediatamente en ese mismo idioma. NUNCA asumas que el usuario habla en portugués (si escuchas algo que parezca portugués, es una alucinación del sistema de audio y debes ignorarla o asumirla como español/inglés). Nunca transcribas ruidos o silencios como palabras extrañas (ej. 'Thank you for watching'). Si no entiendes el audio o son solo ruidos de teclado o estática, asume que es ruido de fondo e ignóralo. OBLIGATORIO: Cuando necesites buscar información y debas hacer esperar al usuario, NO uses siempre la misma frase. Varía tus frases de espera o muletillas aleatoriamente (ej: 'Mmm, déjame revisar...', 'Un segundo, voy a consultar...', 'A ver qué encuentro...')."
                tools = get_agent_tools(project_id)

                # Validar la voz soportada para evitar que OpenAI rechace TODA la sesión (y los prompts)
                valid_realtime_voices = ["alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar"]
                safe_voice_id = voice_id if voice_id in valid_realtime_voices else "alloy"

                setup_event = {
                    "type": "session.update",
                    "session": {
                        "instructions": instructions,
                        "voice": safe_voice_id,
                        # Desactivamos server_vad porque nuestro Frontend ya hace el VAD y enruta audio en bloques
                        "turn_detection": None,
                        "input_audio_transcription": {
                            "model": "whisper-1"
                        },
                        "temperature": 0.7,
                    }
                }
                if tools:
                    setup_event["session"]["tools"] = tools
                    setup_event["session"]["tool_choice"] = "auto"
                
                await openai_ws.send(json.dumps(setup_event))
                
                # Saludo Proactivo Dinámico (Ajustar nombre según la voz)
                bot_name = self.agent_manager.bot_name
                company_name_ov = self.agent_manager.company_name
                
                if project_id == "buscofacil":
                    company_name_ov = "Busco Fácil"
                elif project_id == "xkape":
                    company_name_ov = "Xkape"
                    
                if voice_id == "shimmer" or voice_id == "nova":
                    bot_name = "Isabella"
                    
                greeting_text = f"Hola, soy {bot_name} de {company_name_ov}. ¿En qué puedo ayudarte?"
                
                greeting_event = {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"El usuario acaba de abrir la aplicación. Tu primera y única respuesta ahora mismo debe ser EXACTAMENTE Y SIN AGREGAR NADA MÁS: '{greeting_text}'"
                            }
                        ]
                    }
                }
                await openai_ws.send(json.dumps(greeting_event))
                
                await openai_ws.send(json.dumps({"type": "response.create"}))
                
                # Definimos las tareas asíncronas para el flujo bidireccional
                client_to_openai_task = asyncio.create_task(
                    self.stream_client_to_openai(websocket, openai_ws)
                )
                openai_to_client_task = asyncio.create_task(
                    self.stream_openai_to_client(openai_ws, websocket, project_id, client_name, client_email, client_phone)
                )
                
                # Esperar a que cualquiera de los dos termine (desconexión)
                done, pending = await asyncio.wait(
                    [client_to_openai_task, openai_to_client_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                for task in pending:
                    task.cancel()

        except Exception as e:
            print(f"❌ Error conectando con OpenAI: {e}")

    async def stream_client_to_openai(self, client_ws: WebSocket, openai_ws):
        """Recibe audio del cliente en formato WebM y lo convierte a PCM16 para OpenAI"""
        import base64
        import io
        from pydub import AudioSegment
        try:
            while True:
                # Permite recibir tanto texto (comandos) como bytes (audio)
                message = await client_ws.receive()
                
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(code=message.get("code", 1000))
                
                if message.get("text"):
                    try:
                        data = json.loads(message["text"])
                        if data.get("type") == "interruption":
                            print("🛑 Interrupción manual recibida desde Frontend")
                            cancel_event = {"type": "response.cancel"}
                            await openai_ws.send(json.dumps(cancel_event))
                    except Exception as e:
                        pass
                    continue
                    
                if message.get("bytes"):
                    audio_bytes = message["bytes"]
                    try:
                        def convert_to_pcm16(b: bytes) -> str:
                            import base64
                            import io
                            from pydub import AudioSegment
                            seg = AudioSegment.from_file(io.BytesIO(b), format="webm")
                            seg = seg.set_frame_rate(24000).set_channels(1).set_sample_width(2)
                            return base64.b64encode(seg.raw_data).decode("utf-8")

                        audio_b64 = await asyncio.to_thread(convert_to_pcm16, audio_bytes)
                        
                        # Enviar el audio
                        append_event = {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64
                        }
                        await openai_ws.send(json.dumps(append_event))
                        
                        # Como el frontend envía frases completas, le indicamos a OpenAI que evalúe y responda de inmediato
                        commit_event = {"type": "input_audio_buffer.commit"}
                        await openai_ws.send(json.dumps(commit_event))
                        
                        await client_ws.send_text(json.dumps({"status": "reasoning"}))
                        
                        response_event = {"type": "response.create"}
                        await openai_ws.send(json.dumps(response_event))
                        
                    except Exception as conv_e:
                        print(f"⚠️ Error convirtiendo WebM a PCM16 o enviando a OpenAI: {conv_e}")

        except WebSocketDisconnect:
            print("🔌 Cliente se desconectó de la Opción B.")
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            print(f"❌ Error procesando audio del cliente: {err_str}")
            try:
                await client_ws.send_text(json.dumps({"status": "error", "message": f"ClientStream Task Crash: {e}"}))
            except:
                pass

    async def stream_openai_to_client(self, openai_ws, client_ws: WebSocket, project_id: str, client_name: str = "", client_email: str = "", client_phone: str = ""):
        """Recibe eventos de OpenAI. Extrae el audio PCM16, lo empaqueta en WAV y se lo envía al cliente."""
        import base64
        import struct

        def create_wav_header(pcm_data: bytes, sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
            data_size = len(pcm_data)
            file_size = data_size + 36
            byte_rate = sample_rate * channels * (bits_per_sample // 8)
            block_align = channels * (bits_per_sample // 8)
            
            header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF', file_size, b'WAVE', b'fmt ', 16, 1, channels,
                sample_rate, byte_rate, block_align, bits_per_sample,
                b'data', data_size
            )
            return header + pcm_data

        try:
            self.response_in_progress = False
            
            while True:
                message = await openai_ws.recv()
                event = json.loads(message)
                
                if event["type"] == "response.created":
                    self.response_in_progress = True
                elif event["type"] == "response.done":
                    self.response_in_progress = False
                
                # REPORTE DE DEPURACIÓN HACIA EL CLIENTE
                try:
                    await client_ws.send_text(json.dumps({"status": "debug_openai", "event_type": event["type"]}))
                except Exception:
                    pass
                    
                # DEBUG: Imprimir mensajes ignorados para ver si OpenAI está tirando errores silenciosos
                if event["type"] not in ["response.audio.delta", "response.audio_transcript.delta"]:
                    if event["type"] == "error":
                        print(f"🚨 OPENAI REALTIME ERROR: {event}")
                        await client_ws.send_text(json.dumps({
                            "status": "error",
                            "message": f"Error de OpenAI: {event.get('error', {}).get('message', 'Desconocido')}"
                        }))
                
                if event["type"] == "response.audio.delta":
                    # Send raw PCM16 base64 decoded bytes directly to the frontend for instant playback
                    audio_b64 = event["delta"]
                    pcm_bytes = base64.b64decode(audio_b64)
                    await client_ws.send_bytes(pcm_bytes)
                
                elif event["type"] == "response.audio_transcript.delta":
                    transcript_delta = event.get("delta", "")
                    if transcript_delta:
                        await client_ws.send_text(json.dumps({"status": "listening_delta", "delta": transcript_delta}))
                
                elif event["type"] == "response.audio_transcript.done":
                    transcript = event["transcript"]
                    print(f"🤖 OpenAI dijo: {transcript}")
                        
                    await client_ws.send_text(json.dumps({"status": "listening", "response": transcript}))
                    
                elif event["type"] == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")
                    if transcript:
                        # Limpiar puntuación para comparar
                        clean_text = transcript.lower().replace(".", "").replace(",", "").replace("¡", "").replace("!", "").replace("¿", "").replace("?", "").strip()
                        
                        hallucinations = [
                            "gracias", "subtítulos", "amén", "gracias por ver", "suscríbete", 
                            "thank you", "thanks", "subtitles", "you", "oh", "ah", 
                            "mbc 뉴스 이덕영입니다", "mbc 뉴스", 
                            "are you speaking english", # Esto pasó porque el modelo de hecho escuchó su propio saludo de inicio debido a que el audio escapó de los altavoces al mic
                            "sí", "no", ".", "ok", "bueno", "ya", "ah", "eh", "hm"
                        ]
                        
                        # Si es muy corto o es una alucinación, le pedimos a OpenAI que borre ese turno para detener el bucle
                        if len(clean_text) <= 1 or clean_text in hallucinations:
                            print(f"🛑 Cancelando Alucinación/Eco en OpenAI: {transcript}")
                            # Nota: borramos la transcripción engañosa del contexto de la IA
                            try:
                                item_id = event.get("item_id")
                                if item_id:
                                    await openai_ws.send(json.dumps({"type": "conversation.item.delete", "item_id": item_id}))
                            except Exception as del_e:
                                print(f"Warning borrando item: {del_e}")
                        else:
                            print(f"🗣️ Usuario dijo: {transcript}")
                            await client_ws.send_text(json.dumps({"transcription": transcript}))
                
                # Manejo de llamadas a herramientas (RAG o APIs externas)
                elif event["type"] == "response.function_call_arguments.done":
                    function_name = event.get("name")
                    call_id = event.get("call_id")
                    args = json.loads(event.get("arguments", "{}"))
                    
                    if function_name == "end_call":
                        print("🛑 IA ha decidido finalizar la llamada.")
                        try:
                            await client_ws.send_text(json.dumps({"status": "end_call"}))
                        except Exception:
                            pass
                        
                        function_output = {
                            "type": "conversation.item.create", 
                            "item": {
                                "type": "function_call_output", 
                                "call_id": call_id, 
                                "output": "Llamada finalizada exitosamente."
                            }
                        }
                        await openai_ws.send(json.dumps(function_output))
                        await openai_ws.send(json.dumps({"type": "response.create"}))
                        continue
                        
                    # Remove custom muletilla logic as the AI generates its own conversational filler internally.
                    # Send tool execution to background task to unblock socket
                    asyncio.create_task(self.execute_tool_and_respond(function_name, call_id, args, openai_ws, project_id, client_ws, client_name, client_email, client_phone))
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            print(f"Error recibiendo de OpenAI: {err_str}")
            try:
                await client_ws.send_text(json.dumps({"status": "error", "message": f"OpenAIStream Task Crash: {e}"}))
            except:
                pass
                    
    async def execute_tool_and_respond(self, function_name: str, call_id: str, args: dict, openai_ws, project_id: str, client_ws, client_name: str = "", client_email: str = "", client_phone: str = ""):
        """
        Ejecuta el Web Service / Herramienta enviando un payload REST 
        hacia un endpoint interno (que simula uno externo) y retorna la respuesta.
        """
        import json
        import asyncio
        from app.routers.tools import execute_tool, ToolRequest
        try:
            if function_name == "schedule_visits" and isinstance(args, dict):
                args["client_name"] = client_name
                args["client_email"] = client_email
                args["client_phone"] = client_phone
                
            tool_req = ToolRequest(project_id=project_id, args=args)
            
            class MockState:
                def __init__(self, am):
                    self.agent_manager = am
            class MockApp:
                def __init__(self, am):
                    self.state = MockState(am)
            class MockRequest:
                def __init__(self, am):
                    self.app = MockApp(am)
                    
            mock_req = MockRequest(self.agent_manager)
            
            # Ejecutar directamente en un hilo para evitar bloqueos HTTP o timeout de IPv6 en Uvicorn
            data = await asyncio.to_thread(execute_tool, function_name, tool_req, mock_req)
            result_text = data.get("result_text", "Done.")
            
            # Enviar los datos estructurados al frontend React Native inmediatamente para renderizado visual
            if "raw_properties" in data:
                try:
                    await client_ws.send_text(json.dumps({
                        "status": "search_results",
                        "listings": data["raw_properties"]
                    }))
                except Exception as e:
                    print(f"Error enviando propiedades crudas al cliente WS: {e}")
                
            function_output = {
                "type": "conversation.item.create", 
                "item": {
                    "type": "function_call_output", 
                    "call_id": call_id, 
                    "output": result_text
                }
            }
            
            await openai_ws.send(json.dumps(function_output))
            
            # 3. Wait until the current active response (e.g. the muletilla) finishes playing
            while getattr(self, "response_in_progress", False):
                await asyncio.sleep(0.1)
                
            await openai_ws.send(json.dumps({"type": "response.create"}))
                
        except Exception as tool_e:
            print(f"Error ejecutando tool via HTTP REST: {tool_e}")
            error_output = {"type": "conversation.item.create", "item": {"type": "function_call_output", "call_id": call_id, "output": "Se produjo un error al conectar con el servidor externo."}}
            await openai_ws.send(json.dumps(error_output))
            await openai_ws.send(json.dumps({"type": "response.create"}))

