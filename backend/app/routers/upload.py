import io
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from typing import Optional
from app.services.vector_store import VectorStoreManager
from app.services.ingestion.multi_format import MultiFormatIngestor
from app.services.wasi_api import WasiAPI
from app.services.supabase_client import supabase_client
from app.core.config import settings

router = APIRouter(
    prefix="/upload",
    tags=["Ingestion"]
)

# Inicializamos el VectorStore y el Ingestor
# En una aplicación real usaríamos Dependency Injection, pero para mantener la arquitectura actual
# instanciamos aquí o lo podríamos recibir de main.py
vector_store = VectorStoreManager()
ingestor = MultiFormatIngestor(vector_store)

@router.post("/document")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str = Form("default")
):
    """
    Sube un documento (PDF, TXT, CSV) para ser ingerido en la base vectorial del proyecto específico.
    """
    valid_extensions = ["pdf", "txt", "csv"]
    ext = file.filename.split('.')[-1].lower()
    
    if ext not in valid_extensions:
        raise HTTPException(status_code=400, detail=f"Formato no soportado. Usa: {', '.join(valid_extensions)}")
        
    try:
        # 1. Leer archivo crudo
        file_content = await file.read()
        
        # 2. Generar un nombre único para Storage, saneando el nombre del archivo
        import re
        safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', file.filename)
        unique_filename = f"{project_id}/{uuid.uuid4()}_{safe_filename}"
        
        # 3. Subir a Supabase Storage
        bucket_name = settings.SUPABASE_STORAGE_BUCKET
        res = supabase_client.storage.from_(bucket_name).upload(
            path=unique_filename,
            file=file_content,
            file_options={"content-type": file.content_type}
        )
        
        # 4. Obtener URL pública (asumiendo que el bucket es público)
        # Si el bucket es privado, se podría generar una URL firmada.
        file_url = supabase_client.storage.from_(bucket_name).get_public_url(unique_filename)
        
        # 5. Ingestar usando nuestro MultiFormatIngestor pasando los bytes (Background Task)
        # Esto previene que la petición se quede en timeout por lo que tarde el modelo ML
        background_tasks.add_task(
            ingestor.process_file_content,
            file_content=file_content, 
            filename=file.filename, 
            ext=ext, 
            project_id=project_id,
            file_url=file_url
        )
        
        return {
            "message": "Documento subido. La vectorización se procesará en segundo plano.", 
            "project_id": project_id, 
            "filename": file.filename,
            "file_url": file_url
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando documento: {str(e)}")

@router.post("/text")
async def upload_text(
    text: str = Form(...),
    project_id: str = Form("default")
):
    """
    Ingesta texto libre directamente en el sistema RAG.
    """
    try:
        ingestor.process_text(text, project_id=project_id)
        return {"message": "Texto ingerido exitosamente", "project_id": project_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando texto: {str(e)}")

@router.post("/wasi")
async def upload_wasi(
    take: int = Form(50),
    project_id: str = Form("buscofacil")
):
    """
    Se conecta a la API de Wasi, extrae TODAS las propiedades usando paginación,
    las formatea a texto RAG y las ingesta en la base vectorial del proyecto de inmobiliaria.
    """
    try:
        wasi = WasiAPI()
        
        all_properties = []
        skip = 0
        
        while True:
            properties = wasi.search_properties(take=take, skip=skip)
            if not properties:
                break
                
            all_properties.extend(properties)
            skip += take
            
            if len(properties) < take:
                break
        
        if not all_properties:
            return {"message": "No se encontraron propiedades en Wasi o hubo un error."}
            
        from langchain_core.documents import Document
        
        # Ingertar cada propiedad como un bloque de texto independiente en el RAG
        for prop in all_properties:
            formatted_data = wasi.format_property_for_rag(prop)
            if formatted_data and "text" in formatted_data:
                text = formatted_data["text"]
                metas = formatted_data["metadata"]
                metas["project_id"] = project_id
                
                doc = Document(page_content=text, metadata=metas)
                vector_store.add_documents([doc])
                
        return {
            "message": f"Sincronizadas y vectorizadas {len(all_properties)} propiedades desde Wasi exitosamente", 
            "project_id": project_id,
            "count": len(all_properties)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sincronizando Wasi: {str(e)}")

@router.get("/sources")
async def get_sources(project_id: str):
    """
    Obtiene la lista de todas las fuentes de entrenamiento (documentos, textos, etc.) de un proyecto.
    """
    from app.db.session import SessionLocal
    from app.db.models import TrainingSource
    
    db = SessionLocal()
    try:
        sources = db.query(TrainingSource).filter(TrainingSource.project_id == project_id).all()
        return [
            {
                "id": s.id,
                "project_id": s.project_id,
                "source_type": s.source_type,
                "source_name": s.source_name,
                "status": s.status,
                "file_url": s.file_url,
                "timestamp": s.timestamp.isoformat() if s.timestamp else None
            }
            for s in sources
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error obteniendo fuentes: {str(e)}")
    finally:
        db.close()

@router.delete("/sources/{source_id}")
async def delete_source(source_id: int):
    """
    Elimina una fuente de entrenamiento tanto de la base de datos relacional como de la base vectorial.
    """
    from app.db.session import SessionLocal
    from app.db.models import TrainingSource
    
    db = SessionLocal()
    try:
        # Encontrar la fuente en la base de datos
        source = db.query(TrainingSource).filter(TrainingSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Fuente no encontrada")
            
        project_id = source.project_id
        source_name = source.source_name
        
        # Eliminar vectores de ChromaDB
        try:
            if vector_store.vectorstore:
                collection = getattr(vector_store.vectorstore, '_collection', None)
                if collection:
                    results = collection.get(where={"$and": [{"project_id": project_id}, {"source": source_name}]})
                    if results and results.get('ids'):
                        collection.delete(ids=results['ids'])
                        print(f"🗑️ Eliminados {len(results['ids'])} vectores para {source_name}")
        except Exception as e:
            print(f"⚠️ Logre borrar el registro, pero error de Chroma: {e}")
            
        # Optional: Si es un archivo, eliminar de Supabase Storage. (Omitido por seguridad o se puede implementar si file_url existe).
            
        # Eliminar el registro de SQLite/Postgres
        db.delete(source)
        db.commit()
        
        return {"message": "Fuente eliminada exitosamente", "id": source_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error eliminando fuente: {str(e)}")
    finally:
        db.close()
