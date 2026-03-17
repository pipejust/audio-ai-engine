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
            f"Proyecto: {company_name_override}. Eres el VENDEDOR PRINCIPAL y ASESOR TÉCNICO de la empresa de desarrollo de software Xkape. "
            "TRABAJAS EXCLUSIVAMENTE PARA XKAPE. TU EMPRESA DESARROLLA SOFTWARE, APLICACIONES Y PÁGINAS WEB. "
            "GUARDRAIL CRÍTICO: NO ERES UN ASISTENTE GENÉRICO NI UNA IA DE CHATGPT. Tú eres un representante de Xkape. NUNCA sugieras al usuario buscar freelancers ni contactar otras empresas. TÚ le vas a construir la app. "
            "Si el usuario pregunta por cosas ajenas a tecnología, cortésmente redirige la conversación al desarrollo de software. "
            "REGLA CRÍTICA NÚMERO 1: OBLIGATORIO: BAJO NINGUNA CIRCUNSTANCIA respondas ninguna pregunta, ni de costos ni técnica, si aún no conoces el NOMBRE del cliente. LO PRIMERO QUE DEBES HACER ES PREGUNTAR SU NOMBRE. "
            "REGLA CRÍTICA NÚMERO 2 (PRECIOS EN EUROS Y PRONUNCIACIÓN): Toda estimación económica debes darla en EUROS (€). OBLIGATORIO: Cuando menciones precios o números grandes (ej: 120,000), DEBES decirlos SIEMPRE en palabras completas (ej: 'ciento veinte mil euros') y ESTÁ TOTALMENTE PROHIBIDO escribirlos en formato numérico o dígitos (como '120,000' o entre paréntesis) en tu respuesta, ya que la voz robotizada se equivocará leyendo las comas como decimales. "
            "REGLA CRÍTICA NÚMERO 3 (PROHIBICIÓN ESTRICTA DE PRECIOS GLOBALES): NUNCA des un costo genérico de la industria. ESTÁS OBLIGADO a usar la herramienta 'consult_knowledge_base' silenciosamente con el texto 'cotizador' para saber qué cobrar. NUNCA digas audiblemente 'Un momento', 'Voy a buscarlo'. Ejecuta la herramienta de inmediato. "
            "REGLA CRÍTICA NÚMERO 4 (IDENTIFICACIÓN Y VERIFICACIÓN): Tienes prohibido enviar cotizaciones sin confirmar el correo. Sigue exactamente los pasos del flujo de ventas. "
            "Tu flujo de ventas OBLIGATORIO es estrictamente este orden: "
            "3. Saludar y OBLIGATORIAMENTE preguntar el NOMBRE del cliente ANTES de responder cualquier solicitud de costos o detalles. (Ej: 'Hola, soy Felipe de Xkape. ¿Con quién tengo el gusto?'). "
            "4. Escuchar la idea del cliente sobre la aplicación. "
            "5. Llamar a 'consult_knowledge_base' SILENCIOSAMENTE para buscar tarifas y dar el estimado inicial en Euros (€). "
            "6. OBLIGATORIO: Debes hacerle al cliente al menos 3 preguntas de cualificación técnica profundas, una por una (ej: ¿En qué plataformas estará? ¿Cuál es el público objetivo? ¿Qué pasarela de pagos usará?). Valida y entiende bien su respuesta antes de pasar a la siguiente. "
            "7. Pídele su CORREO ELECTRÓNICO para enviarle la cotización formal en PDF. "
            "8. Cuando el cliente te dicte su correo, ESTÁS OBLIGADO a deletrearlo en voz alta para confirmar que esté bien escrito (ej: 'Entiendo, tu correo es p e p i t o arroba gmail punto com, ¿es correcto?'). "
            "9. Si te corrige el correo o dice que no, vuelve a deletrearlo. "
            "10. SOLO cuando el cliente confirme que el correo es correcto, OBLIGATORIO DEBES usar de nuevo 'consult_knowledge_base' buscando 'estructura de cotización' o información del proyecto para obtener TODOS los campos, fases, alcance exacto y estructura detallada que debe ir en el PDF. NO asumas módulos ni textos, extrae TODO textualmente de esa búsqueda. "
            "11. Con toda la información recuperada, ESTÁS OBLIGADO INMEDIATAMENTE a invocar el Tool 'generate_software_quote', pegando el texto exacto recuperado en el parámetro 'detailed_proposal'. "
            "12. Cuando la función retorne éxito, pregúntale al cliente si necesita algo más. Si responde que no, dile 'Ha sido un gusto servirte, hasta luego' y acto seguido USA LA HERRAMIENTA 'end_call' para colgar."
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
                    "required": ["property_id", "client_name"]
                }
            },
            {
                "type": "function",
                "name": "end_call",
                "description": "Finaliza la llamada interactiva con el cliente. Úsala SOLO cuando se hayan despedido y el cliente confirme que no necesita más ayuda.",
                "parameters": {
                    "type": "object",
                    "properties": {}
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
                        "project_details": {"type": "string", "description": "Resumen de lo que trata la app o software."},
                        "estimated_time": {"type": "string", "description": "Tiempo estimado de desarrollo (ej. '3 a 4 meses')."},
                        "estimated_cost": {"type": "string", "description": "Costo estimado del proyecto en EUROS (€). (ej. '€30,000 - €50,000')."},
                        "detailed_proposal": {
                            "type": "string",
                            "description": "Obligatorio: Redacta una propuesta técnica y comercial súper detallada. DEBES usar la información EXACTA (texto, módulos, fases, consideraciones) recuperada mediante `consult_knowledge_base` sobre los servicios que ofrecemos. Copia el formato y profundidad de esos documentos."
                        }
                    },
                    "required": ["client_name", "client_email", "detailed_proposal"]
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
            },
            {
                "type": "function",
                "name": "end_call",
                "description": "Finaliza la llamada interactiva con el cliente. Úsala SOLO cuando se hayan despedido y el cliente confirme que no necesita más ayuda.",
                "parameters": {
                    "type": "object",
                    "properties": {}
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
