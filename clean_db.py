import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend/.env')))

# Ajustar PYTHONPATH para que app referencie a backend/app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from app.db.session import SessionLocal
from app.db.models import TrainingSource
from app.services.vector_store import VectorStoreManager

def main():
    db = SessionLocal()
    
    # Buscar registros en sqlite donde el project_id sea "buscofacil" y el source_name contenga "Investigacion" o "xkape" o "TI" (de "cotizaciones de TI")
    print("Buscando registros sospechosos en SQLite (Buscofacil)...")
    records = db.query(TrainingSource).filter(
        TrainingSource.project_id == 'buscofacil'
    ).all()
    
    to_delete = []
    for r in records:
        name_lower = r.source_name.lower()
        if 'investigaci' in name_lower or 'xkape' in name_lower or 'ti' in name_lower or 'cotizacion' in name_lower:
            to_delete.append(r)
    
    print(f"Encontrados {len(to_delete)} registros a borrar en SQLite.")
    for r in to_delete:
        print(f" - [{r.id}] {r.source_name}")
    
    if not to_delete:
        print("No hay nada que borrar.")
        return
        
    vs = VectorStoreManager()
    
    for r in to_delete:
        # Borrar de ChromaDB basado en metadata (project_id + source)
        try:
            if vs.vectorstore:
                print(f"Borrando chunks de ChromaDB para source={r.source_name}")
                # En chromadb, get() nos da los IDs filtrando por metadata
                collection = getattr(vs.vectorstore, '_collection', None)
                if collection:
                    results = collection.get(where={"$and": [{"project_id": r.project_id}, {"source": r.source_name}]})
                    if results and results['ids']:
                        collection.delete(ids=results['ids'])
                        print(f"  > {len(results['ids'])} vectores eliminados.")
                    else:
                        print("  > No se encontraron vectores asociados.")
                else:
                    print("  > No se pudo acceder a la coleccion de ChromaDB")
        except Exception as e:
            print(f"Error borrando de ChromaDB: {e}")
            
        print(f"Borrando de SQLite: {r.source_name}")
        db.delete(r)
        
    db.commit()
    print("Limpieza completada.")

if __name__ == '__main__':
    main()
