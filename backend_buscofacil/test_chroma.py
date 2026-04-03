import sys
import os

# Agrega la ruta base del proyecto al path para que Python encuentre 'app'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.vector_store import VectorStoreManager

store = VectorStoreManager(persist_directory=".chroma_db")
retriever = store.get_retriever(k=4, project_id="buscofacil")

query = "apartamento en cali"
docs = retriever.invoke(query)
print(f"Results for '{query}': {len(docs)}")
for d in docs:
    print(d.metadata)
    print(d.page_content)
    print("-----")
