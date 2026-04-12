import asyncio
from enum import Enum
import redis.asyncio as aioredis
from app.services.audio.accumulator import SentenceAccumulator

class VoiceState(Enum):
    LISTENING = 'listening'
    THINKING  = 'thinking'
    SPEAKING  = 'speaking'
 
class ConversationContext:
    MAX_TURNS = 10       # máximo de pares usuario/asistente a conservar
    SYSTEM_PROMPT = '''Eres Sol, un asistente experto en inmuebles. Responde siempre en el mismo
    idioma que usa el usuario — si habla español, responde en español; si habla inglés, en inglés.
    Nunca cambies de idioma a mitad de conversación sin que el usuario lo pida.
    Responde de forma natural y concisa, como en una conversación hablada.
    Máximo 2-3 oraciones por turno salvo que el usuario pida más detalle.
    Nunca uses listas con guiones o números — habla como una persona, no como un documento.
    Prohibido markdown.'''
 
    def __init__(self, dynamic_prompt: str = None):
        self.turns = []
        self.tool_results = {}
        self.system_prompt = dynamic_prompt or self.SYSTEM_PROMPT
 
    def add_turn(self, role: str, content: str, interrupted: bool = False):
        suffix = ' [interrumpido]' if interrupted else ''
        self.turns.append({'role': role, 'content': content + suffix})
        # Mantener solo los últimos N turnos
        if len(self.turns) > self.MAX_TURNS * 2:
            self.turns = self.turns[-(self.MAX_TURNS * 2):]
 
    def build_messages(self, tool_context: str = None) -> list:
        messages = [{'role': 'system', 'content': self.system_prompt}]
        if tool_context:
            messages.append({'role': 'system', 'content': f'Datos actuales: {tool_context}'})
        # Inyectar mapeo visual de IDs para que el LLM sepa qué listing es "la primera", etc.
        listing_ids = self.tool_results.get('listing_ids', [])
        detail_open_id = self.tool_results.get('detail_open_id')

        if listing_ids:
            mapping = "\n".join([f"Propiedad #{i+1}: ID [{pid}]" for i, pid in enumerate(listing_ids) if pid])
            if mapping:
                if detail_open_id:
                    # Propiedad ya abierta en pantalla: NO volver a llamar open_property_details.
                    # El usuario está viendo los detalles — responder sus preguntas con los datos actuales.
                    open_idx = next(
                        (i + 1 for i, pid in enumerate(listing_ids) if str(pid) == str(detail_open_id)),
                        "?"
                    )
                    messages.append({'role': 'system', 'content': (
                        f"[DETALLE ABIERTO EN PANTALLA]: El usuario está viendo AHORA MISMO los detalles "
                        f"de la Propiedad #{open_idx} (ID {detail_open_id}).\n"
                        f"Mantén el idioma de la conversación — no cambies de idioma en este bloque.\n"
                        f"PROHIBIDO llamar open_property_details de nuevo — ya está abierta.\n"
                        f"Responde las preguntas del usuario (habitaciones, baños, precio, etc.) "
                        f"directamente usando los Datos actuales.\n"
                        f"HERRAMIENTAS PERMITIDAS desde esta vista:\n"
                        f"  • close_property_details — si el usuario quiere volver a la lista.\n"
                        f"  • schedule_visits — cuando el usuario pide agendar/visitar/quiere ir a ver. "
                        f"    Llámala con: listing_id={detail_open_id}, date=fecha_mencionada. "
                        f"    NUNCA pidas nombre, correo ni teléfono — el sistema los maneja. "
                        f"    NO respondas verbalmente que 'ya agendaste' — llama la herramienta.\n"
                        f"  • select_properties_for_appointment — si el usuario quiere marcar propiedades.\n"
                        f"Para cualquier otra pregunta, responde con los Datos actuales sin llamar herramientas."
                    )})
                else:
                    messages.append({'role': 'system', 'content': (
                        f"[MAPEO VISUAL EN PANTALLA]:\n{mapping}\n"
                        f"(Cuando el usuario diga 'la primera', 'la uno', 'esa', 'el detalle', 'muéstramela', etc., "
                        f"usa OBLIGATORIAMENTE el ID exacto de arriba y llama open_property_details. "
                        f"Para volver a la lista llama close_property_details.)"
                    )})
        messages.extend(self.turns)
        return messages
 
    def clear(self):
        self.turns = []
        self.tool_results = {}

