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
    # Obtenemos agent_manager desde request.app.state o importándolo, pero aquí usamos
    # el global de main.py mediante un getter simple o import deferido si es necesario.
    # Dado que es mejor inyectarlo o accederlo vía app.state:
    agent_manager = request.app.state.agent_manager
    project_id = request_data.project_id
    args = request_data.args
    
    if function_name == "consult_knowledge_base":
        query = args.get("query", "")
        retriever = agent_manager.vector_store.get_retriever(k=3, project_id=project_id)
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
        if raw_docs:
            for d in raw_docs:
                meta_loc = d.metadata.get("location_search", "")
                meta_type = d.metadata.get("property_type", "")
                
                if location.lower() != "any" and location.lower() not in meta_loc and location.lower() not in d.page_content.lower():
                    continue
                if tipo.lower() != "any" and tipo.lower() not in meta_type and tipo.lower() not in d.page_content.lower():
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
            
            # 1. Generate PDF
            pdf = FPDF()
            pdf.add_page()
            
            # Global Font
            try: pdf.set_font(family, size=size)
            except: pdf.set_font("helvetica", size=size) # fallback
            
            # Title
            pdf.set_text_color(*color_heading)
            pdf.set_font(family, "B", size + 6)
            pdf.cell(0, 10, "Cotización de Software", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(10)
            
            # Greet
            pdf.set_text_color(*color_text)
            pdf.set_font(family, "", size)
            pdf.multi_cell(0, 8, f"Estimado/a {name},\\n\\nAdjuntamos la estimación para su requerimiento de software:")
            pdf.ln(5)
            
            # Details block with background
            pdf.set_fill_color(*color_heading)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font(family, "B", size)
            pdf.cell(0, 10, "Detalles del Proyecto:", new_x="LMARGIN", new_y="NEXT", fill=True)
            
            pdf.set_text_color(*color_text)
            pdf.set_font(family, "", size)
            pdf.multi_cell(0, 10, f"- Requerimiento: {project_details}\\n- Tiempo Estimado: {estimated_time}\\n- Inversión Aproximada: {estimated_cost}")
            pdf.ln(10)
            
            pdf.multi_cell(0, 8, "Esta es una cotización automatizada generada por Inteligencia Artificial. Un agente humano se pondrá en contacto pronto para afinar detalles.")
            
            # Binary PDF output for Resend
            pdf_bytes_global = list(bytes(pdf.output()))
            
            # 2. Setup Resend
            resend_api_key = smtp_obj.smtp_pass if smtp_obj and smtp_obj.smtp_pass else "re_default_invalid"
            resend.api_key = resend_api_key
            from_email = smtp_obj.from_email if smtp_obj and smtp_obj.from_email else "soporte@xkape.bot"
            
            # 3. Send Email
            payload = {
                "from": from_email,
                "to": email,
                "subject": "Tu Cotización de Software Comercial",
                "html": "<p>Adjunto la cotización validada por nuestra Inteligencia Artificial.</p>",
                "attachments": [
                    {
                        "filename": "Cotizacion.pdf",
                        "content": pdf_bytes_global,
                        "content_type": "application/pdf"
                    }
                ]
            }
            resend.Emails.send(payload)
            
            return {"status": "success", "result_text": f"Dile al usuario que acabas de enviarle la cotización formal en PDF con los colores corporativos directamente a su correo {email}."}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"status": "error", "result_text": f"Hubo un fallo generando el PDF o enviando el correo. Informale de esto al usuario. Detalle técnico: {e}"}
        
    else:
        raise HTTPException(status_code=404, detail="Tool not found")
