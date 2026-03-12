import os
try:
    import pandas as pd
    from PyPDF2 import PdfReader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    HAS_INGESTION = True
except ImportError:
    HAS_INGESTION = False

class MultiFormatIngestor:
    def __init__(self, vector_store):
        """Inicializa el Ingestor pasándole una instancia de VectorStoreManager"""
        self.vector_store = vector_store
        
        if HAS_INGESTION:
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                length_function=len,
            )
        else:
            self.text_splitter = None
        # backend/knowledge_registry.db is handled by SQLAlchemy now via Base.metadata.create_all
        # Database initialization has been moved to main.py
        pass
        
    def _log_source(self, project_id: str, source_type: str, source_name: str, file_url: str = None):
        """Registra un nuevo archivo ingestado en la base de datos relacional usando SQLAlchemy"""
        from app.db.session import SessionLocal
        from app.db.models import TrainingSource

        db = SessionLocal()
        try:
            new_source = TrainingSource(
                project_id=project_id,
                source_type=source_type,
                source_name=source_name,
                status="indexed",
                file_url=file_url
            )
            db.add(new_source)
            db.commit()
            print(f"📝 Auditoría: Registrada nueva fuente de conocimiento '{source_name}' para el proyecto '{project_id}'.")
        except Exception as e:
            db.rollback()
            print(f"❌ Error al registrar en BD: {e}")
        finally:
            db.close()

    def process_file_content(self, file_content: bytes, filename: str, ext: str, project_id: str = "default", file_url: str = None):
        """Procesa el contenido de un documento (bytes) y lo envía a la base vectorial"""
        print(f"📄 Procesando contenido de archivo: {filename} ({ext}) para proyecto: {project_id}")
        
        text_content = ""
        metadata = {"source": filename, "type": ext, "project_id": project_id}
        if file_url:
            metadata["file_url"] = file_url

        if ext == 'txt':
            text_content = file_content.decode('utf-8')
        elif ext == 'pdf':
            import io
            reader = PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        elif ext == 'csv':
            import io
            df = pd.read_csv(io.BytesIO(file_content))
            # Convierte cada fila en un texto estructurado
            text_content = df.to_string()
        else:
            print(f"Formato no soportado: {ext}")
            return
        
        self._split_and_store(text_content, metadata)
        
        # Guardar en base de datos para auditoría
        self._log_source(project_id, ext, filename, file_url=file_url)
    def process_text(self, text: str, project_id: str = "default", split: bool = True):
        """Recibe texto libre y lo envía a la base vectorial"""
        if not text.strip():
            print("❌ Texto vacío, nada que procesar.")
            return
            
        print(f"✍️ Procesando texto libre para proyecto: {project_id} (Split={split})")
        metadata = {"source": "manual_input", "type": "text", "project_id": project_id}
        
        if split:
            self._split_and_store(text, metadata)
        else:
            from langchain_core.documents import Document
            doc = Document(page_content=text, metadata=metadata)
            self.vector_store.add_documents([doc])
            print(f"✅ 1 documento integro guardado en la BD Vectorial.")
            
        # Guardar en base de datos para auditoría
        snippet = str(text)[:30] + "..." if len(text) > 30 else text
        self._log_source(project_id, "text", f"Texto Manual: {snippet}")

    def _split_and_store(self, text: str, metadata: dict):
        """Divide el texto en chunks y los guarda en ChromaDB"""
        chunks = self.text_splitter.create_documents([text], metadatas=[metadata])
        self.vector_store.add_documents(chunks)
        print(f"✅ {len(chunks)} fragmentos guardados en la BD Vectorial.")

