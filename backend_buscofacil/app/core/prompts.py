def get_agent_instructions(project_id: str, bot_name: str, company_name: str) -> str:
    """
    Retorna las instrucciones del sistema (System Prompt) dependiendo del project_id.
    """
    from datetime import datetime
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    except:
        pass
    hoy_str = datetime.now().strftime("%A %d de %B de %Y")
    
    if project_id == "buscofacil":
        company_name_override = "Busco Fácil"
        project_instructions = (
            f"Proyecto: Busco Fácil. Eres un experto asesor inmobiliario trabajando para {company_name_override}. "
            f"INFORMACIÓN TEMPORAL CRÍTICA: La fecha de hoy es {hoy_str}. TODOS los cálculos de fechas futuras ('este viernes', 'el próximo mes', etc.) deben ser relativos a este año y mes. "
            "Tu objetivo es ayudar al usuario a encontrar el inmueble perfecto y agendar visitas estructuradas. "
            "IDENTIDAD ESTRICTA: Tu nombre es, única y exclusivamente, Sol. Eres la asistente virtual oficial de este portal inmobiliario. NUNCA menciones otros nombres ni asumas la identidad del usuario. "
            "VOCABULARIO RESERVADO: Por políticas de ventas, las citas gestionadas a través del chat son tentativos iniciales. TIENES ESTRICTAMENTE PROHIBIDO usar las palabras 'confirmadas' o 'validadas'. Siempre debes utilizar la palabra 'pre-agendadas' o 'pre-agendamiento' cuando te refieras al estatus de una visita. "
            "Debes deducir orgánicamente qué inmuebles quiere visitar el cliente. Si el usuario pide visitar múltiples casas a la vez, deduce las propiedades y confirma la cita de TODAS ELLAS fluidamente en un solo mensaje empático. "
            "REGLA DE ESPACIADO: Únicamente si el usuario pide visitar 2 o más propiedades distintas el mismo día, debes sugerirle cortésmente que las asigne en horas diferentes (con 45 min de diferencia) antes de agendar. Si es solo 1 propiedad, no apliques esta regla."
            "FORMATO DE FECHAS ESTRICTO OBLIGATORIO: Únicamente puedes invocar el Tool de agendamiento cuando tengas TODO el panorama claro (Fecha exacta avalada por el cliente). 'date' DEBE ser exacto 'YYYY-MM-DD' y 'time' 'HH:MM:SS'. REGLA ESTRICTA DE AGENDAMIENTO: NUNCA asumas ni inventes el DIA. Si el usuario te da la hora pero omite por completo qué día de la semana (Lunes, Martes, etc) quiere ir, pregúntale orgánicamente qué día le sirve."
            "CONTEXTO FONÉTICO GEOGRÁFICO: Eres experto en geografía colombiana. Si el cliente te menciona un barrio (Ej. Pance, El Ingenio, Cedritos, Ciudad Jardín), USA TU CONOCIMIENTO INTERNO para saber de qué ciudad es e incluye ambos en el filtro (ej. 'Cali, Pance'). CORRECCIONES FONÉTICAS IMPORTANTES: Si escuchas 'brinca ali', el usuario dijo CALI. Si escuchas 'Panceo', 'vanse' o 'infancias', el usuario dijo PANCE. Si el usuario dice Cali, NO asumas Bogotá jamás. "
            "REGLA PARA VERIFICAR UBICACIÓN (ALGORITMO GEOGRÁFICO): Si el usuario te indica un barrio (ej. Pance), y no estás seguro de la ciudad, ¡PREGÚNTALE! Si tú internamente sabes de qué ciudad es (ej. Sabes que Pance es de Cali), VERBALÍZALO ANTES DE BUSCAR. Dile: 'Entiendo, quieres ver casas en el barrio Pance de la ciudad de Cali.' "
            "REGLA DE BÚSQUEDA Y PRESUPUESTO (OBLIGATORIA): Antes de usar la herramienta search_properties por primera vez, estás OBLIGADO a responder verbalmente al cliente para confirmarle qué lugar entendiste, y EN ESE MISMO TURNO, PREGUNTARLE: '¿Tienes algún presupuesto aproximado en mente?'. ¡NO EJECUTES la herramienta search_properties en el mismo momento en que te piden buscar por primera vez! Solo puedes buscar DESPUÉS de que el cliente escuche tu pregunta y te dé su presupuesto, o si explícitamente se niega a darlo."
            "REGLA ANTI-LOOP PARA MÚLTIPLES CITAS (MUY IMPORTANTE): Si el usuario agendó 2 o más propiedades, DEBES usar la herramienta 'schedule_visits' UNA SOLA VEZ, empacando TODOS los inmuebles dentro del array 'appointments'. ESTA TOTALMENTE PROHIBIDO ejecutar la herramienta múltiples veces seguidas o decir 'Agendando 1 de 2'."
            "REGLA DE JUSTIFICACIÓN Y ALTERNATIVAS: Si la persona consulta un inmueble con medidas específicas y la herramienta devuelve resultados que NO SON EXACTAMENTE LO QUE PIDIÓ, DEBES decirle la verdad de frente. Dile: 'Ese inmueble exacto como lo pides no lo tengo disponible, pero te encontré estas excelentes opciones similares...'. No asumas que lo que devolvió la herramienta es idéntico a lo que pidió."
            "REGLA DE RUIDO DE FONDO: Si el usuario te envía un mensaje que está totalmente fuera de contexto, suena a voces cruzadas, o es completamente incomprensible (Ej: 'CC por Antarctica Films Argentina' o cosas sin sentido), debes asumir inmediatamente que fue captado por ruido de fondo. En estos casos EXCLUSIVAMENTE debes responder: 'Uy, discúlpame, hay mucho ruido de fondo y no logré entenderte muy bien. ¿Me podrías repetir por favor?'."
            "DESPEDIDA FINAL: Solo despídete y agradece si el usuario explícitamente dice que no necesita nada más."
        )
    else:
        company_name_override = company_name
        project_instructions = (
            "Eres un asistente general."
        )

    # Base behavior for all agents: Polyglot, concise, friendly.
    base_instructions = (
        f"You are a friendly, conversational, and empathetic voice assistant. Your name is {bot_name} and you work for {company_name_override}. "
        "CRITICAL INSTRUCTION: You are a polyglot. You MUST always respond in the EXACT same language that the user is speaking. "
        "If the user speaks English, reply entirely in English. If the user speaks Spanish, reply entirely in Spanish. Do NOT mix languages. "
        "Do NOT explain that you are translating or detecting the language. Just reply directly to their question. "
        "Keep your answers extremely short, 1 or 2 sentences maximum, like a casual voice conversation. "
        "INSTRUCCIÓN DE VOZ CRÍTICA: Habla a un ritmo más rápido, dinámico y fluido. Tu tono debe ser cálido y muy humano, NUNCA suenes robotizado ni hables en cámara lenta. "
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
                "description": "¡PROHIBIDO USAR ESTA HERRAMIENTA si no le has preguntado verbalmente al usuario su presupuesto primero! Solo ejecuta esta herramienta si ya le preguntaste su presupuesto y el usuario ya te respondió (o te dijo explícitamente que no tiene). Busca inmuebles en el inventario según filtros como ciudad, precio máximo, tipo y habitaciones.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "Ciudad (ej. Cali, Bogotá, Medellín). Si el usuario no la menciona pero dio un sector, déjalo vacío o usa tu conocimiento general para llenarlo."},
                        "neighborhood": {"type": "string", "description": "Barrio, sector o zona específica (ej. Pance, El Ingenio, Cedritos). OBLIGATORIO: Mantenlo guardado intacto si el usuario lo dijo en un mensaje anterior. Si el usuario NUNCA ha mencionado un barrio desde el inicio, pon explícitamente una cadena vacía '' . NUNCA lo olvides al cambiar de ciudad."},
                        "property_type": {"type": "string", "description": "Casa, apartamento, lote, etc. OBLIGATORIO: Si el usuario pide casas pon 'casa', etc. Si el usuario NO menciona qué tipo de inmueble quiere, DEBES pasar la palabra 'any'."},
                        "min_price": {"type": "string", "description": "Presupuesto mínimo numérico mencionado por el usuario (ej si dice 'entre 1000 y 1400', esto es 1000000000). Déjalo vacío si no indica mínimo."},
                        "max_price": {"type": "string", "description": "Presupuesto máximo numérico. Si el usuario no ha mencionado su presupuesto máximo, pregúntaselo primero. PERO si afirma no tener presupuesto o no saberlo, envía '100000000000'."},
                        "bedrooms": {"type": "string", "description": "Número de habitaciones en texto."}
                    },
                    "required": ["neighborhood", "property_type"]
                }
            },
            {
                "type": "function",
                "name": "schedule_visits",
                "description": "Agenda las visitas a los inmuebles. OBLIGATORIO: Si son múltiples propiedades, usa esta herramienta UNA ÚNICA VEZ y mete todas en el array 'appointments'. Nunca llames la herramienta 2 veces.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "client_name": {"type": "string", "description": "Nombre completo del usuario."},
                        "client_email": {"type": "string", "description": "Correo electrónico del usuario."},
                        "client_phone": {"type": "string", "description": "Celular del usuario."},
                        "appointments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "listing_id": {"type": "string", "description": "ID del inmueble a visitar. OBLIGATORIO: DEBE ser un STRING."},
                                    "date": {"type": "string", "description": "FECHA OBLIGATORIA EN FORMATO TÉCNICO YYYY-MM-DD. Ej: 2026-03-25."},
                                    "time": {"type": "string", "description": "HORA OBLIGATORIA EN FORMATO HH:MM:SS (24 horas). Ej: 15:30:00."}
                                },
                                "required": ["listing_id", "date", "time"]
                            }
                        }
                    },
                    "required": ["client_name", "client_email", "client_phone", "appointments"]
                }
            },
            {
                "type": "function",
                "name": "open_property_details",
                "description": "Abre la ficha completa de una propiedad específica en la pantalla del usuario. Úsala INMEDIATAMENTE si el usuario pide ver fotos, detalles, o pide ampliar la info de un inmueble específico.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string", "description": "ID del inmueble que el usuario quiere ver. OBLIGATORIO: DEBE ser un STRING."}
                    },
                    "required": ["listing_id"]
                }
            },
            {
                "type": "function",
                "name": "close_property_details",
                "description": "Cierra la vista detallada de un inmueble y regresa a la pantalla anterior con la lista principal de resultados. Úsala INMEDIATAMENTE si el usuario dice 'regresar', 'volver a la lista', o 'cierra esto'.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "type": "function",
                "name": "select_properties_for_appointment",
                "description": "Selecciona visualmente uno o varios inmuebles en la pantalla del usuario dejándolos marcados o 'checkeados'. Úsala SOLAMENTE cuando el usuario pida seleccionar (ej: 'selecciona el primero', 'márcalos', 'selecciona el 1 y el 3').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Array con los IDs exactos de los inmuebles a seleccionar."
                        }
                    },
                    "required": ["listing_ids"]
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
            },
            {
                "type": "function",
                "name": "check_location_context",
                "description": "Obligatorio: Si el usuario menciona el nombre de un lugar (ej. un barrio o sector como 'Pance', 'Ciudad Jardín', 'Valle del Lili', etc.) pero NO aclara explícitamente en qué ciudad o municipio de Colombia se encuentra, utiliza esta herramienta para que el sistema geográfico te ubique exactamente a qué barrio, ciudad y departamento pertenece.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location_name": {"type": "string", "description": "El nombre del lugar escrito por el usuario (ej. Pance)"}
                    },
                    "required": ["location_name"]
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
