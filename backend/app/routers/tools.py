from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(tags=["Tools"])

class ToolRequest(BaseModel):
    project_id: str
    args: Dict[str, Any]

@router.post("/{function_name}")
async def execute_tool(function_name: str, request_data: ToolRequest, request: Request):
    """
    Endpoint dinámico para ejecutar herramientas.
    Este endpoint simula los Web Services externos para cada tenant.
    """
    # Obtenemos agent_manager desde request.app.state o importándolo, pero aquí usamos
    # el global de main.py mediante un getter simple o import deferido si es necesario.
    # Dado que es mejor inyectarlo o accederlo vía app.state:
    agent_manager = request.app.state.agent_manager
    project_id = request_data.project_id
    args = request_data.args
    
    if function_name == "consult_knowledge_base":
        query = args.get("query", "")
        retriever = agent_manager.vector_store.get_retriever(k=3, project_id=project_id)
        docs = retriever.invoke(query)
        context_text = "\\n".join([d.page_content for d in docs]) if docs else "No information matches the query."
        return {"status": "success", "result_text": context_text}
        
    elif function_name == "search_properties":
        location = args.get("location", "any")
        tipo = args.get("property_type", "any")
        limit = args.get("limit", 15)
        
        search_query = f"propiedades disponibles inmueble"
        if tipo.lower() != "any": search_query += f" tipo {tipo}"
        if location.lower() != "any": search_query += f" en {location}"
        
        safe_limit = min(int(limit), 20)
        
        retriever = agent_manager.vector_store.get_retriever(k=80, project_id=project_id)
        raw_docs = retriever.invoke(search_query)
        
        filtered_docs = []
        if raw_docs:
            for d in raw_docs:
                meta_loc = d.metadata.get("location_search", "")
                meta_type = d.metadata.get("property_type", "")
                
                if location.lower() != "any" and location.lower() not in meta_loc and location.lower() not in d.page_content.lower():
                    continue
                if tipo.lower() != "any" and tipo.lower() not in meta_type and tipo.lower() not in d.page_content.lower():
                    continue
                    
                filtered_docs.append(d)
                if len(filtered_docs) >= safe_limit:
                    break
        
        if filtered_docs:
            result_text = f"RESULTADO DE BASE DE DATOS: Encontré las siguientes opciones de {tipo} en {location}:\\n"
            for i, d in enumerate(filtered_docs):
                snippet = d.page_content[:350] + "..." if len(d.page_content) > 350 else d.page_content
                result_text += f"\\n[{i+1}] {snippet}\\n"
            result_text += "\\nREGLA: Describe estas opciones de forma atractiva. Diles el precio y barrio."
        else:
            result_text = f"Revisé la base de datos extensamente pero NO hay ningún inmueble tipo {tipo} disponible en el sector de {location}. Infórmale esto de inmediato."
            
        return {"status": "success", "result_text": result_text}
        
    elif function_name == "schedule_appointment":
        name = args.get("client_name")
        pid = args.get("property_id")
        mock_result = f"Perfect! I have scheduled an appointment for {name} to see {pid}. A confirmation SMS was just sent."
        return {"status": "success", "result_text": mock_result}
        
    elif function_name == "generate_software_quote":
        name = args.get("client_name")
        email = args.get("client_email")
        mock_result = f"Great {name}, I have just generated the formal quote and sent the PDF to {email}. It looks very promising!"
        return {"status": "success", "result_text": mock_result}
        
    else:
        raise HTTPException(status_code=404, detail="Tool not found")
