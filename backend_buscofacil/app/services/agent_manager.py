import os
import traceback
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from app.services.vector_store import VectorStoreManager
from app.core.prompts import get_agent_instructions

# Semilla fija para detección determinista (evita que el mismo texto dé idiomas distintos)
try:
    from langdetect import detect as _ld_detect, DetectorFactory
    DetectorFactory.seed = 0
    _HAS_LANGDETECT = True
except Exception:
    _HAS_LANGDETECT = False

# Wordsets amplios para detección heurística como segunda capa
_EN_WORDS = {
    "i", "you", "me", "my", "is", "are", "do", "what", "where", "how",
    "want", "find", "looking", "please", "house", "yes", "hello", "hi",
    "the", "a", "an", "and", "or", "not", "can", "will", "would", "should",
    "have", "has", "been", "need", "like", "get", "from", "with", "this",
    "that", "it", "we", "they", "he", "she", "if", "but", "so", "no",
    "ok", "okay", "sure", "great", "good", "apartment", "room", "price",
}
_ES_WORDS = {
    "yo", "tu", "tú", "me", "mi", "es", "son", "que", "qué", "donde",
    "dónde", "como", "cómo", "quiero", "busco", "por", "casa", "si", "sí",
    "hola", "el", "la", "los", "las", "un", "una", "y", "o", "no",
    "tengo", "necesito", "puedo", "puede", "hay", "está", "están", "para",
    "con", "del", "pero", "también", "más", "bien", "bueno", "gracias",
    "apartamento", "habitación", "precio", "cuanto", "cuánto", "quiero",
}


