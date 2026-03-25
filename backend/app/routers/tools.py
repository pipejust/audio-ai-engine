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
        def extract(regex, text, default=""):
            match = re.search(regex, text)
            return match.group(1).strip() if match else default

        for d in filtered_docs:
            content = d.page_content
            title = extract(r"TÍTULO:\s*(.*)", content, "Propiedad")
            
            price_str = extract(r"TIPO DE NEGOCIO:\s*(.*)", content)
            numerics = re.findall(r"\d+", price_str.replace(".", ""))
            precio_int = int(numerics[0]) if numerics else 0
            
            prop_id = d.metadata.get("property_id", "")
            url = extract(r"ENLACE PARA EL CLIENTE:\s*(.*)", content)
            location = extract(r"UBICACIÓN:\s*(.*)", content)
            
            rooms_str = extract(r"-\s*Habitaciones:\s*(\d+)", content, "0")
            rooms = int(rooms_str) if rooms_str.isdigit() else 0
            
            bathrooms_str = extract(r"-\s*Baños:\s*(\d+)", content, "0")
            bathrooms = int(bathrooms_str) if bathrooms_str.isdigit() else 0
            
            area_str = extract(r"-\s*Área:\s*([\d\.]+)", content, "0")
            area = float(area_str) if area_str.replace(".","",1).isdigit() else 0.0
            
            features_str = extract(r"AMENIDADES:\s*(.*)", content)
            features = [f.strip() for f in features_str.split(",") if f.strip() and f.strip() != "No listadas"]
            
            desc = extract(r"DESCRIPCIÓN:\s*(.*)", content)
            if len(desc) > 500:
                desc = desc[:497] + "..."
                
            zone_parts = location.split(",")
            zone = zone_parts[1].strip() if len(zone_parts) > 1 else location
            
            stratum_str = extract(r"-\s*Estrato:\s*(\d+)", content, "0")
            stratum = int(stratum_str) if stratum_str.isdigit() else 0
            
            built_time = extract(r"-\s*Tiempo de construcción:\s*(.*)", content, "N/A")
            
            prop_type_raw = d.metadata.get("property_type", "casa").lower()
            if "apartamento" in prop_type_raw or "apto" in prop_type_raw:
                prop_type_mapped = "apartment"
            elif "lote" in prop_type_raw or "finca" in prop_type_raw:
                prop_type_mapped = "land"
            elif "local" in prop_type_raw or "oficina" in prop_type_raw or "bodega" in prop_type_raw or "comercial" in prop_type_raw:
                prop_type_mapped = "commercial"
            else:
                prop_type_mapped = "house"
            
            # Dinamic matching calculation
            matching_score = 0.95
            if loc_norm:
                meta_loc_val = normalize_str(d.metadata.get("location_search", ""))
                # If location matches main metadata precisely (Zone/City) vs generic text mentions
                if loc_norm in meta_loc_val:
                    matching_score = 0.98 - (len(raw_properties) * 0.02)
                else:
                    matching_score = 0.85 - (len(raw_properties) * 0.02)
            else:
                matching_score = 0.90 - (len(raw_properties) * 0.01)
                
            if matching_score < 0.60:
                matching_score = 0.60
                
            matching_score = round(matching_score, 2)
            
            raw_properties.append({
                "id": str(prop_id),
                "title": title,
                "location": location,
                "zone": zone,
                "price": precio_int,
                "area": area,
                "rooms": rooms,
                "bathrooms": bathrooms,
                "type": prop_type_mapped,
                "features": features,
                "images": [],
                "matching": matching_score,
                "description": desc,
                "projectInfo": {
                    "stratum": stratum,
                    "status": built_time
                },
                "createdAt": "2026-03-22T00:00:00Z",
                "link": url
            })
            
        import concurrent.futures
        from app.services.wasi_api import WasiAPI
        import requests
        
        wasi_client = WasiAPI()
        
        def fetch_live_wasi_property(pid):
            """
            Fetches the live property data directly from WASI to ensure price, status and images are 100% fresh.
            Returns (pid, live_data_dict) or (pid, None) if unavailable/sold.
            """
            try:
                payload = wasi_client._get_payload({"id_property": pid})
                res = requests.post(f"{wasi_client.base_url}/property/search", data=payload, headers=wasi_client._get_headers(), timeout=4.0)
                data = res.json()
                for v in data.values():
                    if isinstance(v, dict) and str(v.get("id_property")) == str(pid):
                        # Extract ALL images
                        images = []
                        if "main_image" in v and isinstance(v["main_image"], dict):
                            img_obj = v["main_image"]
                            best_url = img_obj.get("url_original") or img_obj.get("url_big") or img_obj.get("url")
                            if best_url:
                                images.append(best_url)
                            
                        galleries = v.get("galleries", [])
                        if isinstance(galleries, list) and len(galleries) > 0:
                            for k, img_obj in galleries[0].items():
                                if k.isdigit() and isinstance(img_obj, dict):
                                    best_url = img_obj.get("url_original") or img_obj.get("url_big") or img_obj.get("url")
                                    if best_url and best_url not in images:
                                        images.append(best_url)
                        
                        # Extract live price
                        sale_price = int(v.get("sale_price", 0) or 0)
                        rent_price = int(v.get("rent_price", 0) or 0)
                        final_price = rent_price if rent_price > 0 else sale_price
                        
                        return pid, {
                            "images": images, # Send ALL images without slicing
                            "live_price": final_price,
                            "status_label": v.get("status_on_page_label", "Activo")
                        }
            except Exception as e:
                print(f"Error fetching live WASI property {pid}: {e}")
                pass
            return pid, None
            
        if filtered_docs:
            llm_limit = min(int(limit), 5)
            # The top properties semantically matched
            top_properties = raw_properties[:llm_limit]
            
            # Fetch their LIVE payloads concurrently
            import time
            start_wasi = time.time()
            live_data_map = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_pid = {executor.submit(fetch_live_wasi_property, rp["id"]): rp["id"] for rp in top_properties}
                for future in concurrent.futures.as_completed(future_to_pid):
                    try:
                        pid, live_data = future.result()
                        live_data_map[str(pid)] = live_data
                    except Exception as e:
                        print("Future error:", e)
            print("WASI Hydration took:", time.time() - start_wasi)
                        
            # Filter and update raw_properties with LIVE data
            valid_live_properties = []
            for rp in top_properties:
                live_info = live_data_map.get(str(rp["id"]))
                if live_info is None:
                    # Inmueble bajado de WASI o inactivo, lo ignoramos para no mandar basura a la IA
                    continue
                    
                # Update with verified fresh data
                rp["images"] = live_info["images"]
                if live_info["live_price"] > 0:
                    rp["price"] = live_info["live_price"]
                
                valid_live_properties.append(rp)
                
            raw_properties = valid_live_properties
            llm_docs = [d for d in filtered_docs if str(d.metadata.get("property_id")) in [rp["id"] for rp in raw_properties]]
            
            result_text = f"RESULTADO DE BASE DE DATOS: Encontré {len(filtered_docs)} opciones en total. Aquí tienes las top {len(llm_docs)}:\\n"
            for i, d in enumerate(llm_docs):
                snippet = d.page_content[:350] + "..." if len(d.page_content) > 350 else d.page_content
                result_text += f"\\n[{i+1}] {snippet}\\n"
            result_text += "\\nREGLA: Describe estas opciones de forma atractiva. Diles el precio y barrio."
        else:
            result_text = f"Revisé la base de datos extensamente pero NO hay ningún inmueble tipo {tipo} disponible en el sector de {location}. Infórmale esto de inmediato."
            
        return {"status": "success", "result_text": result_text, "raw_properties": raw_properties}
    elif function_name == "open_property_details":
        listing_id = args.get("listing_id")
        return {
            "status": "success",
            "result_text": "Dile amablemente al usuario: '¡Claro! Aquí tienes los detalles e imágenes de la propiedad en pantalla.'",
            "action": "view_details",
            "listing_id": listing_id
        }
        
    elif function_name == "schedule_visits":
        client_name = args.get("client_name", "")
        client_email = args.get("client_email", "")
        client_phone = args.get("client_phone", "+57 300 000 0000")
        appointments = args.get("appointments", [])
        
        if not client_email or client_email.strip() == "":
            return "ERROR CRÍTICO: El usuario es un invitado no registrado. Tienes OBLIGATORIAMENTE que responderle: 'Para agendar una cita o visita, primero debes iniciar sesión o registrarte usando el botón del panel lateral.'"
        
        # 1. Init external APIs using scoped imports
        import os
        import uuid
        import requests
        from datetime import datetime
        from app.services.wasi_api import WasiAPI
        
        wasi_client = WasiAPI()
        
        try:
            from supabase import create_client, Client
            sb_url = os.environ.get("SUPABASE_URL")
            sb_key = os.environ.get("SUPABASE_KEY")
            supabase_client = create_client(sb_url, sb_key)
        except Exception as e:
            print(f"Supabase client init failed: {e}")
            supabase_client = None
            
        target_table = os.getenv("SUPABASE_APPOINTMENTS_TABLE", "appointments_system")
        inserted_appointments = []
        
        # Obtener vendedor de respaldo dinámico desde api_integrations
        default_vendedor_nombre = "Busco Fácil IA"
        default_vendedor_email = "ventas@buscofacil.com"
        default_vendedor_celular = "+57 300 000 0000"
        
        if supabase_client:
            try:
                res_api = supabase_client.table("api_integrations").select("configuracion").eq("activa", True).limit(1).execute()
                if res_api.data and len(res_api.data) > 0:
                    config = res_api.data[0].get("configuracion", {})
                    if isinstance(config, dict):
                        seller_info = config.get("seller_info", {})
                        if isinstance(seller_info, dict) and seller_info:
                            default_vendedor_nombre = seller_info.get("name", default_vendedor_nombre)
                            default_vendedor_email = seller_info.get("email", default_vendedor_email)
                            default_vendedor_celular = seller_info.get("phone", default_vendedor_celular)
                        else:
                            # Fallback to root configuracion
                            default_vendedor_email = config.get("correo", default_vendedor_email)
                            default_vendedor_nombre = config.get("nombre_asesor", default_vendedor_nombre)
                            default_vendedor_celular = config.get("telefono_asesor", default_vendedor_celular)
            except Exception as e:
                print(f"Error fetching api_integrations fallback seller: {e}")
        
        for appt in appointments:
            pid = appt.get("listing_id")
            
            # Default WASI mapping payload
            wasi_title = f"Inmueble ID {pid}"
            wasi_type = "property"
            wasi_address = "No especificada"
            wasi_city = "No especificada"
            wasi_map = ""
            wasi_lat = None
            wasi_lng = None
            wasi_price = 0
            wasi_area = 0
            wasi_rooms = 0
            wasi_bathrooms = 0
            wasi_garages = 0
            wasi_age = "0"
            wasi_stratum = "0"
            vendedor_nombre = default_vendedor_nombre
            vendedor_email = default_vendedor_email
            vendedor_celular = default_vendedor_celular
            
            # Hydrate via WASI POST hook
            try:
                payload = wasi_client._get_payload({"id_property": pid})
                res = requests.post(f"{wasi_client.base_url}/property/search", data=payload, headers=wasi_client._get_headers(), timeout=5.0)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict) and str(data.get("total", "0")) == "1":
                        v = data.get("0", {})
                        wasi_title = v.get("title", wasi_title)
                        wasi_type = v.get("property_type_label", wasi_type)
                        wasi_address = v.get("address", wasi_address)
                        
                        raw_city = v.get("city_label", wasi_city)
                        if isinstance(raw_city, str) and "," in raw_city:
                            co_cities = ["Bogotá", "Medellín", "Cali", "Barranquilla", "Cartagena", "Cúcuta", "Ibagué", "Bucaramanga", "Santa Marta", "Villavicencio", "Pereira", "Pasto", "Manizales", "Montería", "Neiva", "Jamundí", "Palmira", "Yumbo", "Rozo"]
                            matched = False
                            for c in co_cities:
                                if c.lower() in raw_city.lower():
                                    wasi_city = c
                                    matched = True
                                    break
                            if not matched:
                                parts = [p.strip() for p in raw_city.split(",")]
                                wasi_city = parts[-4] if len(parts) >= 4 else parts[-1]
                        else:
                            wasi_city = raw_city
                            
                        wasi_map = v.get("map", "")
                        wasi_lat = v.get("latitude")
                        wasi_lng = v.get("longitude")
                        wasi_price = max(int(v.get("sale_price", 0) or 0), int(v.get("rent_price", 0) or 0))
                        wasi_area = int(v.get("area", 0) or 0)
                        wasi_rooms = int(v.get("bedrooms", 0) or 0)
                        wasi_bathrooms = int(v.get("bathrooms", 0) or 0)
                        wasi_garages = int(v.get("garages", 0) or 0)
                        wasi_age = str(v.get("building_date", "0"))
                        wasi_stratum = str(v.get("stratum", "0"))
                        
                        # Seller metadata extraction from WASI API
                        user_data = v.get("user_data", {})
                        if user_data:
                            first = user_data.get("first_name", "")
                            last = user_data.get("last_name", "")
                            if first or last:
                                vendedor_nombre = f"{first} {last}".strip()
                            vendedor_email = user_data.get("email", vendedor_email)
                            vendedor_celular = user_data.get("cell_phone", vendedor_celular)
            except Exception as e:
                print(f"Error fetching WASI details for {pid}: {e}")
                
            now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
            
            raw_time = appt.get("time", "00:00")
            if len(raw_time) == 5: # HH:MM conversion to Postgres Time
                raw_time += ":00"
                
            crm_payload = {
                # [1-10] Metadata Core
                "id": str(uuid.uuid4()),
                "inmueble_id": str(pid),
                "inmueble_titulo": wasi_title,
                "inmueble_tipo": wasi_type,
                "inmueble_direccion": wasi_address,
                "inmueble_ciudad": wasi_city,
                "inmueble_coordenadas": wasi_map,
                "inmueble_lat": float(wasi_lat) if wasi_lat else None,
                "inmueble_lng": float(wasi_lng) if wasi_lng else None,
                "inmueble_precio": wasi_price,
                
                # [11-20] Metadata Inmueble (Técnico)
                "inmueble_area": float(wasi_area),
                "inmueble_habitaciones": int(wasi_rooms),
                "inmueble_banos": int(wasi_bathrooms),
                "inmueble_garajes": int(wasi_garages),
                "inmueble_antiguedad": wasi_age,
                "inmueble_estrato": wasi_stratum,
                
                # [21-30] Cliente
                "cliente_id": None,
                "cliente_nombre": client_name,
                "cliente_email": client_email,
                "cliente_celular": client_phone,
                "notas_cliente": "Agendado automáticamente vía Inteligencia Artificial",
                
                # [31-40] Vendedor
                "vendedor_id": None,
                "vendedor_nombre": vendedor_nombre,
                "vendedor_email": vendedor_email,
                "vendedor_celular": vendedor_celular,
                
                # [41-50] Cita Core
                "fecha_cita": appt.get("date", "2026-01-01"),
                "hora_cita": raw_time,
                "hora_inicio": raw_time,
                "hora_fin": None,
                "duracion_minutos": 60,
                
                # [51-54] Estado y Trazabilidad Obligatoria (Diccionario de 10 estados)
                "estado": "pendiente",
                "origen_cita": "bot_inteligencia_artificial",
                "canal_comunicacion": "whatsapp",
                
                # Campos Booleanos y timestamps
                "confirmada_cliente": False,
                "confirmada_vendedor": False,
                "fecha_confirmacion_cliente": None,
                "fecha_confirmacion_vendedor": None,
                
                "activa": True,
                "fecha_creacion": now_iso,
                "ultima_actualizacion": now_iso,
                "notas_internas": "Payload generado dinámicamente desde el bot IA (WASI Hydration loop)."
            }
            
            # Insert into remote DB (admin.buscofacil.com Supabase)
            if supabase_client:
                try:
                    res = supabase_client.table(target_table).insert(crm_payload).execute()
                    print(f"Supabase Insertion OK: {res}")
                except Exception as e:
                    print(f"Supabase Insertion failed for CRM Payload: {e}")
            else:
                print("Skipped Supabase insertion (DB client not configured).")
            
            inserted_appointments.append(crm_payload)
            
        # 2. Dispatch Email Notifications to Vendors
        try:
            from app.db.session import SessionLocal
            from app.db.models import SmtpSettings
            import smtplib
            from email.message import EmailMessage
            
            db = SessionLocal()
            smtp_obj = db.query(SmtpSettings).filter(SmtpSettings.project_id == project_id).first()
            db.close()
            
            if smtp_obj and smtp_obj.smtp_host and smtp_obj.smtp_pass:
                from_name = getattr(smtp_obj, "from_name", None) or "Inteligencia Artificial"
                from_email = getattr(smtp_obj, "from_email", None) or "notificaciones@buscofacil.com"
                
                for appt_payload in inserted_appointments:
                    vendedor_email = appt_payload.get("vendedor_email")
                    if not vendedor_email:
                        continue
                        
                    msg = EmailMessage()
                    msg["Subject"] = f"Nueva Pre-Agenda IA: {appt_payload.get('inmueble_titulo')}"
                    msg["From"] = f"{from_name} <{from_email}>"
                    msg["To"] = vendedor_email
                    
                    bcc = getattr(smtp_obj, "bcc_email", None)
                    if bcc and bcc.strip():
                        msg["Bcc"] = bcc.strip()
                        
                    # Build email body
                    body = f"Hola {appt_payload.get('vendedor_nombre')},\n\n"
                    body += f"Nuestro Asistente de Inteligencia Artificial acaba de pre-agendar una cita para tu inmueble:\n"
                    body += f"- Inmueble: {appt_payload.get('inmueble_titulo')} (ID: {appt_payload.get('inmueble_id')})\n"
                    body += f"- Fecha: {appt_payload.get('fecha_cita')}\n"
                    body += f"- Hora: {appt_payload.get('hora_cita')}\n\n"
                    body += f"Datos del Cliente:\n"
                    body += f"- Nombre: {appt_payload.get('cliente_nombre')}\n"
                    body += f"- Email: {appt_payload.get('cliente_email')}\n"
                    body += f"- Celular: {appt_payload.get('cliente_celular')}\n\n"
                    body += f"Recuerda que esta cita está en estado PENDIENTE. Por favor ingresa a admin.buscofacil.com para Aceptar, Modificar o Cancelar la pre-agenda.\n"
                    
                    msg.set_content(body)
                    
                    try:
                        if smtp_obj.smtp_port == 465:
                            with smtplib.SMTP_SSL(smtp_obj.smtp_host, smtp_obj.smtp_port, timeout=10) as server:
                                server.login(smtp_obj.smtp_user, smtp_obj.smtp_pass)
                                server.send_message(msg)
                        else:
                            with smtplib.SMTP(smtp_obj.smtp_host, smtp_obj.smtp_port, timeout=10) as server:
                                server.starttls()
                                server.login(smtp_obj.smtp_user, smtp_obj.smtp_pass)
                                server.send_message(msg)
                        print(f"Pre-Agenda Notification Email Sent successfully to {vendedor_email}")
                    except Exception as e:
                        print(f"Failed to send email to {vendedor_email}: {e}")
            else:
                print("Skipped Vendor Email Notifications: SMTP Settings not configured for this project.")
        except Exception as e:
            print(f"Failed to dispatch vendor notifications (Exception): {e}")

        return {
            "status": "success", 
            "result_text": "Citas pre-agendadas exitosamente en el sistema CRM central. Confírmale al usuario que hemos registrado su nombre y datos, informándole que sus citas están validadas, y mantén el ciclo abierto por si quiere algo más.",
            "appointments": appointments
        }
        
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
