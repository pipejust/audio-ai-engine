import asyncio
from dotenv import load_dotenv
load_dotenv()

import os
import sys

# Ensure root dir is available
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.services.agent_manager import AgentManager

async def test():
    am = AgentManager()
    
    # Simulate DB resolver
    from db_colombia import setup_database, resolver_ubicacion
    conn = setup_database()
    resolved = resolver_ubicacion("ciudad jardin", conn)
    conn.close()
    
    print("Resolved:", resolved)
    
    retriever = am.vector_store.get_retriever(k=50, project_id="buscofacil")
    sq = f"propiedades disponibles inmuebles tipo apartemento en ciudad jardin cali que pertenezcan a la zona geográfica exacta: {resolved}"
    print("Search Query:", sq)
    
    raw_docs = retriever.invoke(sq)
    print(f"Total raw docs for ciudad jardin: {len(raw_docs)}")
    
    for d in raw_docs[:5]:
        print("ID:", d.metadata.get("property_id"), d.metadata.get("property_type"), d.metadata.get("location_search"))
        
asyncio.run(test())
