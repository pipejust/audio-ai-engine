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

    async def handle_connection(self, websocket: WebSocket, project_id: str = "default", voice_id: str = "alloy"):
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

        try:
            # Conexión persistente hacia OpenAI
            async with websockets.connect(self.url, additional_headers=headers) as openai_ws:
                print("✅ [Opción B] Conectado a OpenAI Realtime API")
                
                # Configurar Instrucciones de OpenAI al inicio de la sesión
                base_instructions = get_agent_instructions(project_id, self.agent_manager.bot_name, self.agent_manager.company_name)
                instructions = base_instructions + "\n\nREGLA CRÍTICA INQUEBRANTABLE SOBRE EL IDIOMA: Por defecto el usuario habla español de Colombia, PERO si el usuario te habla en INGLÉS o en otro idioma, DEBES responderle inmediatamente en ese mismo idioma. NUNCA asumas que el usuario habla en portugués (si escuchas algo que parezca portugués, es una alucinación del sistema de audio y debes ignorarla o asumirla como español/inglés). Nunca transcribas ruidos o silencios como palabras extrañas (ej. 'Thank you for watching'). Si no entiendes el audio o son solo ruidos de teclado o estática, asume que es ruido de fondo e ignóralo. OBLIGATORIO: Cuando necesites buscar información y debas hacer esperar al usuario, NO uses siempre la misma frase. Varía tus frases de espera o muletillas aleatoriamente (ej: 'Mmm, déjame revisar...', 'Un segundo, voy a consultar...', 'A ver qué encuentro...')."
                tools = get_agent_tools(project_id)

                setup_event = {
                    "type": "session.update",
                    "session": {
                        "instructions": instructions,
                        "voice": voice_id,
                        # Desactivamos server_vad porque nuestro Frontend ya hace el VAD y enruta audio en bloques
                        "turn_detection": None,
                        "input_audio_transcription": {
                            "model": "whisper-1"
                        },
                        "tools": tools,
                        "tool_choice": "auto",
                        "temperature": 0.7,
                    }
                }
                await openai_ws.send(json.dumps(setup_event))
                
                # Saludo Proactivo Dinámico (Ajustar nombre según la voz)
                bot_name = self.agent_manager.bot_name
                if voice_id == "shimmer":
                    bot_name = "Isabella"
                    
                greeting_text = f"Mucho gusto mi nombre es {bot_name} de {self.agent_manager.company_name} y te ayudaré con lo que necesites."
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
                await websocket.send_text(json.dumps({"status": "reasoning"}))
                
                # Definimos las tareas asíncronas para el flujo bidireccional
                client_to_openai_task = asyncio.create_task(
                    self.stream_client_to_openai(websocket, openai_ws)
                )
                openai_to_client_task = asyncio.create_task(
                    self.stream_openai_to_client(openai_ws, websocket, project_id)
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
                        # Convertimos el buffer WebM a PCM16 24kHz Mono (Requerimiento de OpenAI Realtime)
                        audio_segment = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
                        audio_segment = audio_segment.set_frame_rate(24000).set_channels(1).set_sample_width(2)
                        pcm_data = audio_segment.raw_data
                        
                        audio_b64 = base64.b64encode(pcm_data).decode("utf-8")
                        
                        # Enviar el audio
                        append_event = {
                            "type": "input_audio_buffer.append",
                            "audio": audio_b64
                        }
                        await openai_ws.send(json.dumps(append_event))
                        
                        # Como el frontend envía frases completas, le indicamos a OpenAI que evalúe y responda de inmediato
                        commit_event = {"type": "input_audio_buffer.commit"}
                        await openai_ws.send(json.dumps(commit_event))
                        
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

    async def stream_openai_to_client(self, openai_ws, client_ws: WebSocket, project_id: str):
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
            audio_buffer = bytearray()
            
            while True:
                message = await openai_ws.recv()
                event = json.loads(message)
                
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
                    # Buffer the base64 PCM16 data instead of sending tiny unplayable WAV fragments
                    audio_b64 = event["delta"]
                    pcm_bytes = base64.b64decode(audio_b64)
                    audio_buffer.extend(pcm_bytes)
                
                elif event["type"] == "response.audio_transcript.done":
                    transcript = event["transcript"]
                    print(f"🤖 OpenAI dijo: {transcript}")
                    
                    # Flush accumulated audio buffer to client as a single WAV file
                    if audio_buffer:
                        wav_bytes = create_wav_header(bytes(audio_buffer))
                        await client_ws.send_bytes(wav_bytes)
                        audio_buffer.clear()
                        
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
                    print(f"🛠️ OpenAI Tool Invoked: {function_name} -> {args}")
                    
                    import random
                    
                    # 1. Determinar y disparar la Muletilla Contextual
                    muletilla = "Dame un segundito..."
                    if function_name == "search_properties":
                        muletilla = random.choice([
                            "Claro, dame un segundo reviso la base de datos de propiedades...",
                            "Un momento, voy a consultar qué propiedades tenemos disponibles por esa zona...",
                            "A ver, déjame mirar en el inventario qué encuentro...",
                            "Permíteme un instante mientras busco las opciones...",
                            "Dame un segundito, ya mismo estoy filtrando las casas para ti...",
                            "Listo, voy a buscar en el sistema a ver qué me sale, un momento...",
                            "Claro que sí, dame un momentico y te cruzo los datos...",
                            "Voy a echarle un vistazo a las propiedades, dame un segundito...",
                            "Perfecto, permíteme revisar qué tenemos en esa ubicación...",
                            "Dame un momentico por favor, estoy conectándome con la base de datos..."
                        ])
                    elif function_name == "generate_software_quote":
                        muletilla = random.choice([
                            "Vale, dame un par de segundos mientras mi sistema calcula los tiempos y costos...",
                            "Excelente, voy a generar la cotización formal en este momento, dame un instante...",
                            "Un segundo mientras redacto la propuesta y estimo los meses de desarrollo...",
                            "Claro, permíteme un momentico armo todo el presupuesto técnico...",
                            "A ver, voy a calcular el alcance para pasarte la propuesta...",
                            "Perfecto, dame un segundito mientras organizo la cotización...",
                            "Ya mismo construyo el escenario financiero...",
                            "Dame un instante, estoy consolidando los costos del proyecto...",
                            "Un momento por favor, voy a sacar las cuentas de esto...",
                            "Listo, dame unos segundos para armarte la proforma formal..."
                        ])
                    elif function_name == "consult_knowledge_base":
                        muletilla = random.choice([
                            "Déjame revisar la documentación un segundo...",
                            "Voy a consultar mis manuales, permíteme un momento...",
                            "A ver qué dice la base de conocimiento sobre eso...",
                            "Dame un segundito, busco esa información técnica en mis guías...",
                            "Permíteme verifico el reglamento al respecto...",
                            "Un momentico, consulto el portal de conocimiento a ver qué nos dice...",
                            "Voy a echarle un ojo a las normativas, dame un instante...",
                            "Claro, déjame leer rápidamente el manual sobre ese tema...",
                            "Un segundo mientras consulto mis bases legales...",
                            "A ver, voy a buscar la respuesta oficial en mi archivo..."
                        ])
                    elif function_name == "schedule_appointment":
                        muletilla = random.choice([
                            "Un segundo mientras conecto con la agenda para separar el espacio...",
                            "Claro, dame un instante para registrar tu visita en el calendario...",
                            "Permíteme un momentico, abro la agenda de citas...",
                            "A ver, voy a revisar qué huecos nos quedan disponibles para eso...",
                            "Dame un secundito, ya mismo separo tu lugar...",
                            "Listo, voy a agendar esto en el sistema...",
                            "Un momentico por favor, bloqueando la fecha en el calendario...",
                            "Perfecto, dame un instante para dejar esto súper agendado...",
                            "Voy a apartar tu espacio, dame un segundo...",
                            "Claro que sí, dame un momento para confirmar el horario..."
                        ])
                        
                    filler_prompt = f"OBLIGATORIO: Dile al usuario EXACTAMENTE esta frase rápido con voz muy natural de COLOMBIANO NATIVO para hacerlo esperar mientras busco: '{muletilla}'"
                    await openai_ws.send(json.dumps({"type": "conversation.item.create", "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": filler_prompt}]}}))
                    await openai_ws.send(json.dumps({"type": "response.create"}))
                    
                    # 2. Despachar la ejecución de la Herramienta al Background
                    # Esto evita bloquear el bucle `recv()` y permite que el usuario ESCUCHE la muletilla generada arriba
                    asyncio.create_task(self.execute_tool_and_respond(function_name, call_id, args, openai_ws, project_id))
        except Exception as e:
            import traceback
            err_str = traceback.format_exc()
            print(f"Error recibiendo de OpenAI: {err_str}")
            try:
                await client_ws.send_text(json.dumps({"status": "error", "message": f"OpenAIStream Task Crash: {e}"}))
            except:
                pass
                    
    async def execute_tool_and_respond(self, function_name: str, call_id: str, args: dict, openai_ws, project_id: str):
        """
        Ejecuta el Web Service / Herramienta enviando un payload REST 
        hacia un endpoint interno (que simula uno externo) y retorna la respuesta.
        """
        import json
        import httpx
        try:
            # Simular petición HTTP al endpoint de herramientas
            url = f"http://localhost:8000/api/tools/{function_name}"
            payload = {
                "project_id": project_id,
                "args": args
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, timeout=10.0)
                
            if response.status_code == 200:
                data = response.json()
                result_text = data.get("result_text", "Done.")
            else:
                result_text = f"Error from Web Service: {response.text}"
                
            function_output = {
                "type": "conversation.item.create", 
                "item": {
                    "type": "function_call_output", 
                    "call_id": call_id, 
                    "output": result_text
                }
            }
            
            await openai_ws.send(json.dumps(function_output))
            await openai_ws.send(json.dumps({"type": "response.create"}))
                
        except Exception as tool_e:
            print(f"Error ejecutando tool via HTTP REST: {tool_e}")
            error_output = {"type": "conversation.item.create", "item": {"type": "function_call_output", "call_id": call_id, "output": "Se produjo un error al conectar con el servidor externo."}}
            await openai_ws.send(json.dumps(error_output))
            await openai_ws.send(json.dumps({"type": "response.create"}))

