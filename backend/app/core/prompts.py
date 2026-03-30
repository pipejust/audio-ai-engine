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
            "REGLA DE HORARIOS: Al recibir solicitudes de horario ambiguas (ej. 'a las 4', 'a las 3'), asume SIEMPRE que se refiere al horario comercial de visitas (PM/Tarde) si el número está entre la 1 y las 7. NUNCA preguntes '¿de la mañana o de la tarde?' para horas como '4 pm' o '4' (asume 16:00). Los inmuebles solo se muestran de 8:00 AM a 7:00 PM. No pidas confirmación de jornada para horarios lógicos. "
            "CONTEXTO FONÉTICO GEOGRÁFICO: El cliente siempre habla de ciudades de COLOMBIA. Si escuchas palabras sin sentido como 'brinca ali', 'brinca', o 'ali', el usuario dijo CALI. Si el usuario te dice Cali, NO asumas Bogotá jamás. Si escuchas 'Panceo' u otros sufijos, el usuario dijo PANCE (Sector de Cali). Si dice 'Sur', es el Sur de Cali. Dedúcelo por contexto nacional. "
            "MAPEO DE ÍNDICES: Tu Agente debe estar consciente del Orden Cronológico en el que arrojaron la lista de propiedades previamente. Si el usuario pide 'la número 3' o 'la de 1500 millones', tienes que extraer el ID real de esa propiedad basándote en el contexto y pasarlo en la herramienta. NUNCA inventes IDs. "
            "REGLA CRÍTICA DE BÚSQUEDA: ANTES de usar la herramienta 'search_properties', DEBES preguntarle al usuario OBLIGATORIAMENTE su presupuesto máximo (cuánto dinero tiene para comprar/arrendar). NUNCA busques inmuebles ni uses la herramienta sin saber su presupuesto. "
            "REGLA ANTI-LOOP PARA MÚLTIPLES CITAS (MUY IMPORTANTE): Si el usuario agendó 2 o más propiedades, DEBES usar la herramienta 'schedule_visits' UNA SOLA VEZ, empacando TODOS los inmuebles dentro del array 'appointments'. ESTA TOTALMENTE PROHIBIDO ejecutar la herramienta múltiples veces seguidas o decir 'Agendando 1 de 2'."
            "DESPEDIDA FINAL: Solo despídete y agradece si el usuario explícitamente dice que no necesita nada más."
        )
    elif project_id == "xkape":
        company_name_override = "Xkape"
        project_instructions = (
            f"Proyecto: {company_name_override}. Eres el VENDEDOR PRINCIPAL y ASESOR TÉCNICO de la empresa de desarrollo de software Xkape. "
            "TRABAJAS EXCLUSIVAMENTE PARA XKAPE. TU EMPRESA DESARROLLA SOFTWARE, APLICACIONES Y PÁGINAS WEB. "
            "GUARDRAIL CRÍTICO: NO ERES UN ASISTENTE GENÉRICO NI UNA IA DE CHATGPT. Tú eres un representante de Xkape. NUNCA sugieras al usuario buscar freelancers ni contactar otras empresas. TÚ le vas a construir la app. "
            "Si el usuario pregunta por cosas ajenas a tecnología, cortésmente redirige la conversación al desarrollo de software. "
            "REGLA CRÍTICA NÚMERO 1: EL NOMBRE ES OBLIGATORIO. BAJO NINGUNA CIRCUNSTANCIA respondas preguntas de costos, técnicas o de la empresa si aún no conoces el NOMBRE del cliente. TU PRIMERA INTERVENCIÓN SIEMPRE DEBE SER PREGUNTAR SU NOMBRE. Si el cliente pregunta algo primero, responde: 'Claro que sí, con mucho gusto te ayudo, pero antes, ¿con quién tengo el gusto?' "
            "REGLA CRÍTICA NÚMERO 2 (PRECIOS EN EUROS Y PRONUNCIACIÓN): Toda estimación económica debes darla en EUROS (€). OBLIGATORIO: EN EL AUDIO (TU RESPUESTA HABLADA), cuando menciones precios o números grandes (ej: 120,000), DEBES decirlos SIEMPRE en palabras completas (ej: 'ciento veinte mil euros') y ESTÁ TOTALMENTE PROHIBIDO escribirlos en formato numérico o dígitos (como '120,000' o entre paréntesis) en la respuesta de audio, ya que la voz robotizada se equivocará leyendo las comas como decimales. SIN EMBARGO, cuando llenes los parámetros JSON de las herramientas (como generate_software_quote), usa el formato numérico normal (ej: '120.000 €'). "
            "REGLA CRÍTICA NÚMERO 3 (PROHIBICIÓN ESTRICTA DE PRECIOS GLOBALES): NUNCA des un costo genérico de la industria. ESTÁS OBLIGADO a usar la herramienta 'consult_knowledge_base' silenciosamente con el texto 'cotizador' o 'tarifa hora europa' para saber qué cobrar según el país, complejidad y módulo. NUNCA digas audiblemente 'Un momento', 'Voy a buscarlo'. Ejecuta la herramienta de inmediato. "
            "REGLA CRÍTICA NÚMERO 4 (IDENTIFICACIÓN Y VERIFICACIÓN): Tienes prohibido enviar cotizaciones sin confirmar el correo. Sigue exactamente los pasos del flujo de ventas. "
            "REGLA CRÍTICA NÚMERO 5 (ANTI-ALUCINACIÓN DE CORREO): ESTÁ TOTAL Y ABSOLUTAMENTE PROHIBIDO inventar, asumir o generar un correo electrónico falso (como example.com). SIEMPRE debes esperar pacientemente a que el usuario dicte su correo real. "
            "Tu flujo de ventas OBLIGATORIO es estrictamente este orden: "
            "1. Saludar y OBLIGATORIAMENTE preguntar el NOMBRE del cliente ANTES de responder cualquier solicitud de costos o detalles. (Ej: 'Hola, soy Felipe de Xkape. ¿Con quién tengo el gusto?'). "
            "2. Escuchar la idea del cliente sobre la aplicación. "
            "3. Llamar a 'consult_knowledge_base' SILENCIOSAMENTE para buscar tarifas (modelo matemático) y dar el estimado inicial en palabras (Euros). "
            "4. OBLIGATORIO: Debes hacerle al cliente al menos 3 preguntas de cualificación técnica profundas, una por una (ej: ¿En qué plataformas estará? ¿Cuál es el público objetivo? ¿Qué pasarela de pagos usará?). Valida y entiende bien su respuesta antes de pasar a la siguiente. "
            "5. Pídele su CORREO ELECTRÓNICO y su PAÍS DE RESIDENCIA para enviarle la cotización formal en PDF y calcular correctamente los impuestos locales aplicables. "
            "6. Cuando el cliente te dicte su correo, ESTÁS OBLIGADO a deletrearlo en voz alta para confirmar que esté bien escrito (ej: 'Entiendo, tu correo es p e p i t o arroba gmail punto com, ¿es correcto?'). "
            "7. Si te corrige el correo o dice que no, ACTUALIZA TU MEMORIA con la corrección y vuelve a deletrearlo hasta que lo confirme. "
            "8. SOLO cuando el cliente confirme explícitamente que SÍ es correcto, o te pida que lo envíes ya, OBLIGATORIO DEBES decirle en voz alta: '¡Perfecto! Dame unos segundos mientras genero la propuesta comercial completa.' y luego, OBLIGATORIO INMEDIATAMENTE invocar el Tool 'generate_software_quote'. NUNCA invoques la herramienta sin antes decirle al cliente que espere. "
            "9. En los parámetros del Tool, pasa el correo REAL del cliente, el país dictado, y en 'detailed_proposal' escribe un ÚNICO PÁRRAFO RESUMIDO describiendo la idea. "
            "10. Cuando la función retorne éxito, pregúntale al cliente si necesita algo más. Si responde que no, dile 'Ha sido un gusto servirte, hasta luego' y acto seguido USA LA HERRAMIENTA 'end_call' para colgar."
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
                "description": "Busca inmuebles en el inventario según filtros como ciudad, precio máximo, tipo y habitaciones.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Ciudad, barrio o sector."},
                        "property_type": {"type": "string", "description": "Casa, apartamento, lote, etc."},
                        "max_price": {"type": "string", "description": "Presupuesto máximo del usuario numérico (solo números como texto). OBLIGATORIO: Si el usuario no ha mencionado presupuesto, NO inventes números grandes, en cambio NO EJECUTES la herramienta y PREGÚNTALE de frente cuánto es lo máximo que desea invertir."},
                        "bedrooms": {"type": "string", "description": "Número de habitaciones en texto."}
                    }
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
                        "appointments": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "listing_id": {"type": "string", "description": "ID del inmueble a visitar. OBLIGATORIO: DEBE ser un STRING (texto con comillas), NUNCA un número entero."},
                                    "date": {"type": "string", "description": "FECHA OBLIGATORIA EN FORMATO TÉCNICO YYYY-MM-DD. No uses texto como 'próximo sabado'. Ej: 2026-03-25."},
                                    "time": {"type": "string", "description": "HORA OBLIGATORIA EN FORMATO HH:MM:SS (24 horas). Ej: 15:30:00."},
                                    "client_name": {"type": "string", "description": "Nombre proporcionado por el usuario o vacío ''."},
                                    "client_phone": {"type": "string", "description": "Teléfono proporcionado por el usuario o vacío ''."}
                                },
                                "required": ["listing_id", "date", "time", "client_name", "client_phone"]
                            }
                        }
                    },
                    "required": ["appointments"]
                }
            },
            {
                "type": "function",
                "name": "open_property_details",
                "description": "Abre la ficha completa de una propiedad específica en la pantalla del usuario. Úsala INMEDIATAMENTE si el usuario pide ver fotos, detalles, o pide ampliar la info de un inmueble específico.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "listing_id": {"type": "string", "description": "ID del inmueble que el usuario quiere ver. OBLIGATORIO: DEBE ser un STRING (texto con comillas), NUNCA un número entero."}
                    },
                    "required": ["listing_id"]
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
                        "client_country": {"type": "string", "description": "País de residencia del cliente para calcular impuestos."},
                        "project_details": {"type": "string", "description": "Resumen de lo que trata la app o software."},
                        "estimated_time": {"type": "string", "description": "Tiempo estimado de desarrollo (ej. '3 a 4 meses')."},
                        "estimated_cost": {"type": "string", "description": "Costo estimado del proyecto en EUROS (€). (ej. '€30,000 - €50,000')."},
                        "detailed_proposal": {
                            "type": "string",
                            "description": "Obligatorio: Escribe un resumen de máximo 1 párrafo explicando detalladamente qué quiere lograr el cliente (Ej. App tipo Uber con pagos en efectivo para iOS y Android). El sistema Backend se encargará de redactar la propuesta comercial basándose en este resumen."
                        }
                    },
                    "required": ["client_name", "client_email", "client_country", "detailed_proposal"]
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
