import asyncio
import os
from app.services.vector_store import VectorStoreManager
from app.services.ingestion.multi_format import MultiFormatIngestor

async def main():
    print("Inicializando VectorStore...")
    vs = VectorStoreManager()
    ingestor = MultiFormatIngestor(vs)
    
    print("Leyendo PDF...")
    with open("large_test.pdf", "rb") as f:
        content = f.read()
        
    print("Llamando a process_file_content...")
    # This runs synchronously in the background task
    ingestor.process_file_content(
        file_content=content,
        filename="large_test.pdf",
        ext="pdf",
        project_id="test_large_pdf"
    )
    print("Proceso terminado.")

if __name__ == "__main__":
    asyncio.run(main())
