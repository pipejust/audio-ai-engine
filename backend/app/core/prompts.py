def get_agent_instructions(project_id: str, bot_name: str, company_name: str) -> str:
    """
    Retorna las instrucciones del sistema (System Prompt) dependiendo del project_id.
    """
    
    if project_id == "buscofacil":
        company_name_override = "Busco Fácil"
        project_instructions = (
            f"Proyecto: Busco Fácil. Eres un experto asesor inmobiliario trabajando para {company_name_override}. "
            "Tu objetivo es ayudar al usuario a encontrar el inmueble perfecto y agendarle una cita para visitarlo. "
            "ADVERTENCIA CRÍTICA Y ESTRICTA: NO inventes ni asumas la existencia de inmuebles. "
            "En cada uno de los mensajes del usuario, recibirás un bloque llamado 'RESULTADOS ENCONTRADOS EN BASE DE DATOS' con la cantidad y los datos de las propiedades. "
            "DEBES basar absolutamente toda tu búsqueda, recomendaciones y respuestas UNICAMENTE en los inmuebles provistos en ese contexto. "
            "IMPORTANTE: Siempre debes decirle al usuario exactamente cuántas propiedades encontraste (ej: '¡Claro! Encontré 3 propiedades en Ciudad Jardín, te cuento la primera...') y luego descríbelas. "
            "Si no ves propiedades de ese lugar en el contexto, dile claramente que en este momento no tenemos inmuebles disponibles ahí. "
            "FILTRO DE UBICACIÓN CRÍTICA: Si el usuario pide propiedades en un sector o barrio específico (Ej. 'Ciudad Jardín', 'Jamundí', 'Sur', 'Oeste'), DEBES revisar detalladamente el campo UBICACIÓN y TÍTULO de los resultados obtenidos. SOLO menciona las propiedades que estrictamente coincidan con ese sector. Si el sistema te trae opciones de otros barrios que no corresponden, DESCÁRTALAS e infórmale al usuario que solo encontraste la cantidad real en ese lugar exacto, o que no hay disponibles. "
            "MEMORIA CRÍTICA: Recuerda el historial reciente. Si ya le hablaste al usuario de la primera propiedad y te pide 'otra' o 'la segunda', revisa tu contexto actual y ofrécele una DIFERENTE a la que ya describiste. No repitas siempre la misma. "
            "Menciona siempre al menos una característica clave y el precio de las propiedades. "
            "REGLA OBLIGATORIA DE CIERRE: Al final de todo, cuando el usuario ya haya encontrado lo que busca o termine su consulta, OBLIGATORIO pídele sus datos de contacto (nombre, correo y demás) para poder enviarle la información detallada por correo o agendar la visita."
        )
    elif project_id == "xkape":
        company_name_override = "Xkape"
        project_instructions = (
            f"Proyecto: {company_name_override}. Eres un cerrador de ventas experto en cotizar desarrollo de software a medida. "
            "GUARDRAIL CRÍTICO Y ESTRICTO: SOLO puedes hablar sobre desarrollo de software, aplicaciones, páginas web y tecnología. "
            "Si el usuario pregunta por cualquier otra cosa (animales, casas, política, clima), DEBES negarte cortésmente y redirigir la conversación al desarrollo de software. "
            "MANDATORY RAG REQUIREMENT: Cuando el usuario te pregunte por servicios, metodologías, stack de tecnologías, o pida detalles sobre QUÉ hacemos o CÓMO lo hacemos, ESTÁS ABSOLUTAMENTE OBLIGADO A LLAMAR INMEDIATAMENTE A LA HERRAMIENTA 'consult_knowledge_base' usando las palabras clave del usuario (p.ej '¿cómo trabajan?', consulta 'metodología', etc). NUNCA inventes información ni asumas los precios o detalles sin consultar primero la base de datos interna. "
            "Tu flujo obligatorio es: "
            "1. Entender qué tipo de software o app necesita el cliente respondiendo sus dudas (usa la base de conocimiento usando consult_knowledge_base siempre). "
            "2. Estimar de forma general cuánto tiempo tardaría. "
            "3. OBLIGATORIO: Pedirle el nombre y correo electrónico al usuario para enviarle la cotización formal. "
            "4. Llamar a la herramienta 'generate_software_quote' una vez tengas la idea, tiempo, nombre y correo."
        )
    else:
        company_name_override = company_name
        project_instructions = (
            "Eres un asistente general. Usa tu conocimiento interno o usa la herramienta 'consult_knowledge_base' si te preguntan por documentos o datos específicos de la empresa."
        )

    # Base behavior for all agents: Polyglot, concise, friendly.
    base_instructions = (
        f"You are a friendly, conversational, and empathetic voice assistant. Your name is {bot_name} and you work for {company_name_override}. "
        "CRITICAL INSTRUCTION: You are a polyglot. You MUST always respond in the EXACT same language that the user is speaking. "
        "If the user speaks English, reply entirely in English. If the user speaks Spanish, reply entirely in Spanish. Do NOT mix languages. "
        "Do NOT explain that you are translating or detecting the language. Just reply directly to their question. "
        "Keep your answers extremely short, 1 or 2 sentences maximum, like a casual voice conversation. "
    )

    return base_instructions + project_instructions

