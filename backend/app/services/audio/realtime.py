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

    async def handle_connection(self, websocket: WebSocket, project_id: str = "default", voice_id: str = "alloy", client_name: str = "", client_email: str = "", client_phone: str = "", context_listing_ids: list[str] = None):
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
            # 0. Hidratar Contexto Visual desde WASI (Para evitar alucinaciones de IDs)
            hydrated_mapping_text = ""
            if context_listing_ids:
                import requests
                from app.services.wasi_api import WasiAPI
                
                wasi = WasiAPI()
                
                def fetch_prop(pid):
                    try:
                        payload = wasi._get_payload({"id_property": pid})
                        res = requests.post(f"{wasi.base_url}/property/search", data=payload, headers=wasi._get_headers(), timeout=2.5)
                        data = res.json()
                        for v in data.values():
                            if isinstance(v, dict) and str(v.get("id_property")) == str(pid):
                                title = v.get("title", "")
                                sale = int(v.get("sale_price", 0) or 0)
                                rent = int(v.get("rent_price", 0) or 0)
                                price_str = f"${sale:,.0f}" if sale > 0 else f"${rent:,.0f}"
                                return f"ID \"{pid}\" - {title}, Precio: {price_str}"
                    except Exception as e:
                        pass
                    return f"ID \"{pid}\""
                
                mapping_lines = []
                # Hit in parallel thread pool to avoid blocking ASGI loop
                tasks = [asyncio.to_thread(fetch_prop, pid) for pid in context_listing_ids]
                results = await asyncio.gather(*tasks)
                
                for i, res in enumerate(results):
                    mapping_lines.append(f"Propiedad {i+1}: {res}")
                
                hydrated_mapping_text = "\n".join(mapping_lines)
                
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
                
                if client_name or client_email or client_phone:
                    base_instructions += f"\n\n[CONTEXTO DE AUTENTICACIÓN]:\nEl sistema ya te envía los datos reales y autenticados del usuario en el payload. Su nombre es '{client_name}', su correo es '{client_email}' y su teléfono es '{client_phone}'. ASUME automáticamente esta información para armar tus Tools. NUNCA le pidas nombre, correo NI TELÉFONO al usuario para agendar; procesa el json de inmediato usando los datos de tu sistema."

                if hydrated_mapping_text:
                    base_instructions += f"\n\n[ESTADO ACTUAL EN LA PANTALLA DEL USUARIO]:\nEsta es la lista cronológica de las propiedades que el cliente está viendo ahora mismo:\n{hydrated_mapping_text}\n(Si el usuario te pide ver o agendar la primera propiedad o la número 1, usa SIEMPRE Y OBLIGATORIAMENTE el ID '{context_listing_ids[0]}'). Así tendrás consciencia espacial total de lo que el usuario ve y llamarás tus herramientas con los ALFANUMÉRICOS REALES exactos."
                
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
                    bot_name = "Sol"
                elif project_id == "xkape":
                    company_name_ov = "Xkape"
                    
                if voice_id == "shimmer" or voice_id == "nova":
                    bot_name = "Isabella"
                
                # Instrucción de rechazo activo de ruido
                instructions += "\n\n[DIRECTIVA DE CANCELACIÓN DE RUIDO]\nEs probable que escuches ruidos de fondo, teclados, respiraciones, golpes o estática. SI EL AUDIO ES SOLO RUIDO, ININTELIGIBLE O NO CONTIENE UNA PREGUNTA DIRIGIDA A TI CLARAMENTE ARTICULADA, GUARDA SILENCIO ABSOLUTO (ignóralo sin decir absolutamente nada). JAMÁS digas 'No te pude oír bien' o '¿Puedes repetir?' a menos que el usuario haya estado activamente en medio de una conversación continua y se haya cortado. Sé inmune al ambiente ininteligible."
                
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
        """Recibe audio del cliente en formato WebM y lo convierte a PCM16 para OpenAI. Bloquea el ruido ambiente con RMS."""
        import base64
        import io
        import time
        from pydub import AudioSegment
        import time
        import asyncio

        self.last_audio_received_time = time.time()
        self.has_uncommitted_audio = False

        async def check_silence():
            while True:
                await asyncio.sleep(0.3)
                # Si han pasado 1.2 segundos sin voz (RMS > 350) y tenemos audio pendiente...
                if getattr(self, "has_uncommitted_audio", False) and (time.time() - getattr(self, "last_audio_received_time", time.time())) > 1.2:
                    try:
                        self.has_uncommitted_audio = False
                        
                        if getattr(self, "response_in_progress", False):
                            await openai_ws.send(json.dumps({"type": "response.cancel"}))
                            self.response_in_progress = False
                            
                        await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                        await client_ws.send_text(json.dumps({"status": "reasoning"}))
                        await openai_ws.send(json.dumps({"type": "response.create"}))
                    except Exception:
                        pass
        
        silence_task = asyncio.create_task(check_silence())

        try:
            while True:
                # Permite recibir comandos y audio en base64 via JSON
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
                        elif data.get("type") == "input_audio_buffer.append":
                            audio_b64 = data.get("audio", "")
                            
                            if audio_b64:
                                import base64
                                import math
                                import struct
                                
                                raw_pcm = base64.b64decode(audio_b64)
                                count = len(raw_pcm) // 2
                                if count > 0:
                                    clean_pcm = raw_pcm[:count*2]
                                    shorts = struct.unpack(f"<{count}h", clean_pcm)
                                    rms = math.sqrt(sum(s*s for s in shorts) / count)
                                else:
                                    rms = 0
                                    
                                if rms >= 10:
                                    print(f"🎤 RMS entrante (JSON): {rms:.0f}")
                                    
                                if rms < 350:
                                    continue
                                
                                append_event = {
                                    "type": "input_audio_buffer.append",
                                    "audio": audio_b64
                                }
                                await openai_ws.send(json.dumps(append_event))
                                self.has_uncommitted_audio = True
                                self.last_audio_received_time = time.time()
                        elif data.get("type") == "input_audio_buffer.commit":
                            print("📥 FRONTEND WS JSON: input_audio_buffer.commit")
                            if getattr(self, "tool_in_progress", False):
                                print("⚠️ Backend IGNORÓ el commit porque hay una búsqueda/tool en progreso.")
                                continue
                            if not getattr(self, "has_uncommitted_audio", False):
                                print("⚠️ Backend IGNORÓ el commit porque no se guardaron fragmentos útiles (RMS fue muy bajo).")
                                continue
                            
                            print("✅ Commit aceptado. Activando IA para procesar el audio aportado...")
                            if getattr(self, "response_in_progress", False):
                                await openai_ws.send(json.dumps({"type": "response.cancel"}))
                                self.response_in_progress = False
                            
                            await openai_ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                            self.has_uncommitted_audio = False
                            await client_ws.send_text(json.dumps({"status": "reasoning"}))
                            await openai_ws.send(json.dumps({"type": "response.create"}))
                    except Exception as e:
                        print(f"⚠️ Error procesando JSON de frontend: {e}")
                    continue
                
                if message.get("bytes"):
                    audio_webm = message["bytes"]
                    buf = io.BytesIO(audio_webm)
                    try:
                        audio_segment = AudioSegment.from_file(buf)
                        # Exportar a PCM16 (raw) a 24000Hz mono, formato esperado por OpenAI
                        raw_pcm = audio_segment.set_frame_rate(24000).set_channels(1).set_sample_width(2).raw_data
                        
                        import math
                        import struct
                        count = len(raw_pcm) // 2
                        if count > 0:
                            clean_pcm_bytes = raw_pcm[:count*2]
                            shorts = struct.unpack(f"<{count}h", clean_pcm_bytes)
                            sum_squares = sum(s * s for s in shorts)
                            rms = math.sqrt(sum_squares / count)
                        else:
                            rms = 0
                            
                        # DEBUG: Ver los decibeles que detecta el servidor para calibrar micrófonos de celular
                        if rms >= 10:
                            print(f"🎤 RMS entrante: {rms:.0f}")
                            
                        if rms < 350:
                            # Ignorar silencios, ruidos de fondo, y ecos de parlante
                            continue
                        
                        append_event = {
                            "type": "input_audio_buffer.append",
                            "audio": base64.b64encode(raw_pcm).decode("utf-8")
                        }
                        await openai_ws.send(json.dumps(append_event))
                        self.has_uncommitted_audio = True
                        self.last_audio_received_time = time.time()
                        
                    except Exception as e:
                        print(f"Error parseando WebM chunk: {e}")
                    continue

        except WebSocketDisconnect:
            print("🔌 Cliente se desconectó de la Opción B.")
            silence_task.cancel()
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            print(f"❌ Error procesando audio del cliente: {err_str}")
            silence_task.cancel()
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
            should_close_ws = False
            current_bot_audio_buffer = bytearray()
            bytes_target_flush = 0
            
            while True:
                message = await openai_ws.recv()
                event = json.loads(message)
                
                if event["type"] == "response.created":
                    self.response_in_progress = True
                elif event["type"] == "response.done":
                    self.response_in_progress = False
                    if should_close_ws:
                        print("🚪 Cortando WebSocket Activamente (end_call invocado) tras despedida de la IA.")
                        try:
                            await client_ws.close(1000)
                        except Exception:
                            pass
                        return
                
                # ELIMINADO: debug_openai spam text_events because blasting 40 text JSONs per second to the Frontend React App 
                # overloads the main UI thread during `response.audio.delta`, starving the HTML5 <audio> component 
                # and producing severe underrun clipping (sounding like a background typewriter "golpeteo de teclado").
                    
                # DEBUG: Imprimir mensajes ignorados para ver si OpenAI está tirando errores silenciosos
                if event["type"] not in ["response.audio.delta", "response.audio_transcript.delta"]:
                    if event["type"] == "error":
                        print(f"🚨 OPENAI REALTIME ERROR: {event}")
                        await client_ws.send_text(json.dumps({
                            "status": "error",
                            "message": f"Error de OpenAI: {event.get('error', {}).get('message', 'Desconocido')}"
                        }))
                
                if event["type"] == "response.audio.delta":
                    # Dynamic Phrase-Pacing: Acumulamos el PCM hasta alcanzar naturalmente el tamaño orgánico
                    # de una oración (marcada por los deltas de texto transcrito), para camuflar los "clics" de React.
                    audio_b64 = event["delta"]
                    pcm_bytes = base64.b64decode(audio_b64)
                    current_bot_audio_buffer.extend(pcm_bytes)
                    
                    # Si cruzamos la meta matemática del Delay post-puntuación, O superamos 2 segundos límite (96000), disparamos:
                    if (bytes_target_flush > 0 and len(current_bot_audio_buffer) >= bytes_target_flush) or len(current_bot_audio_buffer) >= 96000:
                        wav_file = create_wav_header(bytes(current_bot_audio_buffer))
                        await client_ws.send_bytes(wav_file)
                        current_bot_audio_buffer.clear()
                        bytes_target_flush = 0
                
                elif event["type"] == "response.audio.done":
                    # Emite el audio residual (la última palabra antes de que la IA suelte el micrófono)
                    if len(current_bot_audio_buffer) > 0:
                        wav_file = create_wav_header(bytes(current_bot_audio_buffer))
                        await client_ws.send_bytes(wav_file)
                        current_bot_audio_buffer.clear()
                        bytes_target_flush = 0
                        
                elif event["type"] == "response.audio_transcript.delta":
                    transcript_delta = event.get("delta", "")
                    if transcript_delta:
                        # Si detectamos puntuación lingüística, ordenamos al buffer de audio esperar ~0.5 segundos 
                        # de decodificación (24000 bytes) antes de inyectar el salto de WAV para que caiga en el "silencio de respiración".
                        if any(p in transcript_delta for p in [".", ",", "?", "!", "\n"]):
                            # Solo marcamos un nuevo punto de corte si no había ya uno inminente.
                            if bytes_target_flush == 0:
                                bytes_target_flush = len(current_bot_audio_buffer) + 24000
                
                elif event["type"] == "response.audio_transcript.done":
                    transcript = event["transcript"]
                    print(f"🤖 OpenAI dijo: {transcript}")
                        
                    await client_ws.send_text(json.dumps({"status": "listening", "response": transcript}))
                    
                    # Enviar evento de transcripción visual para la UI
                    await client_ws.send_text(json.dumps({
                        "status": "transcription",
                        "role": "assistant",
                        "text": transcript
                    }))
                    
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
                            # Emitir evento oficial de transcripción validado
                            await client_ws.send_text(json.dumps({
                                "status": "transcription",
                                "role": "user",
                                "text": transcript
                            }))
                
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
                        
                        # Señal de Cierre para el interceptor `response.done`
                        should_close_ws = True
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
        self.tool_in_progress = True
        import json
        import asyncio
        from app.routers.tools import execute_tool, ToolRequest
        try:
            if function_name == "schedule_visits" and isinstance(args, dict):
                args["client_name"] = client_name
                args["client_email"] = client_email
                args["client_phone"] = client_phone
                
            if function_name == "search_properties":
                try:
                    await client_ws.send_text(json.dumps({"status": "action", "action": "loading_search"}))
                except Exception:
                    pass
                
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
            
            if "action" in data:
                try:
                    action_payload = {"status": "action", "action": data["action"]}
                    if "listing_id" in data:
                        action_payload["listing_id"] = data["listing_id"]
                    await client_ws.send_text(json.dumps(action_payload))
                except Exception as e:
                    pass
                    
            if "appointments" in data:
                try:
                    await client_ws.send_text(json.dumps({
                        "status": "appointments_created",
                        "appointments": data["appointments"]
                    }))
                except Exception as e:
                    pass
                
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
        finally:
            self.tool_in_progress = False

