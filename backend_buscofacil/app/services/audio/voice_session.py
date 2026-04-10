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
    SYSTEM_PROMPT = '''Eres un asistente experto en inmuebles. Responde de forma
    natural y concisa, como en una conversación hablada. Máximo 2-3 oraciones
    por turno salvo que el usuario pida más detalle. Nunca uses listas con
    guiones o números — habla como una persona, no como un documento. Prohibido markdown.'''
 
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
        self.state = VoiceState.THINKING
 
        # Añadir al contexto
        self.context.add_turn('user', user_text)
 
        accumulator = SentenceAccumulator(on_chunk=self.tts_chunk)
        assistant_text = []

        try:
            self.llm_task = asyncio.create_task(
                self._stream_llm(accumulator, assistant_text, user_text)
            )
            await self.llm_task
            # Respuesta completa — guardar contexto
            self.context.add_turn('assistant', ''.join(assistant_text))
        except asyncio.CancelledError:
            # Barge-in ocurrió — guardar lo generado hasta ahora
            partial = ''.join(assistant_text)
            if partial.strip():
                self.context.add_turn('assistant', partial, interrupted=True)
            raise
        finally:
            self.state = VoiceState.LISTENING

    async def _stream_llm(self, accumulator, collector, last_user_text: str):
        # Delegate real query processing and tool calling to AgentManager but streamed
        
        async for token in self.agent_manager.process_query_stream(
            query=last_user_text, 
            history=self.context.build_messages(),
            project_id=getattr(self, 'project_id', 'buscofacil'),
            client_name=getattr(self, 'client_name', ''),
            client_email=getattr(self, 'client_email', ''),
            client_phone=getattr(self, 'client_phone', ''),
            currency=getattr(self, 'currency', 'COP'),
            websocket=self.ws
        ):
            collector.append(token)
            await accumulator.push(token)
            
        await accumulator.flush()

        # Enviar señal de fin de turno una vez TODO se haya reproducido
        await self.tts_queue.put("[TURN_DONE]")

    async def tts_chunk(self, text: str):
        await self.tts_queue.put(text)