def _detect_language(text: str, session_id: str, session_languages: dict) -> str:
    """
    Detección de idioma multicapa con fallback robusto.
    1. langdetect con seed determinista (si disponible y texto > 2 palabras)
    2. Heurística de wordsets ampliados (capa de verificación)
    3. Persiste el idioma detectado en session_languages
    4. Fallback a español si no hay señal clara
    """
    text_clean = text.strip()
    words = set(text_clean.lower().replace(",", " ").replace(".", " ")
                .replace("?", " ").replace("!", " ").split())

    detected = None

    # Capa 1: langdetect (determinista)
    if _HAS_LANGDETECT and len(words) >= 2:
        try:
            result = _ld_detect(text_clean)
            if result in ("es", "en", "pt", "fr"):
                detected = "es" if result in ("es", "pt") else "en"
        except Exception:
            pass

    # Capa 2: heurística de palabras (verificación o fallback)
    en_count = len(words & _EN_WORDS)
    es_count = len(words & _ES_WORDS)

    if en_count >= 2 and en_count > es_count:
        detected = "en"
    elif es_count >= 2 and es_count > en_count:
        detected = "es"

    # Capa 3: persistir en sesión solo si hay señal clara
    if detected in ("es", "en"):
        session_languages[session_id] = detected

    return session_languages.get(session_id, "es")

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
        self.session_languages = {} # Persistir idioma por sesion

    def process_query(self, query: str, project_id: str = "default", session_id: str = "default_session", context_listing_ids: list = None, client_name: str = "", client_email: str = "", client_phone: str = "", currency: str = "COP") -> dict:
        """Envía un prompt al modelo y maneja Tool Calling para que Text Chat y Voice AI sean idénticos."""
        if not query or not str(query).strip():
            return {"response": "", "status": "ignored"}
            
        print(f"🤖 Text Agent procesando: '{query}' para proyecto: '{project_id}'")
        
        try:
            if query == "system_greeting_trigger":
                greeting_name = "Sol" if project_id == "buscofacil" else self.bot_name
                instant_response = f"Mucho gusto mi nombre es {greeting_name} de {self.company_name} y te ayudaré con lo que necesites."
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
            lang = _detect_language(query, session_id, self.session_languages)
            
            if lang == "en":
                query_with_directive = query + "\n\n[SYSTEM DIRECTIVE: Respond EXCLUSIVELY in English. DO NOT translate names of Colombian cities, but formulate your ENTIRE response in English. It is FORBIDDEN to respond in Spanish even if the user says a Spanish neighborhood.]"
            else:
                query_with_directive = query + "\n\n[DIRECTIVA DE SISTEMA: Responde EXCLUSIVAMENTE en Español, NUNCA en Inglés ni otro idioma. Prohibido usar etiquetas XML manuales.]"
                
            messages = [system_prompt] + history + [HumanMessage(content=query_with_directive)]
            
            # 5. Bucle de Tool Calling
            max_iterations = 3
            all_raw_properties = []
            scheduled_appointments = []
            ui_action = None
            ui_listing_id = None
            did_search = False
            initial_llm_text = ""
            
            for i in range(max_iterations):
                try:
                    response = llm.invoke(messages)
                    messages.append(response)
                except Exception as e:
                    error_msg = str(e)
                    if "validation error for aimessage" in error_msg.lower() and "none is not an allowed value" in error_msg.lower():
                        print(f"⚠️ Detectado error de validación Llama-3 (args nulos). Pidiendo corrección al modelo...")
                        # Append a message to guide the LLM to fix its hallucinated tool call format
                        messages.append(HumanMessage(content="Your last action resulted in a Validation Error because you passed `null` for tool call parameters instead of an empty `{}` object. Please fix this and return a valid JSON object like {} for arguments if empty."))
                        continue
                    elif "failed_generation" in error_msg and "<function=" in error_msg:
                        import re, json, uuid
                        print(f"⚠️ Detectado erro de validación Groq (Text Chat). Autorecuperando tool call... Error: {error_msg}")
                        match = re.search(r'<function=([a-zA-Z0-9_]+)[\s>]*(\{.*?\})', error_msg, re.DOTALL)
                        if match:
                            func_name = match.group(1)
                            func_args_str = match.group(2) or "{}"
                            try:
                                # Creamos un AIMessage "fake" con el texto previo y la llamada nativa injectada
                                fake_content = "Entendido."
                                text_match = re.search(r"failed_generation':\s*'([^<]+)", error_msg)
                                if text_match and text_match.group(1).strip():
                                    fake_content = text_match.group(1).strip()
                                
                                tool_call_id = "call_" + str(uuid.uuid4())[:10]
                                response = AIMessage(
                                    content=fake_content, 
                                    tool_calls=[{"name": func_name, "args": json.loads(func_args_str), "id": tool_call_id}]
                                )
                                messages.append(response)
                            except Exception as parse_e:
                                print(f"❌ Error parseando JSON de failed_generation en Text Chat: {parse_e}")
                                raise e
                        else:
                            raise e
                    else:
                        raise e

                tool_calls = getattr(response, "tool_calls", None)
                if not tool_calls and hasattr(response, "additional_kwargs"):
                    tool_calls = response.additional_kwargs.get("tool_calls", [])
                
                # Auto-recuperación de alucinación Groq Llama 3.3 en texto (Tags XML crudos)
                if not tool_calls and isinstance(response.content, str) and "<function=" in response.content:
                    import re, json, uuid
                    match = re.search(r'<function=([a-zA-Z0-9_]+)[\s>]*(\{.*?\})', response.content, re.DOTALL)
                    if match:
                        func_name = match.group(1)
                        func_args_str = match.group(2) or "{}"
                        try:
                            # Limpiamos todo hasta la etiqueta original de function y extraemos tool_calls
                            clean_content = response.content.split("<function=")[0].strip()
                            # MUTAR response original para que el LangChain history lo guarde LIMPIO
                            response.content = clean_content
                            tool_calls = [{"name": func_name, "args": json.loads(func_args_str), "id": "call_" + str(uuid.uuid4())[:10]}]
                            print(f"⚠️ Text Chat: Autorecuperado Tool Call de Llama-3: {func_name}")
                            # Y se lo agregamos manual al objeto response
                            response.tool_calls = tool_calls
                        except Exception as e:
                            print(f"❌ Error parseando JSON de alucinación Text Chat: {e}")

                if tool_calls and isinstance(response.content, str) and response.content.strip():
                    if not initial_llm_text:
                        initial_llm_text = response.content.strip()

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
                        did_search = True
                        if not initial_llm_text:
                            if lang == "en":
                                initial_llm_text = "Let me check our options momentarily..."
                            else:
                                initial_llm_text = "Permíteme verificar en nuestro sistema unos segundos..."
                        
                        if "max_price" not in args or str(args.get("max_price")).strip() == "":
                            q_lo = query.lower()
                            if any(word in q_lo for word in ["no ", "no.", "no,", "ningun", "nada", "cero", "sin "]) or q_lo == "no" or q_lo == "any" or "any" in q_lo or "cualquier" in q_lo:
                                args["max_price"] = "100000000000"
                            else:
                                # Bloquear la ejecución
                                if lang == "en":
                                    data = "SYSTEM: You haven't asked for a budget limit. ASK the user for their budget before proceeding. NEVER invent a search. Say: 'I understand, but before we search, do you have any specific budget in mind?'"
                                else:
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
                                for prop in data["raw_properties"]:
                                    prop["currency"] = currency
                                    prop["ui_currency"] = currency
                                all_raw_properties.extend(data["raw_properties"])
                            if "appointments" in data:
                                scheduled_appointments.extend(data["appointments"])
                            if "action" in data and data["action"] == "view_details":
                                ui_action = "view_details"
                                ui_listing_id = data.get("listing_id")
                    except Exception as e:
                        print(f"❌ Tool Error in Text Chat: {e}")
                        result_text = f"Error ejecutando la herramienta: {e}"

                    import json
                    json_content = json.dumps(data, ensure_ascii=False) if isinstance(data, dict) else result_text
                    messages.append(ToolMessage(
                        content=json_content,
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
            if did_search and initial_llm_text:
                result_payload["filler_text"] = initial_llm_text
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
        
        # Encontrar el último mensaje humano e inyectarle la orden condicionante
        from langchain_core.messages import HumanMessage
        for i in range(len(messages)-1, -1, -1):
            msg = messages[i]
            is_human = False
            original_text = ""
            if isinstance(msg, HumanMessage):
                is_human = True
                original_text = msg.content
            elif isinstance(msg, dict) and msg.get("role") == "user":
                is_human = True
                original_text = msg.get("content", "")
                
            if is_human:
                stream_session_id = str(id(history)) if history else "anonymous"
                lang = _detect_language(original_text, stream_session_id, self.session_languages)
                
                if lang == "en":
                    new_content = original_text + "\n\n[SYSTEM DIRECTIVE: Respond EXCLUSIVELY in English. DO NOT translate names of Colombian cities, but formulate your ENTIRE response in English. It is FORBIDDEN to respond in Spanish even if the user says a Spanish neighborhood. Never output manual XML <function> tags.]"
                else:
                    new_content = original_text + "\n\n[DIRECTIVA DE SISTEMA: Responde EXCLUSIVAMENTE en Español, NUNCA en Inglés ni otro idioma. Prohibido usar etiquetas XML manuales.]"
                    
                if isinstance(msg, HumanMessage):
                    messages[i].content = new_content
                else:
                    messages[i]["content"] = new_content

                break

        # ── Pre-check: si el ÚLTIMO mensaje del asistente preguntó por presupuesto,
        # el mensaje actual del usuario ES su respuesta (precio, rango, o "no tengo").
        # En todos esos casos, forzar tool_choice="required" para que el LLM llame search_properties.
        _force_tool_choice = False
        if project_id == "buscofacil":
            # Recorrer mensajes en reverso para encontrar el ÚLTIMO mensaje del asistente
            for _pm in reversed(messages[:-1]):  # Excluir el mensaje actual del usuario
                _role = (getattr(_pm, "type", None) or
                         (_pm.get("role", "") if isinstance(_pm, dict) else "") or "")
                if _role not in ("ai", "assistant"):
                    continue
                # Encontramos el último mensaje del asistente
                _pmc = (getattr(_pm, "content", None) or
                        (_pm.get("content", "") if isinstance(_pm, dict) else "")) or ""
                if "presupuesto" in _pmc.lower() or "budget" in _pmc.lower():
                    _force_tool_choice = True
                    print("🎯 Pre-check: último mensaje del asistente preguntó presupuesto → tool_choice=required")
                break  # Solo nos interesa el último mensaje del asistente

        # Groq solo acepta tool_choice con 1 tool y el nombre explícito del tool.
        # "required" no es un nombre válido — debemos pasar el nombre real de la función.
        _search_tool_only = [t for t in chat_tools if t["function"]["name"] == "search_properties"]
        _llm_first = (
            llm.bind_tools(
                _search_tool_only,
                tool_choice={"type": "function", "function": {"name": "search_properties"}}
            )
            if _force_tool_choice
            else llm_with_tools
        )

        try:
            # Iteración 1: Ver si lanza texto directo o pide una tool
            is_tool_call = False
            tool_call_chunks = []

            from collections import defaultdict
            import json, re, uuid
            consolidated = defaultdict(lambda: {"name": "", "args": "", "id": ""})

            # FORCED PATH: LangChain no envía tool_choice correctamente a Groq.
            # Llamamos el cliente Groq directamente para forzar search_properties.
            if _force_tool_choice:
                try:
                    from groq import Groq as _GroqClient
                    _gc = _GroqClient(api_key=os.getenv("GROQ_API_KEY"))
                    _role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
                    _gmsgs = []
                    for _m in messages:
                        if isinstance(_m, dict):
                            _gmsgs.append({"role": _m.get("role", "user"), "content": _m.get("content", "") or ""})
                        else:
                            _role = _role_map.get(getattr(_m, "type", ""), "user")
                            _gmsgs.append({"role": _role, "content": getattr(_m, "content", "") or ""})
                    _gr = _gc.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=_gmsgs,
                        tools=_search_tool_only,
                        tool_choice={"type": "function", "function": {"name": "search_properties"}},
                        temperature=0.0
                    )
                    _gtcs = _gr.choices[0].message.tool_calls or []
                    if _gtcs:
                        is_tool_call = True
                        for _fi, _gtc in enumerate(_gtcs):
                            consolidated[_fi] = {
                                "name": _gtc.function.name,
                                "args": _gtc.function.arguments or "{}",
                                "id": _gtc.id or "call_" + str(uuid.uuid4())[:10]
                            }
                        print(f"✅ [FORCED] Groq directo → {[t.function.name for t in _gtcs]}")
                    else:
                        print(f"⚠️ [FORCED] Groq directo sin tool_calls. finish_reason={_gr.choices[0].finish_reason}")
                except Exception as _fe:
                    print(f"⚠️ [FORCED] Groq directo falló: {_fe}")

            try:
                if not is_tool_call:
                    inside_function_tag = False
                    hallucinated_xml = ""
                    async for chunk in _llm_first.astream(messages):
                        tcc = getattr(chunk, 'tool_call_chunks', None) or []
                        if tcc:
                            is_tool_call = True
                            tool_call_chunks.extend(tcc)
                        elif chunk.content and not is_tool_call:
                            chunk_text = str(chunk.content)

                            # Si encontramos el inicio de un tag, separamos la parte útil antes de iniciar modo captura
                            if "<function" in chunk_text:
                                part_before = chunk_text.split("<function")[0]
                                inside_function_tag = True
                                hallucinated_xml += chunk_text[len(part_before):] # Acumulamos desde <function
                                chunk_text = part_before
                            elif inside_function_tag:
                                hallucinated_xml += chunk_text

                            if inside_function_tag:
                                if "</function>" in str(chunk.content):
                                    inside_function_tag = False
                                if not chunk_text.strip():
                                    continue

                            if chunk_text:
                                yield chunk_text

                    # Al terminar el stream, revisar si extrajimos un tool manual
                    if not is_tool_call and hallucinated_xml:
                        import re
                        # Limpiamos el texto capturado para mayor seguridad
                        match = re.search(r"<function=([a-zA-Z0-9_]+)[\s=]*(\{.*?\})>?</function>", hallucinated_xml, re.DOTALL)
                        if match:
                            func_name = match.group(1)
                            func_args_str = match.group(2)
                            is_tool_call = True
                            import uuid
                            consolidated[0] = {"name": func_name, "args": func_args_str, "id": "call_" + str(uuid.uuid4())[:10]}

            except Exception as inner_e:
                error_msg = str(inner_e)
                # Recuperación anti-alucinaciones Llama 3.3 de Groq (400 Bad Request / failed_generation)
                if "failed_generation" in error_msg and "<function=" in error_msg:
                    print(f"⚠️ Detectado erro de validación Groq. Autorecuperando tool call... Error: {error_msg}")
                    # regex tolerante a la ausencia o presencia del > de cierre o la inclusión de signos igual = extra
                    match = re.search(r"<function=([a-zA-Z0-9_]+)[\s>]*(\{.*?\})", error_msg, re.DOTALL)
                    if match:
                        func_name = match.group(1)
                        func_args_str = match.group(2)
                        
                        is_tool_call = True
                        consolidated[0] = {"name": func_name, "args": func_args_str, "id": "call_" + str(uuid.uuid4())[:10]}
                    else:
                        print("Regex falló. Propagando excepción...")
                        raise inner_e
                elif "validation error for aimessage" in error_msg.lower() and "none is not an allowed value" in error_msg.lower():
                    print("⚠️ Detectado 'args': null en tool_call por Pydantic. Reintentando/ignorando tool call malformado.")
                    yield "Un momento, estoy organizando mi respuesta..."
                    return
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

                print(f"🔧 TOOL CALL detectado. consolidated keys: {list(consolidated.keys())}")
                for _k, _v in consolidated.items():
                    print(f"   [{_k}] name={_v.get('name')} | args_len={len(_v.get('args',''))} | id={_v.get('id','')[:20]}")

                if not consolidated:
                    print("⚠️ consolidated está vacío — no hay tools que ejecutar. Respondiendo sin tool context.")
                    async for chunk in llm_with_tools.astream(messages):
                        if chunk.content:
                            yield chunk.content
                    return

                # Parsear args de forma segura antes de construir el AIMessage
                parsed_tool_calls = []
                for c in consolidated.values():
                    try:
                        parsed_args = json.loads(c["args"]) if c["args"].strip() else {}
                    except json.JSONDecodeError as e:
                        print(f"⚠️ JSON inválido en args de tool '{c['name']}': {e} | raw: {c['args'][:200]}")
                        parsed_args = {}
                    parsed_tool_calls.append({"name": c["name"], "args": parsed_args, "id": c["id"]})

                messages.append(AIMessage(content="", tool_calls=parsed_tool_calls))

                # Ejecutar
                for c, parsed in zip(consolidated.values(), parsed_tool_calls):
                    func_name = c["name"]
                    args = parsed["args"]
                    print(f"▶️  Ejecutando tool: {func_name} | args: {str(args)[:300]}")
                    
                    if func_name == "search_properties":
                        if "max_price" not in args or str(args.get("max_price")).strip() == "":
                            # Auto-override para evitar loops si el usuario ya dijo que no tiene
                            q_lo = query.lower().strip().rstrip(".,!?¡¿").strip()
                            if any(word in q_lo for word in ["no ", "no.", "no,", "ningun", "nada", "cero", "sin "]) or q_lo == "no" or q_lo == "any" or "any" in q_lo or "cualquier" in q_lo:
                                args["max_price"] = "100000000000"
                            else:
                                # Force the LLM to output speech asking for budget
                                session_lang = self.session_languages.get(stream_session_id, "es")
                                if session_lang == "en":
                                    data = "SYSTEM: CRITICAL: You did not attach max_price. You are prohibited from searching without a budget. IGNORE tool instructions. VERBALLY ask the user for their budget directly in English."
                                else:
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
                            session_lang = self.session_languages.get(stream_session_id, "es")
                            if session_lang == "en":
                                muletillas = [
                                    "Searching our listings database for you...",
                                    "Applying your filters to the available inventory...",
                                    "Scanning current listings that match your criteria...",
                                    "Checking availability across the portfolio...",
                                    "Reviewing options that fit your requirements...",
                                    "Cross-referencing your request with our database..."
                                ]
                            else:
                                muletillas = [
                                    "Consultando la base de datos de propiedades...",
                                    "Aplicando sus filtros al inventario disponible...",
                                    "Revisando las opciones que se ajustan a sus criterios...",
                                    "Verificando disponibilidad en el portafolio actual...",
                                    "Cruzando su solicitud con nuestra base de datos...",
                                    "Analizando las propiedades que coinciden con su búsqueda..."
                                ]
                            import random
                            random.shuffle(muletillas)
                            yield muletillas.pop() + " "

                            muletillas_count = 0
                            while not tool_task.done() and muletillas_count < 2:
                                done, pending = await asyncio.wait([tool_task], timeout=4.5)
                                if not done:
                                    muletillas_count += 1
                                    yield muletillas.pop() + " "

                        # Timeout de seguridad: si la tool no responde en 20s, abortar
                        try:
                            await asyncio.wait_for(asyncio.shield(tool_task), timeout=20.0)
                        except asyncio.TimeoutError:
                            tool_task.cancel()
                            print(f"⏰ Tool '{func_name}' tardó más de 20s. Abortando.")
                            yield "[CLEAR_MULETILLAS] "
                            raise TimeoutError(f"Tool {func_name} timeout")

                        yield "[CLEAR_MULETILLAS] "
                        data = tool_task.result()
                        print(f"✅ Tool '{func_name}' completada. result keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
                            
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
                        print(f"❌ Error ejecutando tool '{func_name}': {e}")
                        yield "[CLEAR_MULETILLAS] "
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

            # ── ANTI-LOOP FALLBACK ───────────────────────────────────────────────
            # Groq Llama a veces genera texto de confirmación ("Entendido, buscaremos...")
            # sin llamar la herramienta. Detectamos ese patrón y forzamos una segunda
            # llamada al LLM con un mensaje imperativo para que ejecute search_properties.
            if not is_tool_call and project_id == "buscofacil":
                q_lo = query.lower().strip().rstrip(".,!?¡¿").strip()
                _NO_BUDGET_EXACT = {"no", "sí", "si", "yes", "ok", "okay", "dale", "busca", "buscar"}
                _NO_BUDGET_PHRASES = [
                    "no tengo", "no importa", "sin límite", "sin limite",
                    "sin presupuesto", "cualquier", "sin restriccion", "da igual",
                    "sin filtro", "no hay", "busca ya", "busca ahora",
                ]
                is_no_budget = q_lo in _NO_BUDGET_EXACT or any(p in q_lo for p in _NO_BUDGET_PHRASES)

                budget_was_asked = False
                if is_no_budget:
                    for _m in messages[-8:]:
                        _mc = (getattr(_m, "content", None) or
                               (_m.get("content", "") if isinstance(_m, dict) else "")) or ""
                        if "presupuesto" in _mc.lower() or "budget" in _mc.lower():
                            budget_was_asked = True
                            break

                if is_no_budget and budget_was_asked:
                    print("🔄 ANTI-LOOP: LLM generó texto sin tool call. Forzando segunda llamada para search_properties...")
                    messages.append(SystemMessage(content=(
                        "ORDEN CRÍTICA FINAL: El usuario ya dijo que no tiene presupuesto. "
                        "Debes llamar search_properties AHORA MISMO con la ubicación ya discutida. "
                        "NO generes texto adicional. Solo ejecuta la herramienta."
                    )))
                    try:
                        import uuid as _uuid
                        from app.routers.tools import execute_tool, ToolRequest
                        import asyncio as _asyncio
                        from groq import Groq as _GroqClient

                        # Llamar Groq directamente para garantizar que tool_choice se envía
                        _gc2 = _GroqClient(api_key=os.getenv("GROQ_API_KEY"))
                        _search_only = [t for t in chat_tools if t["function"]["name"] == "search_properties"]
                        _role_map2 = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
                        _gmsgs2 = []
                        for _m in messages:
                            if isinstance(_m, dict):
                                _gmsgs2.append({"role": _m.get("role", "user"), "content": _m.get("content", "") or ""})
                            else:
                                _role2 = _role_map2.get(getattr(_m, "type", ""), "user")
                                _gmsgs2.append({"role": _role2, "content": getattr(_m, "content", "") or ""})
                        _gr2 = _gc2.chat.completions.create(
                            model="llama-3.3-70b-versatile",
                            messages=_gmsgs2,
                            tools=_search_only,
                            tool_choice={"type": "function", "function": {"name": "search_properties"}},
                            temperature=0.0
                        )
                        _raw_tcs = _gr2.choices[0].message.tool_calls or []
                        _tc_list = [
                            {"name": _t.function.name, "args": json.loads(_t.function.arguments or "{}"), "id": _t.id}
                            for _t in _raw_tcs
                        ]

                        if _tc_list:
                            _tc = _tc_list[0]
                            _args = (_tc["args"] if isinstance(_tc["args"], dict)
                                     else json.loads(_tc["args"]))
                            _func = _tc["name"]
                            # Solo forzar max_price cuando el usuario dijo explícitamente que no tiene presupuesto.
                            # Si dio un precio real ("400 millones", "entre 200 y 300"), el LLM ya lo parseó.
                            if _func == "search_properties" and is_no_budget and not _args.get("max_price"):
                                _no_budget_exact = {"no", "sí", "si", "yes", "ok", "okay", "dale"}
                                _no_budget_phrases = ["no tengo", "sin presupuesto", "sin límite",
                                                      "sin limite", "cualquier", "sin restriccion",
                                                      "da igual", "no importa"]
                                _qlo = query.lower().strip().rstrip(".,!?¡¿").strip()
                                if (_qlo in _no_budget_exact or
                                        any(p in _qlo for p in _no_budget_phrases)):
                                    _args["max_price"] = "100000000000"
                            _tid = _tc.get("id", "call_" + str(_uuid.uuid4())[:10])

                            class _MockReq:
                                class _App:
                                    class _State:
                                        agent_manager = self
                                    state = _State()
                                app = _App()

                            _tool_req = ToolRequest(project_id=project_id, args=_args, currency=currency)
                            _sl = self.session_languages.get(stream_session_id, "es")
                            yield ("Searching now... " if _sl == "en" else "Consultando ahora... ")

                            _tt = _asyncio.create_task(
                                _asyncio.to_thread(execute_tool, _func, _tool_req, _MockReq())
                            )
                            await _asyncio.wait_for(_asyncio.shield(_tt), timeout=20.0)
                            yield "[CLEAR_MULETILLAS] "

                            _data = _tt.result()
                            _rtxt = (_data if isinstance(_data, str)
                                     else _data.get("result_text", "Done."))

                            if websocket and isinstance(_data, dict) and "raw_properties" in _data:
                                for _prop in _data["raw_properties"]:
                                    _prop["ui_currency"] = currency
                                    _prop["currency"] = currency
                                await websocket.send_json({
                                    "status": "search_results",
                                    "listings": _data["raw_properties"]
                                })
                                print(f"📡 [ANTI-LOOP] {len(_data['raw_properties'])} propiedades enviadas al frontend")

                            messages.append(AIMessage(
                                content="",
                                tool_calls=[{"name": _func, "args": _args, "id": _tid}]
                            ))
                            messages.append(ToolMessage(content=_rtxt, tool_call_id=_tid, name=_func))
                            if session_context:
                                session_context.tool_results["last_search"] = _rtxt

                            async for _c in llm_with_tools.astream(messages):
                                if _c.content:
                                    yield _c.content
                        else:
                            print("⚠️ [ANTI-LOOP] Segundo llamado LLM tampoco generó tool call — dejando respuesta de texto.")
                    except Exception as _fe:
                        print(f"❌ [ANTI-LOOP] Error en forced search: {_fe}")
            # ── FIN ANTI-LOOP ────────────────────────────────────────────────────

        except Exception as e:
            print(f"❌ Error en process_query_stream: {e}")
            yield "Hubo un error de conexión."
