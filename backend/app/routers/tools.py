from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(tags=["Tools"])

class ToolRequest(BaseModel):
    project_id: str
    args: Dict[str, Any]

@router.post("/{function_name}")
def execute_tool(function_name: str, request_data: ToolRequest, request: Request):
    """
    Endpoint dinámico para ejecutar herramientas.
    Este endpoint simula los Web Services externos para cada tenant.
    Se ejecuta en un threadpool gracias a FastAPI para no bloquear el Event Loop (por smtp).
    """
    import smtplib
    from email.message import EmailMessage
    # Obtenemos agent_manager desde request.app.state o importándolo, pero aquí usamos
    # el global de main.py mediante un getter simple o import deferido si es necesario.
    # Dado que es mejor inyectarlo o accederlo vía app.state:
    agent_manager = request.app.state.agent_manager
    project_id = request_data.project_id
    args = request_data.args
    
    if function_name == "consult_knowledge_base":
        query = args.get("query", "")
        retriever = agent_manager.vector_store.get_retriever(k=25, project_id=project_id)
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
        
        def normalize_str(s):
            import unicodedata
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()
            
        loc_norm = normalize_str(location) if location.lower() != "any" else ""
        type_norm = normalize_str(tipo) if tipo.lower() != "any" else ""
        
        if raw_docs:
            for d in raw_docs:
                page_norm = normalize_str(d.page_content)
                meta_loc = normalize_str(d.metadata.get("location_search", ""))
                meta_type = normalize_str(d.metadata.get("property_type", ""))
                
                if loc_norm and loc_norm not in meta_loc and loc_norm not in page_norm:
                    continue
                if type_norm and type_norm not in meta_type and type_norm not in page_norm:
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
        name = args.get("client_name", "Cliente")
        email = args.get("client_email")
        project_details = args.get("project_details", "Desarrollo de Software a Medida")
        estimated_time = args.get("estimated_time", "No especificado")
        estimated_cost = args.get("estimated_cost", "No especificado")
        detailed_proposal = args.get("detailed_proposal", None)
        
        if not email:
            return {"status": "error", "result_text": "Email is required to send the quote."}
            
        try:
            from app.db.session import SessionLocal
            from app.db.models import Template, SmtpSettings
            import json
            import resend
            from fpdf import FPDF
            
            # Fetch Styles and SMTP Config
            db = SessionLocal()
            template_obj = db.query(Template).filter(Template.project_id == project_id).first()
            smtp_obj = db.query(SmtpSettings).filter(SmtpSettings.project_id == project_id).first()
            db.close()
            
            style_config = {}
            if template_obj and template_obj.style_config:
                try: style_config = json.loads(template_obj.style_config)
                except: pass
                
            def hex_to_rgb_tuple(hex_str: str) -> tuple:
                hex_str = hex_str.lstrip('#')
                if len(hex_str) != 6: return (0, 0, 0)
                return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16))
                
            color_text = hex_to_rgb_tuple(style_config.get("textColor", "#1f2937"))
            color_heading = hex_to_rgb_tuple(style_config.get("headingColor", "#4f46e5"))
            family = style_config.get("fontFamily", "helvetica").lower()
            size = int(style_config.get("fontSize", 12))
            
            # Get Company Data
            c_name = style_config.get("companyName", "").encode('latin-1', 'ignore').decode('latin-1')
            c_id = style_config.get("companyId", "").encode('latin-1', 'ignore').decode('latin-1')
            c_address = style_config.get("companyAddress", "").encode('latin-1', 'ignore').decode('latin-1')
            c_phone = style_config.get("companyPhone", "").encode('latin-1', 'ignore').decode('latin-1')
            c_web = style_config.get("companyWebsite", "").encode('latin-1', 'ignore').decode('latin-1')
            
            # 1. Generate PDF
            pdf = FPDF()
            pdf.add_page()
            
            # Global Font
            try: pdf.set_font(family, size=size)
            except: pdf.set_font("helvetica", size=size) # fallback
            
            # --- COMPANY HEADER ---
            if c_name or c_phone or c_web:
                pdf.set_text_color(*color_heading)
                pdf.set_font(family, "B", size + 6)
                pdf.cell(0, 8, c_name if c_name else "Propuesta Comercial", new_x="LMARGIN", new_y="NEXT", align="R")
                
                pdf.set_text_color(*color_text)
                pdf.set_font(family, "", size - 2)
                if c_id: pdf.cell(0, 5, f"NIT/ID: {c_id}", new_x="LMARGIN", new_y="NEXT", align="R")
                if c_address: pdf.cell(0, 5, c_address, new_x="LMARGIN", new_y="NEXT", align="R")
                if c_phone: pdf.cell(0, 5, f"Tel: {c_phone}", new_x="LMARGIN", new_y="NEXT", align="R")
                if c_web: pdf.cell(0, 5, c_web, new_x="LMARGIN", new_y="NEXT", align="R")
                
                pdf.ln(5)
                pdf.set_draw_color(*color_heading)
                pdf.set_line_width(0.5)
                pdf.line(10, pdf.get_y(), 200, pdf.get_y())
                pdf.ln(10)
            
            # Title
            pdf.set_text_color(*color_heading)
            pdf.set_font(family, "B", size + 4)
            pdf.cell(0, 10, "PROPUESTA DE DESARROLLO DE SOFTWARE", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(10)
            
            # Greet
            pdf.set_text_color(*color_text)
            pdf.set_font(family, "", size)
            pdf.multi_cell(0, 8, f"Estimado/a {name},\n\nAdjuntamos la estimación para su requerimiento de software:")
            pdf.ln(5)
            
            # FPDF's default Helvetica does not support the € symbol in latin-1. Replace it to avoid crashes.
            safe_cost = estimated_cost.replace("€", "EUR")
            
            if detailed_proposal:
                # Disparar Langchain para escalar el resumen corto a una propuesta de 16 Puntos
                from langchain_openai import ChatOpenAI
                from langchain_core.messages import SystemMessage, HumanMessage
                import os
                import time
                from datetime import datetime
                import locale
                try: locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
                except: pass
                today_str = datetime.now().strftime("%d de %B de %Y")
                quote_code = f"COT-{int(time.time())}"
                
                # Cargar el prompt gigante documentado por el usuario
                template_path = os.path.join(os.path.dirname(__file__), "../cotizacion_prompt_template.txt")
                if os.path.exists(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        system_prompt_text = f.read()
                else:
                    system_prompt_text = "Eres un redactor comercial experto."
                
                legal_text = (
                    "\n\n--- INICIO TEXTO OBLIGATORIO AL FINAL DE LA COTIZACIÓN (Sección 17) ---\n"
                    "Gobernanza: legal, seguridad, privacidad, validación y roadmap\n"
                    "Consideraciones legales, de seguridad y privacidad al usar cotizaciones reales\n"
                    "1) Datos personales y anonimización\n"
                    "La AEPD señala que los datos anonimizados no se consideran datos personales (y por tanto no se rigen por normativa de protección de datos), pero también introduce el riesgo de reidentificación como concepto relevante. El RGPD contempla salvaguardas y menciona medidas como la seudonimización en ciertos contextos de tratamiento. Implicación para dataset: separar PII (nombres, mails, teléfonos) de datos de cotización y aplicar anonimización/seudonimización, además de evaluar riesgo de reidentificación en combinaciones de campos.\n"
                    "2) Confidencialidad comercial\n"
                    "Cotizaciones reales suelen contener márgenes, descuentos, condiciones negociadas, nombres de clientes y arquitectura sensible. Aun sin PII, esto puede ser secreto comercial. Recomendación: Obtener autorización contractual o generar dataset sintético derivado de plantillas. Mantener source_type y license_notes por registro, y restringir acceso por rol.\n"
                    "3) Controles de seguridad de la plataforma de datos/modelo\n"
                    "Para controles, puede alinearse con un catálogo de controles de seguridad y privacidad como NIST SP 800-53 (catálogo amplio de controles), y aplicar endurecimiento de acceso, cifrado, logging y segregación de entornos. Para seguridad aplicada al software que se cotiza, OWASP ASVS da una base verificable para requisitos y pruebas de controles técnicos en aplicaciones.\n"
                    "4) Riesgo de IA y gobernanza\n"
                    "El NIST AI RMF está planteado como recurso voluntario para gestionar riesgos de IA y promover confiabilidad, y puede servir como marco de control del ciclo de vida (diseño, despliegue, evaluación).\n"
                    "--- FIN TEXTO OBLIGATORIO ---\n"
                )

                strict_rules = (
                    "REGLAS CRÍTICAS DE FORMATO Y CONTENIDO (OBLIGATORIAS):\n"
                    "1. NO inventes información bancaria. Como no tienes los datos del banco, elimina completamente los campos 'Banco', 'Tipo de Cuenta', 'Número de Cuenta', 'Titular' y 'Correo de Confirmación de Pago'. ¡NO los imprimas con corchetes!\n"
                    "2. En el encabezado, usa exactamente los datos provistos. NUNCA escribas corchetes como '[Ciudad]', usa los datos que te paso.\n"
                    "3. Usa el nombre provisto para el Cliente y Contacto.\n"
                    "4. En la Firma y Datos de Proveedor, usa EXCLUSIVAMENTE la Información Proveedor que te paso. Si 'Cargo' no existe, bórralo.\n"
                    "5. Genera DIRECTAMENTE y ÚNICAMENTE el contenido del documento PDF (sin metadatos ni bloque 2 o 3).\n"
                    "6. OBLIGATORIO Y CRÍTICO: Debes incluir IMPERATIVAMENTE los valores exactos que te paso de 'Tiempo Estimado de Ejecución' y 'Costo de la Inversión'. NO pongas 'No especificado'. NO omitas los tiempos ni los precios. Es el corazón de la cotización.\n"
                    "7. NO uses caracteres extraños ni saltos de línea escapados (\\n). Para negritas usa asteriscos dobles (**texto**). NO uses los corchetes [] bajo ninguna circunstancia.\n"
                    f"8. Agrega textualmente el 'TEXTO OBLIGATORIO' sobre Gobernanza al final del documento. {legal_text}\n"
                    "9. MÁXIMA PRIORIDAD - DESGLOSE DE COSTOS Y HORAS: Haz que la sección de costos sea la MÁS GRANDE y EXTREMADAMENTE DETALLADA de la cotización. Para llegar al 'Costo de la Inversión' final estipulado, DEBES desglosar CADA fase del proyecto (Planificación, Diseño UX/UI, Desarrollo Frontend, Desarrollo Backend, Pruebas y QA, Despliegue, etc.). Para cada fase es OBLIGATORIO inventar razonablemente la cantidad de horas ('son tantas horas') y multiplicarlo por una tarifa hora coherente (entre 55 EUR y 140 EUR la hora, acorde al mercado de Andorra/Europa), detallando la fórmula exacta: [XX horas * YY EUR/hr = ZZ EUR], de manera que la SUMA TOTAL OBLIGATORIAMENTE DEBE COINCIDIR EXACTAMENTE con el Costo Total de Inversión dictado en este prompt."
                )
                
                llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
                
                human_prompt = (
                    f"Genera exactamente ÚNICAMENTE el texto de la Cotización PDF basándote en lo siguiente:\n"
                    f"Ciudad: Andorra\n"
                    f"Fecha: {today_str}\n"
                    f"Código de Cotización: {quote_code}\n"
                    f"Nombre del Cliente: {name}\n"
                    f"Nombre del Contacto: {name}\n"
                    f"Correo: {email}\n"
                    f"Proyecto Corto: {project_details}\n"
                    f"Tiempo Estimado de Ejecución (OBLIGATORIO IMPRIMIRLO): {estimated_time}\n"
                    f"Costo de la Inversión (OBLIGATORIO IMPRIMIRLO COMO TOTAL FINAL EXACTO): {safe_cost}\n"
                    f"Información Proveedor Comercial (Firma y Datos): Empresa {c_name}, NIT {c_id}, Tel {c_phone}, Web {c_web}\n"
                    f"Resumen del Asesor (Lo que el cliente quiere): {detailed_proposal}\n"
                )

                messages = [
                    SystemMessage(content=system_prompt_text + "\n\n" + strict_rules),
                    HumanMessage(content=human_prompt)
                ]
                print("⏳ Llamando a GPT-4o para redactar la propuesta comercial formal (16 Puntos)...")
                llm_response = llm.invoke(messages)
                
                full_proposal = llm_response.content
                
                pdf.set_fill_color(*color_heading)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font(family, "B", size)
                pdf.cell(0, 10, "Propuesta Técnica y Comercial:", new_x="LMARGIN", new_y="NEXT", fill=True)
                
                pdf.set_text_color(*color_text)
                pdf.set_font(family, "", size)
                
                # Cleanup chars that break FPDF's default latin-1 and unwanted markdown artifacts
                safe_proposal = full_proposal.replace("€", "EUR").replace("•", "-").replace("·", "-").replace("–", "-").replace("# ", "").replace("## ", "").replace("### ", "").replace("```", "").replace("\n\n\n", "\n\n")
                safe_proposal = safe_proposal.replace(r"\n", "\n") # Fix literal escaped newlines just in case
                safe_proposal = safe_proposal.encode('latin-1', 'ignore').decode('latin-1')
                
                pdf.multi_cell(0, 6, safe_proposal, markdown=True)
                pdf.ln(5)
            else:
                # Details block with background
                pdf.set_fill_color(*color_heading)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font(family, "B", size)
                pdf.cell(0, 10, "Detalles del Proyecto:", new_x="LMARGIN", new_y="NEXT", fill=True)
                
                pdf.set_text_color(*color_text)
                pdf.set_font(family, "", size)
                
                pdf.multi_cell(0, 10, f"- Requerimiento: {project_details}\\n- Tiempo Estimado: {estimated_time}\\n- Inversión Aproximada: {safe_cost}")
                pdf.ln(10)
            
            # Binary PDF output for Resend
            pdf_bytes_global = bytes(pdf.output())
            
            # 2. Setup standard SMTP
            if not smtp_obj or not smtp_obj.smtp_host or not smtp_obj.smtp_pass:
                return {"status": "error", "result_text": "Dile al usuario: 'El sistema no tiene un servidor SMTP configurado para enviar correos. Pide a soporte que ingrese las claves.'"}
            
            msg = EmailMessage()
            msg["Subject"] = "Tu Cotización de Software Comercial"
            from_name = getattr(smtp_obj, "from_name", None) or "Xkape Bot"
            from_email = getattr(smtp_obj, "from_email", None) or "soporte@xkape.bot"
            msg["From"] = f"{from_name} <{from_email}>"
            msg["To"] = email
            
            bcc = getattr(smtp_obj, "bcc_email", None)
            if bcc and bcc.strip():
                msg["Bcc"] = bcc.strip()
                
            msg.set_content(f"Hola {name},\n\nAdjunto la cotización validada por nuestra Inteligencia Artificial.\nUno de nuestros asesores comerciales se contactará pronto.\n\n(Registro Interno: Cotización solicitada por {name})")
            msg.add_attachment(pdf_bytes_global, maintype='application', subtype='pdf', filename='Cotizacion.pdf')
            
            # 3. Send Email via standard SMTP (Supports Resend SMTP, Gmail, etc)
            import socket
            try:
                if smtp_obj.smtp_port == 465:
                    with smtplib.SMTP_SSL(smtp_obj.smtp_host, smtp_obj.smtp_port, timeout=15) as server:
                        server.login(smtp_obj.smtp_user, smtp_obj.smtp_pass)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(smtp_obj.smtp_host, smtp_obj.smtp_port, timeout=15) as server:
                        server.starttls()
                        server.login(smtp_obj.smtp_user, smtp_obj.smtp_pass)
                        server.send_message(msg)
            except socket.timeout:
                return {"status": "error", "result_text": "Dile al usuario: 'El servidor de correos no responde (Timeout). Revisa la configuración del dashboard para asegurarte de que el host y el puerto (ej. 465 o 587) sean correctos.'"}
            
            return {"status": "success", "result_text": f"Dile al usuario que acabas de enviarle la cotización formal en PDF con los colores corporativos directamente a su correo {email}."}
            
        except smtplib.SMTPAuthenticationError:
            return {"status": "error", "result_text": "Dile al usuario: 'No pude enviar el correo porque las credenciales (usuario/contraseña SMTP) son inválidas. Revisa la configuración del servidor en el dashboard.'"}
        except smtplib.SMTPException as smtp_e:
            return {"status": "error", "result_text": f"Dile al usuario: 'El servidor SMTP rechazó el mensaje (quizás el dominio no está verificado). Detalle: {smtp_e}'"}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "result_text": f"Dile al usuario: 'Hubo un problema técnico enviando el correo. Detalle: {e}'"}
        
    else:
        raise HTTPException(status_code=404, detail="Tool not found")
