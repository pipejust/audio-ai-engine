from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(tags=["Tools"])

class ToolRequest(BaseModel):
    project_id: str
    args: Dict[str, Any]

@router.post("/{function_name}")
async def execute_tool(function_name: str, request_data: ToolRequest, request: Request):
    """
    Endpoint dinámico para ejecutar herramientas.
    Este endpoint simula los Web Services externos para cada tenant.
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
            pdf.multi_cell(0, 8, f"Estimado/a {name},\\n\\nAdjuntamos la estimación para su requerimiento de software:")
            pdf.ln(5)
            
            # FPDF's default Helvetica does not support the € symbol in latin-1. Replace it to avoid crashes.
            safe_cost = estimated_cost.replace("€", "EUR")
            
            if detailed_proposal:
                pdf.set_fill_color(*color_heading)
                pdf.set_text_color(255, 255, 255)
                pdf.set_font(family, "B", size)
                pdf.cell(0, 10, "Propuesta Técnica y Comercial:", new_x="LMARGIN", new_y="NEXT", fill=True)
                
                pdf.set_text_color(*color_text)
                pdf.set_font(family, "", size)
                # Cleanup chars that break FPDF's default latin-1 and strip basic markdown
                safe_proposal = detailed_proposal.replace("€", "EUR").replace("•", "-").replace("·", "-").replace("–", "-").replace("**", "").replace("*", "").replace("# ", "")
                safe_proposal = safe_proposal.encode('latin-1', 'ignore').decode('latin-1')
                pdf.multi_cell(0, 6, safe_proposal)
                pdf.ln(5)
                
                pdf.set_fill_color(240, 240, 240)
                pdf.set_font(family, "B", size)
                pdf.multi_cell(0, 8, f"Resumen: {project_details}\\nTiempo Estimado: {estimated_time}\\nInversión Aproximada: {safe_cost}", fill=True)
                pdf.ln(10)
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
            
            pdf.multi_cell(0, 8, "Esta es una cotización automatizada generada por Inteligencia Artificial. Un agente humano se pondrá en contacto pronto para afinar detalles.")
            
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