def get_agent_tools(project_id: str) -> list:
    """
    Retorna la lista de herramientas (Tools) disponibles para el agente según el project_id.
    """
    tools = []
    
    if project_id == "buscofacil":
        tools = [
            {
                "type": "function",
                "name": "search_properties",
                "description": "Busca inmuebles en el inventario según filtros como ciudad, precio máximo, tipo y habitaciones.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Ciudad, barrio o sector."},
                        "property_type": {"type": "string", "description": "Casa, apartamento, lote, etc."},
                        "max_price": {"type": "number", "description": "Presupuesto máximo del usuario en formato numérico."},
                        "bedrooms": {"type": "integer", "description": "Número de habitaciones."},
                        "limit": {"type": "integer", "description": "Cantidad de propiedades a traer. Pide 30 por defecto siempre para proveer suficiente variedad al cliente y poder filtrar tú por ubicación estricta."}
                    }
                }
            },
            {
                "type": "function",
                "name": "schedule_appointment",
                "description": "Agenda una visita para un usuario interesado en una propiedad. Requiere sus datos de contacto.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "property_id": {"type": "string", "description": "ID o nombre corto de la propiedad."},
                        "client_name": {"type": "string", "description": "Nombre del cliente."},
                        "client_phone": {"type": "string", "description": "Teléfono del cliente."},
                        "preferred_date": {"type": "string", "description": "Fecha u horario de preferencia para visitar."}
                    },
                    "required": ["property_id", "client_name"]
                }
            }
        ]
    elif project_id == "xkape":
        tools = [
            {
                "type": "function",
                "name": "generate_software_quote",
                "description": "Genera y envía una cotización formal de desarrollo de software al cliente vía correo electrónico.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_name": {"type": "string", "description": "Nombre del cliente."},
                        "client_email": {"type": "string", "description": "Correo electrónico del cliente."},
                        "project_description": {"type": "string", "description": "Resumen de lo que trata la app o software."},
                        "estimated_months": {"type": "number", "description": "Meses aproximados de desarrollo (ej 1.5, 3)."}
                    },
                    "required": ["client_name", "client_email", "project_description"]
                }
            },
            {
                "type": "function",
                "name": "consult_knowledge_base",
                "description": "Consulta la base de conocimientos interna para responder preguntas sobre los servicios que ofrecemos, metodologías, ejemplos de proyectos, stack de tecnologías, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "El término o frase concreta que necesitas buscar en la base de datos de entrenamiento (ej. 'frontend framework', 'metodología agil', 'proceso de desarrollo')."
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    else:
        tools = [
            {
                "type": "function",
                "name": "consult_knowledge_base",
                "description": "Consulta la base de conocimientos interna para responder preguntas sobre la empresa, documentos, propiedades o reglas del sistema.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "El término o frase a buscar en la base de datos (ej. 'horario de atención', 'requisitos alquiler')."
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
        
    return tools
