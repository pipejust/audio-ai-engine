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

def sync_wasi_on_startup():
    try:
        print("🔄 Inicializando sincronización de WASI automática...")
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
    allow_origins=["*"],
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
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """
    Endpoint de WebSocket para streaming Full Duplex.
    Verifica JWT antes de permitir el pase al gateway.
    """
    if not token:
        await websocket.close(code=1008)  # Missing Token
        return
        
    payload = security.verify_token(token)
    if not payload:
        await websocket.close(code=1008)  # Invalid Token
        return
        
    # Obtener el project_id "duro" (seguro) del JWT validado
    auth_project_id = payload.get("project_id", "default")

    await voice_gateway.connect(websocket)
    await voice_gateway.process_audio_stream(websocket, auth_project_id)

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
