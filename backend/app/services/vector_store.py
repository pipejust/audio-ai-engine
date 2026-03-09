import os
import chromadb
from chromadb.config import Settings
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

class VectorStoreManager:
    def __init__(self, persist_directory: str = None):
        is_vercel = os.getenv("VERCEL") == "1"
        if is_vercel:
            os.environ["HF_HOME"] = "/tmp/huggingface"
            os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface"
        
        if persist_directory is None:
            if is_vercel:
                self.persist_directory = "/tmp/.chroma_db"
            else:
                # Forzamos que la bd siempre se instancie dentro de la carpeta 'backend'
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                self.persist_directory = os.path.join(base_dir, ".chroma_db")
        else:
            self.persist_directory = persist_directory
            
        # Uso de embeddings locales y gratuitos (rápidos para pruebas)
        # BAAI/bge-small-en-v1.5 u 'all-MiniLM-L6-v2' son excelentes para RAG ligero.
        print("Cargando modelo de Embeddings (Local)...")
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Inicialización de Chroma
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection_name = "audio_rag_knowledge"
        
        self.vectorstore = Chroma(
            client=self.client,
            collection_name=self.collection_name,
            embedding_function=self.embeddings
        )

    def add_documents(self, chunks):
        """Agrega chunks de texto a la base de datos vectorial"""
        print(f"Ingestando {len(chunks)} chunks en ChromaDB...")
        self.vectorstore.add_documents(chunks)
        print("Ingesta completada.")

    def get_retriever(self, k=4, project_id: str = "default", exact_location: str = None):
        """Retorna el recuperador de información para usar en la cadena RAG filtrado por proyecto usando MMR y filtros exactos"""
        
        # Base filter by project ID
        filter_dict = {"project_id": project_id}
            
        search_kwargs = {
            "k": k, 
            "fetch_k": k * 4, # Fetches more documents before filtering with MMR para dar mucha más variedad
            "filter": filter_dict
        }
        # search_type="mmr" ensures we get diverse results instead of just the top closest ones
        return self.vectorstore.as_retriever(search_type="mmr", search_kwargs=search_kwargs)
