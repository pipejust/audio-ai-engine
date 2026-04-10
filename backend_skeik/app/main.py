import os
from dotenv import load_dotenv
# Forzamos la carga del .env (override) para evitar que variables cacheadas rompan las llaves
load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.services.agent_manager import AgentManager
from app.routers import upload, auth
from app.core import security

from contextlib import asynccontextmanager
import asyncio

from app.services.vector_store import VectorStoreManager
from langchain_core.documents import Document
import logging
from io import StringIO

log_stream = StringIO()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("uvicorn.error")

# Custom handler for our buffer
stream_handler = logging.StreamHandler(log_stream)
stream_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Redirect standard prints to the logger so we catch everything
import sys
class PrintToLogger:
    def write(self, message):
        if message.strip():
            logger.info(message.strip())
    def flush(self): pass
sys.stdout = PrintToLogger()



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar Base de Datos Relacional (SQLite/PostgreSQL)
    from app.db.session import engine
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    print("✅ Base de datos relacional inicializada correctamente.")

    yield


app = FastAPI(title="MoshWasi AI Audio Project", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar nuestro Orquestador de Agentes
agent_manager = AgentManager()
app.state.agent_manager = agent_manager

from app.routers import upload, auth, tools, settings

app.include_router(upload.router)
app.include_router(auth.router)
app.include_router(tools.router, prefix="/api/tools")
app.include_router(settings.router)


from pydantic import Field
class ChatRequest(BaseModel):
    query: str
    session_id: str = "default_session"
    project_id: str = "default"
    context_listing_ids: list[str] = []
    client_name: str = ""
    client_email: str = ""
    client_phone: str = ""
    clientName: str = ""
    clientEmail: str = ""
    clientPhone: str = ""

@app.get("/")
def read_root():
    return {"message": "Welcome to MoshWasi AI Audio API. Multi-Agent Layer ready."}

@app.post("/chat")
def chat_with_agent(request: ChatRequest):
    """
    Endpoint principal de texto. El Agent Manager evaluará la consulta,
    decidirá si necesita consultar la base vectorial, raspar una web, 
    o simplemente responder basándose en su conocimiento.
    """
    c_name = request.client_name or request.clientName
    c_email = request.client_email or request.clientEmail
    c_phone = request.client_phone or request.clientPhone
    
    result = agent_manager.process_query(
        request.query, 
        request.project_id, 
        request.session_id,
        request.context_listing_ids,
        c_name,
        c_email,
        c_phone
    )
    return result

# Configuración del Gateway de Voz Full Duplex
from fastapi import WebSocket
from app.services.audio.gateway import VoiceGatewayManager
from app.services.audio.stt import STTEngine
from app.services.audio.tts import TTSEngine
from app.services.audio.realtime import OpenAIRealtimeManager

stt_engine = STTEngine()
tts_engine = TTSEngine()

# Ya no instanciamos el VoiceGateway de forma global.
# Debe ser instanciado dinámicamente por solicitud websocket para garantizar aislamiento de memoria (threads).
@app.websocket("/voice/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint de WebSocket público para streaming Full Duplex de audio.
    Ya no requiere JWT para permitir acceso público a la interfaz de voz.
    """
    local_realtime = OpenAIRealtimeManager(agent_manager)
    local_gateway = VoiceGatewayManager(agent_manager, stt_engine, tts_engine, local_realtime)
    await local_gateway.connect(websocket)
    project_id = websocket.query_params.get("project_id", "default")
    client_name = websocket.query_params.get("clientName", websocket.query_params.get("client_name", ""))
    client_email = websocket.query_params.get("clientEmail", websocket.query_params.get("client_email", ""))
    client_phone = websocket.query_params.get("clientPhone", websocket.query_params.get("client_phone", ""))
    context_ids_str = websocket.query_params.get("context_listing_ids", "")
    context_listing_ids = context_ids_str.split(",") if context_ids_str else []
    
    try:
        await local_gateway.process_audio_stream(websocket, project_id, client_name, client_email, client_phone, context_listing_ids)
    finally:
        local_gateway.disconnect(websocket)

@app.websocket("/ws/realtime/{project_id}")
async def websocket_legacy_endpoint(websocket: WebSocket, project_id: str):
    """
    Endpoint de WebSocket alias (Legacy) para mantener compatibilidad 
    con frontends cacheados en Vercel que apuntan a la ruta antigua.
    """
    local_realtime = OpenAIRealtimeManager(agent_manager)
    local_gateway = VoiceGatewayManager(agent_manager, stt_engine, tts_engine, local_realtime)
    await local_gateway.connect(websocket)
    client_name = websocket.query_params.get("clientName", websocket.query_params.get("client_name", ""))
    client_email = websocket.query_params.get("clientEmail", websocket.query_params.get("client_email", ""))
    client_phone = websocket.query_params.get("clientPhone", websocket.query_params.get("client_phone", ""))
    context_ids_str = websocket.query_params.get("context_listing_ids", "")
    context_listing_ids = context_ids_str.split(",") if context_ids_str else []
    
    try:
        await local_gateway.process_audio_stream(websocket, project_id, client_name, client_email, client_phone, context_listing_ids)
    finally:
        local_gateway.disconnect(websocket)

@app.get("/api/test-openai")
async def test_openai_api():
    """Diagnóstico temporal para probar OpenAI Realtime API desde Render."""
    import os
    import json
    import websockets
    import asyncio
    from app.core.prompts import get_agent_instructions, get_agent_tools
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "No OPENAI_API_KEY found"}
        
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    trace = []
    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            trace.append("Connected to OpenAI")
            # Read first event (session.created)
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            trace.append({"received": json.loads(msg)})
            
            project_id = "buscofacil"
            base_instructions = get_agent_instructions(project_id, "TestBot", "TestComp")
            instructions = base_instructions + "\n\nREGLA CRÍTICA... "
            tools = get_agent_tools(project_id)
            
            setup_event = {
                "type": "session.update",
                "session": {
                    "instructions": instructions,
                    "voice": "alloy",
                    "turn_detection": None,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.7,
                }
            }
            trace.append({"sent": "setup_event"})
            await ws.send(json.dumps(setup_event))
            
            resp_event = {"type": "response.create"}
            trace.append({"sent": "response.create"})
            await ws.send(json.dumps(resp_event))
            
            for _ in range(5):
                try:
                    reply = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    trace.append({"received": json.loads(reply)})
                except asyncio.TimeoutError:
                    trace.append("Timeout waiting for more events")
                    break
                    
    except Exception as e:
        trace.append({"error": str(e)})
        
    return {"trace": trace}

@app.websocket("/ws/test-openai")
async def test_websocket_openai(websocket: WebSocket):
    import os
    import json
    import websockets
    import asyncio
    from app.core.prompts import get_agent_instructions, get_agent_tools
    
    await websocket.accept()
    
    api_key = os.getenv("OPENAI_API_KEY")
    url = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "realtime=v1"
    }
    
    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            await websocket.send_text("Connected to OpenAI")
            
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            await websocket.send_text(f"Session Created: {msg}")
            
            project_id = "buscofacil"
            base_instructions = get_agent_instructions(project_id, "TestBot", "TestComp")
            instructions = base_instructions + "\n\nREGLA CRÍTICA... "
            tools = get_agent_tools(project_id)
            
            setup_event = {
                "type": "session.update",
                "session": {
                    "instructions": instructions,
                    "voice": "alloy",
                    "turn_detection": None,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.7,
                }
            }
            await ws.send(json.dumps(setup_event))
            await websocket.send_text("Sent session.update")
            
            greeting_event = {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Hola, prueba."
                        }
                    ]
                }
            }
            await ws.send(json.dumps(greeting_event))
            await websocket.send_text("Sent greeting")
            
            resp_event = {"type": "response.create"}
            await ws.send(json.dumps(resp_event))
            await websocket.send_text("Sent response.create")
            
            for _ in range(5):
                try:
                    reply = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    await websocket.send_text(f"OAI MSG: {reply}")
                except asyncio.TimeoutError:
                    await websocket.send_text("Timeout.")
                    break
    except Exception as e:
        await websocket.send_text(f"Error: {e}")

@app.get("/api/logs")
async def get_memory_logs():
    return {"logs": log_stream.getvalue().split("\n")[-100:]}

@app.get("/cleanup-db")
async def cleanup_db():
    from app.db.session import SessionLocal
    from app.db.models import TrainingSource
    from app.services.vector_store import VectorStoreManager
    db = SessionLocal()
    records = db.query(TrainingSource).filter(TrainingSource.project_id == 'buscofacil').all()
    to_delete = []
    names = []
    for r in records:
        name_lower = r.source_name.lower() if r.source_name else ""
        if 'investigaci' in name_lower or 'xkape' in name_lower or 'ti' in name_lower or 'cotizacion' in name_lower:
            to_delete.append(r)
            names.append(r.source_name or "Unknown")
    
    if not to_delete:
        db.close()
        return {"msg": "No hay nada que borrar"}
        
    vs = VectorStoreManager()
    deleted_vectors = 0
    
    for r in to_delete:
        try:
            if vs.vectorstore:
                collection = getattr(vs.vectorstore, '_collection', None)
                if collection:
                    results = collection.get(where={"$and": [{"project_id": r.project_id}, {"source": r.source_name}]})
                    if results and results.get('ids'):
                        collection.delete(ids=results['ids'])
                        deleted_vectors += len(results['ids'])
        except Exception as e:
            pass
        db.delete(r)
        
    db.commit()
    db.close()
    return {"msg": "Limpieza OK", "deleted": names, "vectors_deleted": deleted_vectors}

# Servir estáticamente los frontends para entorno local
import os
frontend_base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

if os.path.exists(os.path.join(frontend_base, "xkape")):
    app.mount("/xkape", StaticFiles(directory=os.path.join(frontend_base, "xkape"), html=True), name="xkape_ui")
