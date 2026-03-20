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
        
        retriever = agent_manager.vector_store.get_retriever(k=300, project_id=project_id)
        raw_docs = retriever.invoke(search_query)
        
        filtered_docs = []
        seen_ids = set()
        
        def normalize_str(s):
            import unicodedata
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()
            
        loc_norm = normalize_str(location) if location.lower() != "any" else ""
        type_norm = normalize_str(tipo) if tipo.lower() != "any" else ""
        
        if raw_docs:
            for d in raw_docs:
                p_id = d.metadata.get("property_id")
                if p_id and p_id in seen_ids:
                    continue
                if p_id: seen_ids.add(p_id)
                
                page_norm = normalize_str(d.page_content)
                meta_loc = normalize_str(d.metadata.get("location_search", ""))
                meta_type = normalize_str(d.metadata.get("property_type", ""))
                
                if loc_norm and loc_norm not in meta_loc and loc_norm not in page_norm:
                    continue
                if type_norm and type_norm not in meta_type and type_norm not in page_norm:
                    continue
                    
                filtered_docs.append(d)
                if len(filtered_docs) >= 100:
                    break
        
        raw_properties = []
        import re
        for d in filtered_docs:
            content = d.page_content
            title_match = re.search(r"TÍTULO:\s*(.*)", content)
            title = title_match.group(1).strip() if title_match else "Propiedad"
            
            price_match = re.search(r"TIPO DE NEGOCIO:\s*(.*)", content)
            price_str = price_match.group(1).strip() if price_match else "0"
            numerics = re.findall(r"\d+", price_str.replace(".", ""))
            precio_int = int(numerics[0]) if numerics else 0
            
            prop_id = d.metadata.get("property_id", "")
            url_res = re.search(r"ENLACE PARA EL CLIENTE:\s*(.*)", content)
            link_str = url_res.group(1).strip() if url_res else ""
            
            raw_properties.append({
                "id": prop_id,
                "titulo": title,
                "precio": precio_int,
                "link": link_str,
                "imagenes": [] # La db vectorial no guarda blobs, se deja vacío para que React Native no crashee
            })
        
        if filtered_docs:
            llm_limit = min(int(limit), 15)
            llm_docs = filtered_docs[:llm_limit]
            
            result_text = f"RESULTADO DE BASE DE DATOS: Encontré {len(filtered_docs)} opciones en total. Aquí tienes las top {len(llm_docs)}:\\n"
            for i, d in enumerate(llm_docs):
                snippet = d.page_content[:350] + "..." if len(d.page_content) > 350 else d.page_content
                result_text += f"\\n[{i+1}] {snippet}\\n"
            result_text += "\\nREGLA: Describe estas opciones de forma atractiva. Diles el precio y barrio."
        else:
            result_text = f"Revisé la base de datos extensamente pero NO hay ningún inmueble tipo {tipo} disponible en el sector de {location}. Infórmale esto de inmediato."
            
        return {"status": "success", "result_text": result_text, "raw_properties": raw_properties}
        
    elif function_name == "schedule_appointment":
        name = args.get("client_name")
        pid = args.get("property_id")
        mock_result = f"Perfect! I have scheduled an appointment for {name} to see {pid}. A confirmation SMS was just sent."
        return {"status": "success", "result_text": mock_result}
        
    elif function_name == "generate_software_quote":
        name = args.get("client_name", "Cliente")
        email = args.get("client_email")
        country = args.get("client_country", "País no especificado")
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
            color_heading = hex_to_rgb_tuple("#36AA32")
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
            # Global Font
            try: pdf.set_font(family, size=size)
            except: pdf.set_font("helvetica", size=size) # fallback
            
            # (El saludo "Estimado" se elimina ya que el usuario pidió quitarlo y usar el LLM para iniciar sin saludo)
            
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
                )

                strict_rules = (
                    "ERES UN REDACTOR EXPERTO Y DEBES SEGUIR OBLIGATORIAMENTE ESTA PLANTILLA EXACTA.\n"
                    "Copia la estructura al pie de la letra, manteniendo los espacios y la numeración exacta de los títulos (ej. '##1. Introducción').\n"
                    "OBLIGATORIO: Sustituye los valores entre corchetes con la información real, calcúlala lógicamente para que todo coincida, pero NO PONGAS PRECIOS EN EL ALCANCE.\n\n"
                    "PLANTILLA OBLIGATORIA:\n"
                    "PROPUESTA DE DESARROLLO DE SOFTWARE\n\n"
                    "Estimado/a [Nombre del Cliente],\n\n"
                    "Adjuntamos la estimación para su requerimiento de software:\n\n"
                    "Propuesta Técnica y Comercial:\n"
                    "Ciudad y Fecha: [Capital del país], [Fecha de hoy]\n"
                    "Código de Cotización: [Código]\n"
                    "Nombre del Cliente: [Nombre del Cliente]\n"
                    "Nombre del Contacto: [Nombre del Contacto]\n"
                    "Nombre del Proyecto: [Nombre del Proyecto]\n"
                    "Asunto: Propuesta para el desarrollo de [Tema]\n"
                    "---\n\n"
                    "##1. Introducción\n"
                    "Estimado Sr./Sra. [Apellido del cliente],\n"
                    "En respuesta a su solicitud, nos complace presentar la propuesta para el desarrollo de [Proyecto]. Este proyecto está diseñado para satisfacer la necesidad de [Objetivo principal], optimizado para su funcionamiento en [País] y a nivel mundial.\n\n"
                    "##2. Descripción del Proyecto\n"
                    "[Escribe 1 párrafo detallando de qué trata el software/app, cómo funcionará y plataformas objetivo]\n\n"
                    "##3. Alcance del Proyecto\n"
                    "Fases y Horas Estimadas (Asigna un total de horas uniforme para que el subtotal matemático cuadre exactamente a 50 EUR/hora según el sugerido):\n"
                    "- Fase 1: [Nombre de fase] - [XX] horas\n"
                    "(Agrega las fases necesarias dictadas por la lógica del software)\n\n"
                    "##4. Módulos, Componentes o Servicios Incluidos\n"
                    "- [Lista viñeteada de módulos]\n\n"
                    "##5. Entregables\n"
                    "- [Lista viñeteada de entregables, ej. Código fuente, Manuales, Despliegue...]\n\n"
                    "##6. Tecnologías a Utilizar\n"
                    "- [Lista viñeteada de tecnologías front, back, db, etc.]\n\n"
                    "##7. Tiempo Estimado de Ejecución\n"
                    "La duración total estimada para la ejecución del proyecto es de [Tiempo estimado], comenzando formalmente tras la aprobación final y recepción de los insumos necesarios del cliente.\n\n"
                    "##8. Garantía y Soporte\n"
                    "- Tiempo de Garantía: 6 meses posteriores al despliegue\n"
                    "- Cobertura: Corrección de errores y soporte técnico básico\n"
                    "- Exclusiones: Modificaciones y nuevas funcionalidades\n\n"
                    "##9. Inversión o Costo del Proyecto\n"
                    "OBLIGATORIO: Toma el punto medio exacto de la Inversión Sugerida. Usa una tarifa estandarizada de 50 EUR/hora y multiplica para que el subtotal inicial coincida. Investiga y aplica el porcentaje de IVA/Tax correspondiente al país del usuario.\n"
                    "- Fase 1: [Nombre] - [XX] horas a 50 EUR/hora = [ZZZ] EUR\n"
                    "(Desglosa cada fase de manera idéntica al Alcance acordando la suma)\n"
                    "Subtotal general: [Suma de fases] EUR\n"
                    "Descuento Comercial (10%): -[Monto] EUR\n"
                    "Base Imponible Neto: [Neto] EUR\n"
                    "Impuestos ([Nombre del Impuesto y Porcentaje (%) aplicable en el País del Cliente, Ej. IVA 21%, VAT 18%, IVA 19%, o Exento]): [Impuesto Calculado sobre Neto] EUR\n"
                    "Inversión Total a Pagar: [Total Final Matemático] EUR\n\n"
                    "##10. Costos Operativos No Incluidos\n"
                    "- Hosting y servidores en AWS\n"
                    "- Licencias de software de terceros\n"
                    "- Costos de mantenimiento recurrente\n\n"
                    "##11. Forma de Pago\n"
                    "- Anticipo del 30% al inicio del proyecto\n"
                    "- 40% al completar la fase de Desarrollo Backend\n"
                    "- 30% al finalizar el despliegue y monitoreo\n\n"
                    "##12. Consideraciones Finales\n"
                    "- Cualquier cambio fuera del alcance será cotizado aparte.\n"
                    "- Los tiempos están sujetos a aprobaciones oportunas del cliente.\n"
                    "- Cuentas de terceros deben estar a nombre del cliente.\n"
                    "- La propuesta tiene vigencia comercial de 30 días.\n\n"
                    "##13. Datos de Pago y Cierre Comercial\n"
                    "Nombre de la Empresa Proveedora: [Nombre Empresa]\n"
                    "Teléfono: [Teléfono Empresa]\n"
                    "Web: [Web Empresa]\n\n"
                    "##14. Firma o Cierre Final\n"
                    "Agradecemos la oportunidad de colaborar en este proyecto y esperamos poder iniciar una relación comercial fructífera. No dude en contactarnos para cualquier consulta adicional.\n"
                )
                
                llm = ChatOpenAI(model="gpt-4o", temperature=0.7)
                
                human_prompt = (
                    f"Genera exactamente ÚNICAMENTE el texto de la Cotización PDF basándote en lo siguiente:\n"
                    f"País del Proyecto: {country}\n"
                    f"Fecha: {today_str}\n"
                    f"Código de Cotización: {quote_code}\n"
                    f"Nombre del Cliente: {name}\n"
                    f"Nombre del Contacto: {name}\n"
                    f"Correo: {email}\n"
                    f"Proyecto Corto: {project_details}\n"
                    f"Tiempo Estimado de Ejecución (OBLIGATORIO IMPRIMIRLO): {estimated_time}\n"
                    f"Costo de la Inversión Sugerido (TÓMALO SOLO COMO REFERENCIA INICIAL): {safe_cost}\n"
                    f"Información Proveedor Comercial (Firma y Datos): Empresa {c_name}, Tel {c_phone}, Web {c_web}\n"
                    f"Resumen del Asesor (Lo que el cliente quiere): {detailed_proposal}\n"
                )

                messages = [
                    SystemMessage(content=system_prompt_text + "\n\n" + strict_rules),
                    HumanMessage(content=human_prompt)
                ]
                print("⏳ Llamando a GPT-4o para redactar la propuesta comercial formal (16 Puntos)...")
                llm_response = llm.invoke(messages)
                
                full_proposal = llm_response.content + "\n\n---\n\n" + legal_text
                
                pdf.set_text_color(*color_text)
                pdf.set_font(family, "", size)
                
                # Cleanup chars that break FPDF's default latin-1 and unwanted markdown artifacts
                safe_proposal = full_proposal.replace("€", "EUR").replace("•", "-").replace("·", "-").replace("–", "-").replace("```", "")
                safe_proposal = safe_proposal.replace(r"\n", "\n") # Fix literal escaped newlines just in case
                safe_proposal = safe_proposal.encode('latin-1', 'ignore').decode('latin-1')
                
                # Custom line-by-line renderer to color Markdown titles #36AA32
                import re
                KNOWN_HEADERS = [
                    "1. Introducción", "2. Descripción del Proyecto", "3. Alcance del Proyecto",
                    "4. Módulos, Componentes o Servicios Incluidos", "5. Entregables",
                    "6. Tecnologías a Utilizar", "7. Tiempo Estimado de Ejecución",
                    "8. Garantía y Soporte", "9. Inversión o Costo del Proyecto", 
                    "10. Costos Operativos No Incluidos", "11. Forma de Pago", 
                    "12. Consideraciones Finales", "13. Datos de Pago y Cierre Comercial",
                    "14. Firma o Cierre Final", "Gobernanza", "Consideraciones legales"
                ]
                
                lines = safe_proposal.split('\n')
                for line in lines:
                    stripped = line.strip()
                    if not stripped:
                        pdf.ln(5)
                        continue
                    
                    # Regex to remove ONLY markdown hashes. It keeps numbers. (e.g. '##1. Introducción' -> '1. Introducción')
                    clean_line = re.sub(r'^#*\s*', '', stripped).strip().replace("**", "")
                    
                    is_header = False
                    for h in KNOWN_HEADERS:
                        if clean_line.startswith(h):
                            is_header = True
                            clean_line = clean_line # Keep the exact numbered header as requested
                            break
                    
                    if is_header:
                        pdf.ln(4)
                        pdf.set_text_color(*color_heading) # Corporate Green #36AA32
                        pdf.set_font(family, "B", size + 1)
                        try:
                            pdf.multi_cell(0, 8, clean_line, new_x="LMARGIN", new_y="NEXT")
                        except Exception as e:
                            print(f"FPDF Error header: {clean_line} -> {e}")
                        
                        pdf.set_text_color(*color_text)
                        pdf.set_font(family, "", size)
                    elif stripped.startswith("**") and stripped.endswith("**"):
                        # Basic bold for full bold lines
                        pdf.set_font(family, "B", size)
                        try:
                            pdf.multi_cell(0, 6, stripped.replace("**", ""), new_x="LMARGIN", new_y="NEXT")
                        except Exception as e:
                            print(f"FPDF Error in bold line: {stripped} -> {e}")
                        pdf.set_font(family, "", size)
                    else:
                        # Standard Markdown processing for normal lines (handles bold in the middle)
                        try:
                            pdf.multi_cell(0, 6, stripped, new_x="LMARGIN", new_y="NEXT")
                        except Exception as e:
                            print(f"FPDF Error in markdown line: {stripped} -> {e}")
                
                pdf.ln(5)
            else:
                # Details block with background
                pdf.set_fill_color(*color_heading)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font(family, "B", size)
                pdf.cell(0, 10, "Detalles del Proyecto:", new_x="LMARGIN", new_y="NEXT", fill=True)
                
                pdf.set_text_color(*color_text)
                pdf.set_font(family, "", size)
                
                pdf.multi_cell(0, 10, f"- Requerimiento: {project_details}\\n- Tiempo Estimado: {estimated_time}\\n- Inversión Aproximada: {safe_cost}", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(10)
            
            # Binary PDF output for Resend
            pdf_bytes_global = bytes(pdf.output())
            
            # Debug tool: Intercept and save the absolute final PDF block locally before trusting SMTP
            try:
                with open("/tmp/latest_quote_debug.pdf", "wb") as debug_file:
                    debug_file.write(pdf_bytes_global)
                print("✅ TEST LOCAL: Se guardó en /tmp/latest_quote_debug.pdf")
            except Exception as e:
                print(f"Error escribiendo PDF debug local: {e}")
            
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
