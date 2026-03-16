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
        
    def _create_source(self, project_id: str, source_type: str, source_name: str, file_url: str = None) -> int:
        """Crea un registro en estado 'processing' y retorna su ID"""
        from app.db.session import SessionLocal
        from app.db.models import TrainingSource

        db = SessionLocal()
        try:
            new_source = TrainingSource(
                project_id=project_id,
                source_type=source_type,
                source_name=source_name,
                status="processing",
                file_url=file_url
            )
            db.add(new_source)
            db.commit()
            db.refresh(new_source)
            print(f"📝 Auditoría: Iniciando procesamiento de '{source_name}' (ID: {new_source.id})")
            return new_source.id
        except Exception as e:
            db.rollback()
            print(f"❌ Error al crear registro en BD: {e}")
            return None
        finally:
            db.close()

    def _update_source_status(self, source_id: int, status: str):
        if not source_id:
            return
        from app.db.session import SessionLocal
        from app.db.models import TrainingSource
        db = SessionLocal()
        try:
            source = db.query(TrainingSource).filter(TrainingSource.id == source_id).first()
            if source:
                source.status = status
                db.commit()
                print(f"📝 Auditoría: Estado actualizado a '{status}' para fuente ID {source_id}.")
        except Exception as e:
            db.rollback()
            print(f"❌ Error actualizando estado en BD: {e}")
        finally:
            db.close()

    def process_file_content(self, file_content: bytes, filename: str, ext: str, project_id: str = "default", file_url: str = None):
        """Procesa el contenido de un documento (bytes) y lo envía a la base vectorial"""
        import gc
        import traceback
        import sys
        print(f"📄 Procesando contenido de archivo: {filename} ({ext}) para proyecto: {project_id}")
        
        source_id = self._create_source(project_id, ext, filename, file_url=file_url)
        
        try:
            metadata = {"source": filename, "type": ext, "project_id": project_id}
            if file_url:
                metadata["file_url"] = file_url

            if ext == 'txt':
                text_content = file_content.decode('utf-8')
                self._split_and_store(text_content, metadata)
                del text_content
            elif ext == 'pdf':
                import io
                reader = PdfReader(io.BytesIO(file_content))
                
                # Para evitar OOM en archivos grandes de cientos de páginas, dividimos el procesamiento
                pages_batch = []
                for i, page in enumerate(reader.pages):
                    pages_batch.append(page.extract_text() + "\n")
                    
                    if len(pages_batch) >= 15 or i == len(reader.pages) - 1:
                        batch_text = "".join(pages_batch)
                        if batch_text.strip():
                            self._split_and_store(batch_text, metadata)
                        pages_batch = []
                        gc.collect()
                del reader
            elif ext == 'csv':
                import io
                df = pd.read_csv(io.BytesIO(file_content))
                text_content = df.to_string()
                self._split_and_store(text_content, metadata)
                del df
                del text_content
            else:
                print(f"Formato no soportado: {ext}")
                self._update_source_status(source_id, "error")
                return
                
            del file_content
            gc.collect()
            
            self._update_source_status(source_id, "indexed")
            
        except Exception as e:
            print(f"❌ Error CRÍTICO procesando {filename}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            import logging
            logging.getLogger("uvicorn.error").error(f"Error procesando documento {filename}: {e}\n{traceback.format_exc()}")
            self._update_source_status(source_id, "error")
            del file_content
            gc.collect()
    def process_text(self, text: str, project_id: str = "default", split: bool = True):
        """Recibe texto libre y lo envía a la base vectorial"""
        if not text.strip():
            print("❌ Texto vacío, nada que procesar.")
            return
            
        print(f"✍️ Procesando texto libre para proyecto: {project_id} (Split={split})")
        
        snippet = str(text)[:30] + "..." if len(text) > 30 else text
        source_id = self._create_source(project_id, "text", f"Texto Manual: {snippet}")
        
        try:
            metadata = {"source": "manual_input", "type": "text", "project_id": project_id}
            
            if split:
                self._split_and_store(text, metadata)
            else:
                from langchain_core.documents import Document
                doc = Document(page_content=text, metadata=metadata)
                self.vector_store.add_documents([doc])
                print(f"✅ 1 documento integro guardado en la BD Vectorial.")
                
            self._update_source_status(source_id, "indexed")
        except Exception as e:
            import traceback
            import sys
            import logging
            logging.getLogger("uvicorn.error").error(f"Error procesando texto manual: {e}\n{traceback.format_exc()}")
            self._update_source_status(source_id, "error")

    def _split_and_store(self, text: str, metadata: dict):
        """Divide el texto en chunks y los guarda en ChromaDB"""
        import gc
        chunks = self.text_splitter.create_documents([text], metadatas=[metadata])
        
        # Free up the large raw string now that chunks are created
        del text
        gc.collect()
        
        # Add to vector store in smaller batches to avoid RAM spike in Free Tier
        batch_size = 20
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i+batch_size]
            self.vector_store.add_documents(batch)
            
            # Explicitly force GC for the model inference memory
            del batch
            gc.collect()

        print(f"✅ {len(chunks)} fragmentos guardados en la BD Vectorial.")
        del chunks
        gc.collect()