class VoiceSession:
    def __init__(self, session_id: str, redis: aioredis.Redis, ws, agent_manager, tts_engine, dynamic_prompt: str = None):
        self.id         = session_id
        self.redis      = redis
        self.ws         = ws       # WebSocket con el cliente
        self.state      = VoiceState.LISTENING
        self.llm_task   = None     # asyncio.Task del ciclo LLM activo
        self.tts_task   = None     # asyncio.Task del stream TTS activo
        self.context    = ConversationContext(dynamic_prompt=dynamic_prompt)
        self.agent_manager = agent_manager
        self.tts_engine = tts_engine
        self.current_voice_id = "" # Sera inyectado por el gateway
        self.session_language = "es"  # Idioma detectado; pasa a Whisper como hint para reducir alucinaciones
        self.did_emit_text = False
        self.tts_queue = asyncio.Queue()
        self.tts_worker_task = asyncio.create_task(self._tts_worker())
 
    async def _tts_worker(self):
        while True:
            text = await self.tts_queue.get()
            if text == "[STOP]": break
            if text == "[TURN_DONE]":
                try:
                    await self.ws.send_json({'type': 'response.audio_transcript.done'})
                except Exception:
                    pass
                self.tts_queue.task_done()
                continue
            
            self.state = VoiceState.SPEAKING
            if not text.strip(): 
                self.state = VoiceState.LISTENING
                self.tts_queue.task_done()
                continue
                
            self.tts_task = asyncio.create_task(
                self.tts_engine.synthesize_and_stream(text, self, self.current_voice_id)
            )
            try:
                await self.tts_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                print(f"⚠️ TTS worker error (ignorado para mantener sesión activa): {e}")
            finally:
                self.state = VoiceState.LISTENING
                self.tts_queue.task_done()

    async def handle_interruption(self):
        self.interrupted = True  # In-memory flag para abortar TTS
        did_interrupt_something = False

        # 1. Cancelar LLM si sigue generando
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()
            did_interrupt_something = True
            try:
                await self.llm_task
            except asyncio.CancelledError:
                pass
                
        # 1.5 Limpiar la cola de TTS
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
                self.tts_queue.task_done()
                did_interrupt_something = True
            except asyncio.QueueEmpty:
                break
 
        # 2. Cancelar TTS activa
        if self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
            did_interrupt_something = True
            try:
                await self.tts_task
            except asyncio.CancelledError:
                pass
 
        # 3. Notificar cliente — detener reproducción de manera segura en esquema OpenAI
        if did_interrupt_something:
            try:
                await self.ws.send_json({'type': 'response.audio_transcript.done'})
            except:
                pass
 
        # 4. Cambiar estado
        self.state = VoiceState.LISTENING
 
    async def respond(self, user_text: str):
        self.interrupted = False
        self.did_emit_text = False
        self.state = VoiceState.THINKING
 
        # Añadir al contexto
        self.context.add_turn('user', user_text)
 
        accumulator = SentenceAccumulator(on_chunk=self.tts_chunk)
        assistant_text = []

        try:
            self.llm_task = asyncio.create_task(
                self._stream_llm(accumulator, collector=assistant_text, last_user_text=user_text)
            )
            await self.llm_task
            full_response = ''.join(assistant_text)
            if full_response.strip():
                print(f"🤖 Sol dijo: {full_response[:300]}")
            self.context.add_turn('assistant', full_response)
        except asyncio.CancelledError:
            # Barge-in ocurrió — guardar lo generado hasta ahora
            partial = ''.join(assistant_text)
            if partial.strip():
                print(f"🤖 Sol dijo (interrumpido): {partial[:300]}")
                self.context.add_turn('assistant', partial, interrupted=True)
            raise
        finally:
            self.state = VoiceState.LISTENING

    async def _stream_llm(self, accumulator, collector, last_user_text: str):
        # Delegate real query processing and tool calling to AgentManager but streamed

        # Timeout filler: si el LLM no emite nada en 1 segundo, reproducir muletilla
        # para evitar silencio muerto (algoritmo de ubicación, consultas lentas, etc.)
        first_token_received = False
        timeout_filler_task: asyncio.Task | None = None

        async def _timeout_filler():
            await asyncio.sleep(1.0)
            if not first_token_received:
                en_words = {'the', 'is', 'are', 'i', 'you', 'what', 'where', 'how', 'can', 'will'}
                is_english = len(set(last_user_text.lower().split()) & en_words) >= 2
                fillers_es = ["Un momento...", "Déjame verificar eso...", "Enseguida...", "Permítame un instante..."]
                fillers_en = ["One moment...", "Let me check that...", "Just a second...", "Stand by..."]
                import random
                filler = random.choice(fillers_en if is_english else fillers_es)
                await self.tts_chunk(filler)

        timeout_filler_task = asyncio.create_task(_timeout_filler())

        async for token in self.agent_manager.process_query_stream(
            query=last_user_text,
            history=self.context.build_messages(tool_context=self.context.tool_results.get('last_search')),
            project_id=getattr(self, 'project_id', 'buscofacil'),
            client_name=getattr(self, 'client_name', ''),
            client_email=getattr(self, 'client_email', ''),
            client_phone=getattr(self, 'client_phone', ''),
            currency=getattr(self, 'currency', 'COP'),
            websocket=self.ws,
            session_context=self.context
        ):
            if not first_token_received:
                first_token_received = True
                if timeout_filler_task and not timeout_filler_task.done():
                    timeout_filler_task.cancel()

            if token == "[CLEAR_MULETILLAS] ":
                # Cancelar muletilla activa en TTS y vaciar la cola
                if self.tts_task and not self.tts_task.done():
                    self.tts_task.cancel()
                while not self.tts_queue.empty():
                    try:
                        self.tts_queue.get_nowait()
                        self.tts_queue.task_done()
                    except asyncio.QueueEmpty:
                        break
                continue

            collector.append(token)
            await accumulator.push(token)

        if timeout_filler_task and not timeout_filler_task.done():
            timeout_filler_task.cancel()

        await accumulator.flush()

        # Enviar señal de fin de turno una vez TODO se haya reproducido
        await self.tts_queue.put("[TURN_DONE]")

    async def tts_chunk(self, text: str):
        if not self.did_emit_text:
            try:
                await self.ws.send_json({"type": "response.created"})
            except:
                pass
            self.did_emit_text = True
        await self.tts_queue.put(text)
    def close(self):
        if self.tts_worker_task and not self.tts_worker_task.done():
            self.tts_worker_task.cancel()
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()
        if self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
