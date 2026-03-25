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

    def process_query(self, query: str, project_id: str = "default", session_id: str = "default_session", context_listing_ids: list = None, client_name: str = "", client_email: str = "", client_phone: str = "") -> dict:
        """Envía un prompt al modelo y maneja Tool Calling para que Text Chat y Voice AI sean idénticos."""
        if not query or not str(query).strip():
            return {"response": "", "status": "ignored"}
            
        print(f"🤖 Text Agent procesando: '{query}' para proyecto: '{project_id}'")
        
        try:
            if query == "system_greeting_trigger":
                instant_response = f"Mucho gusto mi nombre es {self.bot_name} de {self.company_name} y te ayudaré con lo que necesites."
                return {
                    "response": instant_response,
                    "status": "success"
                }

            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
            from app.core.prompts import get_agent_tools
            from app.routers.tools import execute_tool, ToolRequest
            import json

            # 1. Cargar las mismas Instrucciones que el Bot de Voz
            dynamic_instructions = get_agent_instructions(project_id, self.bot_name, self.company_name)
            system_prompt = SystemMessage(content=dynamic_instructions)
            
            if client_name or client_phone:
                system_prompt.content += f"\n\nREGLA DE CONTEXTO: OBLIGATORIO LEER.\nEl sistema te informa que estás atendiendo al usuario: {client_name}, Teléfono: {client_phone}.\nComo ya tienes estos datos, TIENES STRICTAMENTE PROHIBIDO preguntar su nombre o teléfono. Si el usuario te pide agendar, EJECUTA LA HERRAMIENTA DE AGENDAMIENTO INMEDIATAMENTE e INYECTA estos datos directamente en el JSON de 'appointments'. Cero preguntas."
            else:
                system_prompt.content += "\n\nREGLA DE CONTACTO: Eres un invitado anónimo. Antes de emitir el JSON final de 'appointments', SIEMPRE pregunta amablemente al cliente: '¿A qué nombre y número de celular dejo registrada la visita?'. Una vez que el usuario los proporcione, debes emitir esos datos exactos e inyectarlos localmente en el arreglo JSON de la respuesta usando las llaves 'client_name' y 'client_phone'. Si el usuario se niega a darlos o dice 'usa mi perfil', envía ''."

            if context_listing_ids:
                # Inyección instantánea (Cero latencia) del orden visual exacto
                mapping_text = "\n".join([f"Propiedad #{i+1}: ID [{pid}]" for i, pid in enumerate(context_listing_ids)])
                system_prompt.content += f"\n\n[MAPEO VISUAL EN PANTALLA]:\nEste es el orden cronológico exacto de las casas que el cliente está viendo ahora mismo:\n{mapping_text}\n(Usa estrictamente estos IDs referenciales si el usuario te pide ver 'la primera', 'la 3', 'esa última', etc.)."
                
                try:
                    raw_docs = []
                    # Fetch perfect semantic data directly from PGVector. LIMIT to 2 items max to reduce latency on simple queries.
                    for pid in context_listing_ids[:2]:
                        docs_for_id = self.vector_store.vectorstore.similarity_search(
                            "propiedad", 
                            k=1, 
                            filter={"property_id": str(pid)}
                        )
                        raw_docs.extend(docs_for_id)
                        
                    if raw_docs:
                        context_text = "\n".join([f"ID[{d.metadata.get('property_id')}]: {d.page_content}" for d in raw_docs])
                        system_prompt.content += f"\n\nCONTEXTO VISUAL ACTUAL (Viendo en pantalla):\n{context_text}\n(EL USUARIO TE ESTÁ PREGUNTANDO DIRECTAMENTE SOBRE ESTAS PROPIEDADES. NO uses la herramienta 'search_properties' para buscar esto, confía en esta información para responder orgánicamente sus dudas)."
                except Exception as e:
                    print(f"Error cargando contexto visual de vector_store: {e}")
            
            print(f"--- DEBUG SYSTEM PROMPT ---\n{system_prompt.content}\n----------------------------")

            # 2. Cargar las mismas Tools pero adaptar schema Realtime -> ChatCompletion
            raw_tools = get_agent_tools(project_id)
            chat_tools = []
            for t in raw_tools:
                chat_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name"),
                        "description": t.get("description"),
                        "parameters": t.get("parameters", {})
                    }
                })

            # Volver a OpenAI: gpt-4o-mini para estabilidad ABSOLUTA en Function Calling JSON
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
            if chat_tools:
                llm = llm.bind_tools(chat_tools)

            # 3. Inicializar Historial
            if session_id not in self.sessions:
                self.sessions[session_id] = []
            
            # Limitar a los últimos 40 mensajes para no reventar contexto
            history = self.sessions[session_id][-40:]
            
            # 4. Iniciar la cadena de llamadas
            messages = [system_prompt] + history + [HumanMessage(content=query)]
            
            # 5. Bucle de Tool Calling
            max_iterations = 3
            all_raw_properties = []
            scheduled_appointments = []
            ui_action = None
            ui_listing_id = None
            
            for i in range(max_iterations):
                response = llm.invoke(messages)
                messages.append(response)

                tool_calls = getattr(response, "tool_calls", None)
                if not tool_calls and hasattr(response, "additional_kwargs"):
                    tool_calls = response.additional_kwargs.get("tool_calls", [])
                
                if not tool_calls:
                    # El LLM terminó de pensar y respondió en texto final
                    break

                # Ejecutar cada tool que el LLM solicitó
                for tool_call in tool_calls:
                    # Langchain newer versions dict format or older additional_kwargs format (which requires json loads)
                    import json
                    if isinstance(tool_call, dict) and "function" in tool_call:
                        # Formato antiguo de OpenAI
                        function_name = tool_call["function"]["name"]
                        args = json.loads(tool_call["function"]["arguments"])
                        tool_call_id = tool_call.get("id", "call_123")
                    else:
                        # Formato nuevo de LangChain
                        function_name = tool_call["name"]
                        args = tool_call["args"]
                        tool_call_id = tool_call.get("id", "call_123")
                    
                    if function_name == "schedule_visits":
                        if isinstance(args, dict):
                            args["client_name"] = client_name
                            args["client_email"] = client_email
                            args["client_phone"] = client_phone
                            
                    print(f"🛠️ LLM Text invoked tool: {function_name} with args: {args}")
                    
                    # Simular petición para ejecutar la misma lógica de los WebSockets
                    class MockState:
                        def __init__(self, am):
                            self.agent_manager = am
                    class MockApp:
                        def __init__(self, am):
                            self.state = MockState(am)
                    class MockRequest:
                        def __init__(self, am):
                            self.app = MockApp(am)
                    
                    mock_req = MockRequest(self)
                    tool_req = ToolRequest(project_id=project_id, args=args)
                    
                    try:
                        # Ejecución local síncrona
                        data = execute_tool(function_name, tool_req, mock_req)
                        if isinstance(data, str):
                            result_text = data
                        else:
                            result_text = data.get("result_text", "Done.")
                            if "raw_properties" in data:
                                all_raw_properties.extend(data["raw_properties"])
                            if "appointments" in data:
                                scheduled_appointments.extend(data["appointments"])
                            if "action" in data and data["action"] == "view_details":
                                ui_action = "view_details"
                                ui_listing_id = data.get("listing_id")
                    except Exception as e:
                        print(f"❌ Tool Error in Text Chat: {e}")
                        result_text = f"Error ejecutando la herramienta: {e}"

                    # Añadir la respuesta de la tool a la conversación
                    messages.append(ToolMessage(
                        content=result_text,
                        tool_call_id=tool_call_id,
                        name=function_name
                    ))

            final_text = response.content
            
            # 6. Guardar solo el turno final en memoria limpia para reanudar más fácil
            self.sessions[session_id].append(HumanMessage(content=query))
            self.sessions[session_id].append(AIMessage(content=final_text))
            
            result_payload = {
                "response": final_text,
                "status": "success",
                "listings": all_raw_properties
            }
            if ui_action:
                result_payload["action"] = ui_action
                result_payload["listing_id"] = ui_listing_id
                
            if scheduled_appointments:
                # Deduplicar arreglos en Python para evitar doble conteo si el LLM repite JSON items
                unique_appts = []
                seen_appts = set()
                for appt in scheduled_appointments:
                    # Crear hash unico basado en ID y fecha
                    unique_key = f"{appt.get('listing_id')}_{appt.get('date')}_{appt.get('time')}"
                    if unique_key not in seen_appts:
                        seen_appts.add(unique_key)
                        unique_appts.append(appt)
                        
                result_payload["appointments"] = unique_appts
                
            return result_payload
                
        except Exception as e:
            print(f"❌ Error en AgentManager: {e}")
            traceback.print_exc()
            return {
                "response": f"Lo siento, mi motor de texto tuvo un inconveniente: {str(e)}",
                "status": "error"
            }
