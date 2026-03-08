import os
import traceback
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from app.services.vector_store import VectorStoreManager
from app.core.prompts import get_agent_instructions

class AgentManager:
    def __init__(self):
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            print("⚠️ ADVERTENCIA: GROQ_API_KEY no encontrada.")
            
        self.bot_name = os.getenv("BOT_NAME", "Felipe")
        self.company_name = os.getenv("COMPANY_NAME", "Softnexus")
            
        # El modelo LLM que funciona como cerebro del agente
        self.llm = ChatGroq(
            groq_api_key=groq_api_key,
            model_name="llama-3.1-8b-instant",
            temperature=0.7 # Temperatura más alta para que sea conversacional y natural
        )
        
        self.vector_store = VectorStoreManager()
        self.sessions = {} # Diccionario para guardar el historial de la conversación por sesión

    def process_query(self, query: str, project_id: str = "default", session_id: str = "default_session") -> dict:
        """Envía un prompt al modelo y retorna la respuesta."""
        if not query or not str(query).strip():
            return {"response": "", "status": "ignored"}
            
        print(f"🤖 Agente procesando: '{query}' para proyecto: '{project_id}'")
        
        try:
            if query == "system_greeting_trigger":
                # Saludo proactivo inicial siempre en español
                prompt_text = f"El usuario acaba de abrir la aplicación y conectarse. Es imperativo que tu primer respuesta sea EXACTAMENTE Y SIN AGREGAR NADA MÁS: 'Mucho gusto mi nombre es {self.bot_name} de {self.company_name} y te ayudaré con lo que necesites.'"
                # 1. Recuperar contexto (RAG) usando la consulta completa para atrapar semántica real
                print(f"🔍 Búsqueda RAG sobre query original: {query}")
                retriever = self.vector_store.get_retriever(k=6, project_id=project_id)
                docs = retriever.invoke(query)
                
                # deduplicar documentos por contenido para evitar repeticiones
                unique_docs = []
                seen_content = set()
                for d in docs:
                    if d.page_content not in seen_content:
                        unique_docs.append(d)
                        seen_content.add(d.page_content)
                
                num_docs = len(unique_docs)
                
                context_text = f"RESULTADOS ENCONTRADOS EN BASE DE DATOS: {num_docs} propiedades.\n\n"
                context_text += "\n".join([d.page_content for d in unique_docs]) if unique_docs else "No hay propiedades que coincidan."

                prompt_text = (
                    f"User message: \"{query}\"\n\n"
                    f"Context provided from database (Use this to answer if relevant):\n{context_text}\n\n"
                    "-> YOUR MANDATORY RULE: Reply to the above message in the EXACT SAME LANGUAGE it was written in. Do not use any other language."
                )

            # Cargar instrucciones dinámicas según el proyecto
            dynamic_instructions = get_agent_instructions(project_id, self.bot_name, self.company_name)
            system_prompt = SystemMessage(content=dynamic_instructions)
            
            # Cargar historial de la sesión
            if session_id not in self.sessions:
                self.sessions[session_id] = []
            history = self.sessions[session_id][-50:] # Mantener últimos 50 mensajes
            
            messages = [system_prompt] + history + [("human", prompt_text)]
            response = self.llm.invoke(messages)
            
            # Guardar en memoria: query pura (sin chunk RAG completo) y su respuesta
            if query != "system_greeting_trigger":
                self.sessions[session_id].append(("human", query))
                self.sessions[session_id].append(("ai", response.content))
            
            return {
                "response": response.content,
                "status": "success"
            }
                
        except Exception as e:
            print(f"❌ Error en AgentManager:")
            traceback.print_exc()
            return {
                "response": "Lo siento, mi motor de agentes tuvo un inconveniente.",
                "status": "error"
            }
