import os
import sqlite3
import pandas as pd
from app.services.vector_store import VectorStoreManager
from app.services.ingestion.multi_format import MultiFormatIngestor

def setup_mock_db():
    print("Preparando Mock DB...")
    db_path = "data/mock_properties.db"
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            city TEXT,
            price INTEGER
        )
    ''')
    cursor.execute("INSERT INTO properties (title, city, price) VALUES ('Apartamento Bonito', 'Bogota', 300000000)")
    cursor.execute("INSERT INTO properties (title, city, price) VALUES ('Casa Grande', 'Medellin', 500000000)")
    conn.commit()
    conn.close()
    return db_path

def run_ingestion_test():
    print("Iniciando prueba de ingesta multi-formato...")
    
    # Init Vector Store
    vector_store = VectorStoreManager(persist_directory=".chroma_db_test")
    
    # Init Ingestor
    ingestor = MultiFormatIngestor(vector_store)
    
    # Test SQLite Ingestion
    db_path = setup_mock_db()
    ingestor.process_sqlite(db_path)
    
    # Mock CSV Ingestion
    csv_path = "data/mock_knowledge.csv"
    with open(csv_path, "w") as f:
        f.write("question,answer\n")
        f.write("¿Cuáles son los horarios de atención?,De Lunes a Viernes de 8am a 6pm\n")
        f.write("¿Qué pasa si quiero rentar mi casa?,Contáctanos y te ayudamos a arrendarla por el 10%\n")
        
    ingestor.process_file(csv_path)
    print("Prueba finalizada.")

if __name__ == "__main__":
    run_ingestion_test()
