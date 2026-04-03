import sys
import os

# Agrega la ruta base del proyecto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.vector_store import VectorStoreManager

store = VectorStoreManager(persist_directory=".chroma_db")
retriever = store.get_retriever(k=4, project_id="buscofacil")

queries = [
    "casa de mas de dos habitaciones en ciudad jardín",
    "casa ciudad jardín",
    "apartamento 3 habitaciones"
]

for q in queries:
    print(f"\n--- Query: '{q}' ---")
    docs = retriever.invoke(q)
    print(f"Resultados: {len(docs)}")
    for d in docs:
        print(d.page_content.split('\n')[1]) # Print Title
