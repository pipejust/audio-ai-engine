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
from app.services.wasi_api import WasiAPI
from app.services.vector_store import VectorStoreManager
from langchain_core.documents import Document
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

def sync_wasi_on_startup():
    try:
        logger.info("🔄 Inicializando sincronización de WASI automática...")
        wasi = WasiAPI()
        vector_store = VectorStoreManager()
        
        all_properties = []
        skip = 0
        take = 50
        project_id = "buscofacil"
        
        while True:
            properties = wasi.search_properties(take=take, skip=skip)
            if not properties:
                break
                
            all_properties.extend(properties)
            skip += take
            
            if len(properties) < take:
                break
        
        if all_properties:
            # Ingertar cada propiedad como un bloque de texto independiente en el RAG
            for prop in all_properties:
                formatted_data = wasi.format_property_for_rag(prop)
                if formatted_data and "text" in formatted_data:
                    text = formatted_data["text"]
                    metas = formatted_data["metadata"]
                    metas["project_id"] = project_id
                    
                    doc = Document(page_content=text, metadata=metas)
                    vector_store.add_documents([doc])
            
            print(f"✅ Sincronización WASI completada: {len(all_properties)} propiedades vectorizadas.")
        else:
            print("⚠️ Sincronización WASI: No se encontraron propiedades para vectorizar.")

    except Exception as e:
        print(f"❌ Error en sincronización WASI automática: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicializar Base de Datos Relacional (SQLite/PostgreSQL)
    from app.db.session import engine
    from app.db.models import Base
    Base.metadata.create_all(bind=engine)
    print("✅ Base de datos relacional inicializada correctamente.")

    # Tarea en segundo plano en otro thread para no bloquear el event loop de Uvicorn
    # ya que sync_wasi_on_startup contiene peticiones HTTP síncronas que bloquean
    asyncio.create_task(asyncio.to_thread(sync_wasi_on_startup))
    yield


app = FastAPI(title="MoshWasi AI Audio Project", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "https://audioaiproject.vercel.app",
        "*"
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar nuestro Orquestador de Agentes
agent_manager = AgentManager()
app.state.agent_manager = agent_manager

from app.routers import upload, auth, tools

app.include_router(upload.router)
app.include_router(auth.router)
app.include_router(tools.router, prefix="/api/tools")


class ChatRequest(BaseModel):
    query: str
    session_id: str = "default_session"
    project_id: str = "default"

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
    result = agent_manager.process_query(request.query, request.session_id, request.project_id)
    return result

# Configuración del Gateway de Voz Full Duplex
from fastapi import WebSocket
from app.services.audio.gateway import VoiceGatewayManager
from app.services.audio.stt import STTEngine
from app.services.audio.tts import TTSEngine
from app.services.audio.realtime import OpenAIRealtimeManager

stt_engine = STTEngine()
tts_engine = TTSEngine()
openai_realtime_manager = OpenAIRealtimeManager(agent_manager)
voice_gateway = VoiceGatewayManager(agent_manager, stt_engine, tts_engine, openai_realtime_manager)

@app.websocket("/voice/stream")
async def websocket_endpoint(websocket: WebSocket):
    """
    Endpoint de WebSocket público para streaming Full Duplex de audio.
    Ya no requiere JWT para permitir acceso público a la interfaz de voz.
    """
    await voice_gateway.connect(websocket)
    project_id = websocket.query_params.get("project_id", "default")
    await voice_gateway.process_audio_stream(websocket, project_id)

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
if os.path.exists(os.path.join(frontend_base, "buscofacil")):
    app.mount("/buscofacil", StaticFiles(directory=os.path.join(frontend_base, "buscofacil"), html=True), name="buscofacil_ui")
if os.path.exists(os.path.join(frontend_base, "xkape")):
    app.mount("/xkape", StaticFiles(directory=os.path.join(frontend_base, "xkape"), html=True), name="xkape_ui")
