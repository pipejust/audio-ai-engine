import asyncio
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.services.agent_manager import AgentManager

async def test():
    am = AgentManager()
    retriever = am.vector_store.get_retriever(k=400, project_id="buscofacil")
    sq = "propiedades disponibles inmueble tipo apartemento en Cali, Ciudad Jardín que pertenezcan a la zona geográfica exacta: 'ciudad jardin' es el barrio Ciudad Jardín de la Comuna 22, pertenece a la zona Sur en la ciudad de Cali, departamento de Valle del Cauca."
    raw_docs = retriever.invoke(sq)
    print("Found docs:", len(raw_docs))
    seen = set()
    for d in raw_docs:
        p_id = d.metadata.get("property_id")
        if p_id not in seen:
            seen.add(p_id)
            print("ID:", p_id, "Type:", d.metadata.get("property_type"), "Loc:", d.metadata.get("location_search"))
        
asyncio.run(test())
