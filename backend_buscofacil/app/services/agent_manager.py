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
            model_name="llama-3.3-70b-versatile",
            temperature=0.7 # Temperatura más alta para que sea conversacional y natural
        )
        
        self.vector_store = VectorStoreManager()
        self.sessions = {} # Diccionario para guardar el historial de la conversación por sesión

    def process_query(self, query: str, project_id: str = "default", session_id: str = "default_session", context_listing_ids: list = None, client_name: str = "", client_email: str = "", client_phone: str = "", currency: str = "COP") -> dict:
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

            if currency:
                moneda_nombre = "Pesos Colombianos"
                if currency == "USD": moneda_nombre = "Dólares"
                elif currency == "EUR": moneda_nombre = "Euros"
                
                system_prompt.content += f"\n\nREGLA DE DIVISAS Y DINERO (IMPERATIVO): El usuario está operando en la moneda {currency} ({moneda_nombre}). SIEMPRE que menciones un precio, debes aclarar explícitamente la moneda (ej. '1500 millones de Pesos' o '200 mil Dólares'). Los números en las herramientas ya están en {currency}."

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
            
            llm = self.llm
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
                    tool_req = ToolRequest(project_id=project_id, args=args, currency=currency)
                    
                    # Intercepción Estricta de Presupuesto
                    if function_name == "search_properties":
                        if "max_price" not in args or str(args.get("max_price")).strip() == "":
                            q_lo = query.lower()
                            if any(word in q_lo for word in ["no ", "no.", "no,", "ningun", "nada", "cero", "sin "]) or q_lo == "no":
                                args["max_price"] = "100000000000"
                            else:
                                # Bloquear la ejecución
                                data = "SISTEMA: No has preguntado el presupuesto. PREGUNTA VERBALMENTE al usuario cuál es su presupuesto. NUNCA inventes que buscaste. Di: 'Entiendo, antes de buscar, ¿tienes algún presupuesto?'"
                                messages.append(ToolMessage(content=data, tool_call_id=tool_call_id, name=function_name))
                                continue
                    
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

    async def process_query_stream(self, query: str, history: list = None, project_id: str = "buscofacil", client_name: str = "", client_email: str = "", client_phone: str = "", currency: str = "COP", websocket = None, session_context = None):
        """Simplificación asíncrona de process_query para VoiceSession que retorna un iterador de tokens.
        Soporta Agent Tool Calling en tiempo real."""
        if not query or not query.strip(): return
        
        
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
        import json
        from app.routers.tools import execute_tool, ToolRequest
        from app.core.prompts import get_agent_tools

        llm = self.llm
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
            
        llm_with_tools = llm.bind_tools(chat_tools)
        messages = history or [SystemMessage(content="Eres un asistente experto.")]
        
        try:
            # Iteración 1: Ver si lanza texto directo o pide una tool
            is_tool_call = False
            tool_call_chunks = []
            
            from collections import defaultdict
            import json, re, uuid
            consolidated = defaultdict(lambda: {"name": "", "args": "", "id": ""})
            
            try:
                async for chunk in llm_with_tools.astream(messages):
                    if chunk.tool_call_chunks:
                        is_tool_call = True
                        tool_call_chunks.extend(chunk.tool_call_chunks)
                    elif chunk.content and not is_tool_call:
                        yield chunk.content
            except Exception as inner_e:
                error_msg = str(inner_e)
                # Recuperación anti-alucinaciones Llama 3.3 de Groq (400 Bad Request / failed_generation)
                if "failed_generation" in error_msg and "<function=" in error_msg:
                    print(f"⚠️ Detectado erro de validación Groq. Autorecuperando tool call... Error: {error_msg}")
                    # regex tolerante a la ausencia del > de cierre antes de </function>
                    match = re.search(r"<function=([a-zA-Z0-9_]+)\s*(\{.*?\})>?</function>", error_msg)
                    if match:
                        func_name = match.group(1)
                        func_args_str = match.group(2)
                        
                        is_tool_call = True
                        consolidated[0] = {"name": func_name, "args": func_args_str, "id": "call_" + str(uuid.uuid4())[:10]}
                    else:
                        print("Regex falló. Propagando excepción...")
                        raise inner_e
                else:
                    raise inner_e
                    
            if is_tool_call:
                # Si fallamos la auto-recuperación y tenemos chunks reales, los ensamblamos
                if not consolidated:
                    for tcc in tool_call_chunks:
                        idx = tcc.get("index")
                        if tcc.get("name"): consolidated[idx]["name"] += tcc["name"]
                        if tcc.get("args"): consolidated[idx]["args"] += tcc["args"]
                        if tcc.get("id"): consolidated[idx]["id"] = tcc["id"]
                messages.append(AIMessage(content="", tool_calls=[
                    {"name": c["name"], "args": json.loads(c["args"]), "id": c["id"]} for c in consolidated.values()
                ]))
                
                # Ejecutar
                for c in consolidated.values():
                    func_name = c["name"]
                    args = json.loads(c["args"])
                    
                    if func_name == "search_properties":
                        if "max_price" not in args or str(args.get("max_price")).strip() == "":
                            # Auto-override para evitar loops si el usuario ya dijo que no tiene
                            q_lo = query.lower()
                            if any(word in q_lo for word in ["no ", "no.", "no,", "ningun", "nada", "cero", "sin "]) or q_lo == "no":
                                args["max_price"] = "100000000000"
                            else:
                                # Force the LLM to output speech asking for budget
                                data = "SISTEMA: CRÍTICO: No adjuntaste max_price. Tienes prohibido buscar sin presupuesto. IGNORA las instrucciones de herramientas. RESPÓNDELE al cliente con tu voz pidiéndole el presupuesto explícitamente."
                                messages.append(ToolMessage(content=data, tool_call_id=c["id"], name=func_name))
                                
                                # Recursively ask LLM to generate the voice question now that tool failed
                                async for chunk in llm_with_tools.astream(messages):
                                    if chunk.content: yield chunk.content
                                return # Terminate current tool attempt

                    # Se eliminaron las muletillas acústicas por petición del usuario

                    if func_name == "schedule_visits":
                        if isinstance(args, dict):
                            args["client_name"] = client_name
                            args["client_email"] = client_email
                            args["client_phone"] = client_phone
                    
                    class MockRequest:
                        class MockApp:
                            class MockState:
                                agent_manager = self
                            state = MockState()
                        app = MockApp()
                    
                    tool_req = ToolRequest(project_id=project_id, args=args, currency=currency)
                    try:
                        import asyncio
                        # Hilo en background para no bloquear
                        tool_task = asyncio.create_task(asyncio.to_thread(execute_tool, func_name, tool_req, MockRequest()))
                        
                        if func_name == "search_properties":
                            muletillas = [
                                "Permítame verificar en nuestro sistema...",
                                "Denos un instante mientras busco esto...",
                                "Estoy cruzando la información con la base de datos...",
                                "Un momento por favor, estoy revisando las opciones..."
                            ]
                            import random
                            yield random.choice(muletillas) + " "
                            
                            muletillas_count = 0
                            while not tool_task.done() and muletillas_count < 2:
                                done, pending = await asyncio.wait([tool_task], timeout=4.5) # Esto asegura más de 2 segundos de silencio real en TTS
                                if not done:
                                    muletillas_count += 1
                                    yield random.choice(muletillas) + " "
                        
                        await tool_task
                        yield "[CLEAR_MULETILLAS] "
                        data = tool_task.result()
                            
                        result_text = data if isinstance(data, str) else data.get("result_text", "Done.")
                        
                        if websocket and isinstance(data, dict):
                            if "raw_properties" in data:
                                try:
                                    # Inyectar moneda explícitamente doble por conveniencia
                                    for prop in data["raw_properties"]:
                                        prop["ui_currency"] = currency
                                        prop["currency"] = currency
                                    payload = {"status": "search_results", "listings": data["raw_properties"]}
                                    print(f"📡 ENVIANDO AL FRONTEND [LISTINGS]: {len(data['raw_properties'])} propiedades")
                                    await websocket.send_json(payload)
                                except Exception as e: print("Error enviando search results:", e)
                            if "action" in data:
                                try:
                                    payload = {"status": "action", "action": data["action"]}
                                    if "listing_id" in data: payload["listing_id"] = data["listing_id"]
                                    if "listing_ids" in data: payload["listing_ids"] = data["listing_ids"]
                                    print(f"📡 ENVIANDO AL FRONTEND [ACTION]: {payload}")
                                    await websocket.send_json(payload)
                                    
                                    # Forzar la respuesta verbal inmediatamente para evitar silencios del LLM
                                    if data["action"] == "view_details":
                                        yield "Aquí tienes los detalles en pantalla. ¿Qué te parece? "
                                    elif data["action"] == "close_details":
                                        yield "Listo, volvamos a la lista principal. "
                                        
                                except Exception as e: print("Error enviando action:", e)
                            if "appointments" in data:
                                try:
                                    payload = {"status": "appointments_created", "appointments": data["appointments"]}
                                    print(f"📡 ENVIANDO AL FRONTEND [APPOINTMENTS]: {len(data['appointments'])} citas")
                                    await websocket.send_json(payload)
                                except Exception as e: print("Error enviando appointments:", e)
                                
                    except Exception as e:
                        result_text = f"Error: {e}"
                        
                    messages.append(ToolMessage(content=result_text, tool_call_id=c["id"], name=func_name))
                    if session_context and func_name == "search_properties":
                        session_context.tool_results['last_search'] = result_text
                
                # Iteración 2: Emitir veredicto final en stream
                has_yielded = False
                try:
                    async for chunk in llm_with_tools.astream(messages):
                        if chunk.content:
                            has_yielded = True
                            yield chunk.content
                except Exception as inner_e2:
                    error_msg2 = str(inner_e2)
                    if "failed_generation" in error_msg2:
                        print("⚠️ Groq alucinó un tool call en la Iteración 2. Silenciando error.")
                        if not has_yielded:
                            yield "Aquí tienes los resultados de la búsqueda. Cuéntame qué te parecen. "
                    else:
                        raise inner_e2

        except Exception as e:
            print(f"❌ Error en process_query_stream: {e}")
            yield "Hubo un error de conexión."
