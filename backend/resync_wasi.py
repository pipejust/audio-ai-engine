import sys
import os

# Agrega la ruta base del proyecto al path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.vector_store import VectorStoreManager
from app.services.ingestion.multi_format import MultiFormatIngestor
from app.services.wasi_api import WasiAPI

print("Limpiando colección anterior...")
store = VectorStoreManager()
try:
    store.client.delete_collection(name=store.collection_name)
    print("Colección eliminada exitosamente.")
except Exception as e:
    print(f"La colección no existía o error al eliminar: {e}")

# Recrear
print("Recreando instancia y colección...")
store = VectorStoreManager()
ingestor = MultiFormatIngestor(store)
wasi = WasiAPI()

print("Descargando de Wasi...")
all_properties = []
skip = 0
take = 50

while True:
    print(f"Obteniendo lote de propiedades (take={take}, skip={skip})...")
    properties = wasi.search_properties(take=take, skip=skip)
    
    if not properties:
        break
        
    all_properties.extend(properties)
    skip += take
    
    # Si Wasi retorna menos propiedades de las que pedimos, es el último lote
    if len(properties) < take:
        break

print(f"Se descargaron un total de {len(all_properties)} propiedades de Wasi.")

print(f"Ingestando {len(all_properties)} propiedades ENTERAS sin split...")
for prop in all_properties:
    formatted_data = wasi.format_property_for_rag(prop)
    if formatted_data and "text" in formatted_data:
        text = formatted_data["text"]
        metas = formatted_data["metadata"]
        metas["project_id"] = "buscofacil" # Para que Chroma asigne el proyecto base
        
        # En vez de llamar a process_text que no soporta metadata adicional fácilmente, usamos store_manager
        from langchain_core.documents import Document
        doc = Document(page_content=text, metadata=metas)
        store.add_documents([doc])

print("¡Sincronización completa!")
