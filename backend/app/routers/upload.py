import io
import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
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
        
        # 2. Generar un nombre único para Storage
        unique_filename = f"{project_id}/{uuid.uuid4()}_{file.filename}"
        
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
        
        # 5. Ingestar usando nuestro MultiFormatIngestor pasando los bytes
        ingestor.process_file_content(
            file_content=file_content, 
            filename=file.filename, 
            ext=ext, 
            project_id=project_id,
            file_url=file_url
        )
        
        return {
            "message": "Documento subido a Storage y vectorizado exitosamente", 
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
