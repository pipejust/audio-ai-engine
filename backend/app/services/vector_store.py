import os
try:
    from langchain_community.vectorstores.pgvector import PGVector
    from langchain_openai import OpenAIEmbeddings
    HAS_ML = True
except ImportError:
    HAS_ML = False

class VectorStoreManager:
    def __init__(self, persist_directory: str = None):
        is_vercel = os.getenv("VERCEL") == "1"
        if is_vercel:
            os.environ["HF_HOME"] = "/tmp/huggingface"
            os.environ["TRANSFORMERS_CACHE"] = "/tmp/huggingface"
        
        if not HAS_ML:
            print("⚠️ Ejecutando sin dependencias ML (Vercel). VectorStore desactivado.")
            self.vectorstore = None
            return

        print("Cargando modelo de Embeddings (OpenAI API)...")
        openai_key = os.getenv("OPENAI_API_KEY")
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=openai_key,
            model="text-embedding-3-small"
        )
        
        db_url = os.getenv("DATABASE_URL")
        if db_url and db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        self.collection_name = "audio_rag_knowledge_oai"
        
        try:
            self.vectorstore = PGVector(
                connection_string=db_url,
                embedding_function=self.embeddings,
                collection_name=self.collection_name,
                use_jsonb=False, # Changed to False because Supabase fails with jsonb_path_match
                engine_args={"pool_pre_ping": True, "pool_recycle": 3600}
            )
            print("✅ Conectado a PGVector en Supabase.")
        except Exception as e:
            print(f"❌ Error conectando a PGVector: {e}")
            self.vectorstore = None

    def add_documents(self, chunks):
        """Agrega chunks de texto a la base de datos vectorial"""
        if not self.vectorstore:
            print("⚠️ VectorStore desactivado, ignorando add_documents.")
            return
            
        print(f"Ingestando {len(chunks)} chunks en PGVector...")
        self.vectorstore.add_documents(chunks)
        print("Ingesta completada.")

    def get_retriever(self, k=4, project_id: str = "default", exact_location: str = None):
        """Retorna el recuperador de información para usar en la cadena RAG filtrado por proyecto usando MMR y filtros exactos"""
        if not self.vectorstore:
            print("⚠️ VectorStore desactivado. Retornando None.")
            class MockRetriever:
                def invoke(self, query):
                    return []
            return MockRetriever()
            
        # Base filter by project ID
        filter_dict = {"project_id": project_id}
            
        search_kwargs = {
            "k": k, 
            "fetch_k": k * 4, # Fetches more documents before filtering with MMR para dar mucha más variedad
            "filter": filter_dict
        }
        # search_type="mmr" ensures we get diverse results instead of just the top closest ones
        return self.vectorstore.as_retriever(search_type="mmr", search_kwargs=search_kwargs)

