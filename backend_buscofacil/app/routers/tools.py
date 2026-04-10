from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(tags=["Tools"])

class ToolRequest(BaseModel):
    project_id: str
    args: Dict[str, Any]
    currency: str = "COP"

@router.post("/{function_name}")
def execute_tool(function_name: str, request_data: ToolRequest, request: Request, background_tasks: BackgroundTasks = None):
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
    
    if function_name == "check_location_context":
        location_name = args.get("location_name", "")
        import os
        import sys
        
        # Ensure the root path is in sys.path to safely import db_colombia
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        if root_dir not in sys.path:
            sys.path.append(root_dir)
            
        try:
            from db_colombia import setup_database, resolver_ubicacion
            conn = setup_database()
            resolver_response = resolver_ubicacion(location_name, conn)
            conn.close()
            return {"status": "success", "result_text": f"Dato geográfico: {resolver_response}. IMPORTANTE: Infórmaselo inmediatamente al cliente y hazle una pregunta corta de confirmación sobre la ciudad encontrada para estar seguros antes de buscar."}
        except Exception as e:
            return {"status": "error", "result_text": f"Falló al buscar contexto de lugar: {e}"}
            
    if function_name == "consult_knowledge_base":
        query = args.get("query", "")
        retriever = agent_manager.vector_store.get_retriever(k=25, project_id=project_id)
        docs = retriever.invoke(query)
        context_text = "\\n".join([d.page_content for d in docs]) if docs else "No information matches the query."
        return {"status": "success", "result_text": context_text}
        
    elif function_name == "search_properties":
        city = args.get("city") or ""
        neighborhood = args.get("neighborhood") or ""
        loc_parts = [p.strip() for p in [city, neighborhood] if p and p.strip()]
        location = ", ".join(loc_parts) if loc_parts else "any"
        tipo = args.get("property_type") or "any"
        tipo = str(tipo)
        limit = args.get("limit") or 15
        
        print(f"🔥 BÚSQUEDA RAG: location='{location}' | city='{city}' | barrio='{neighborhood}' | tipo='{tipo}'")
        
        import re
        max_price_str = str(args.get("max_price") or "100000000000")
        max_price_numerics = re.findall(r"\d+", max_price_str.replace(".", "").replace(",", ""))
        max_price_val = int("".join(max_price_numerics)) if max_price_numerics else 100000000000
        
        min_price_str = str(args.get("min_price") or "0")
        min_price_numerics = re.findall(r"\d+", min_price_str.replace(".", "").replace(",", ""))
        min_price_val = int("".join(min_price_numerics)) if min_price_numerics else 0
        
        # --- NEW LOCATION RESOLUTION ---
        resolved_context = ""
        import os, sys
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        if root_dir not in sys.path:
            sys.path.append(root_dir)
        try:
            from db_colombia import setup_database, resolver_ubicacion
            conn = setup_database()
            if neighborhood:
                resolved_context = resolver_ubicacion(neighborhood, conn)
            elif city:
                resolved_context = resolver_ubicacion(city, conn)
            conn.close()
        except:
            pass
            
        print(f"🚀 Contexto de Ubicación Resuelto para Búsqueda (Velocidad Extendida): {resolved_context}")
        
        search_query = f"propiedades disponibles inmueble"
        if tipo.lower() != "any": search_query += f" tipo {tipo}"
        if location.lower() != "any": search_query += f" en {location}"
        if resolved_context and "No se encontró" not in resolved_context:
            search_query += f" que pertenezcan a la zona geográfica exacta: {resolved_context}"
        
        safe_limit = min(int(limit), 20)
        
        # Aumentar K a 400 para asegurar que traemos el corpus completo y filtramos robustamente en Python.
        retriever = agent_manager.vector_store.get_retriever(k=400, project_id=project_id)
        raw_docs = retriever.invoke(search_query)
        
        filtered_docs = []
        fallback_docs = []
        seen_ids = set()
        
        def normalize_str(s):
            import unicodedata
            return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn').lower()
            
        loc_norm = normalize_str(location) if location.lower() != "any" else ""
        
        tipo_sin_plural = tipo.lower().replace("casas", "casa").replace("apartamentos", "apartamento").replace("lotes", "lote").replace("fincas", "finca").replace("oficinas", "oficina").replace("locales", "local")
        type_norm = normalize_str(tipo_sin_plural) if tipo_sin_plural != "any" else ""
        
        if raw_docs:
            for d in raw_docs:
                p_id = d.metadata.get("property_id")
                if p_id and p_id in seen_ids:
                    continue
                if p_id: seen_ids.add(p_id)
                
                page_norm = normalize_str(d.page_content)
                meta_loc = normalize_str(d.metadata.get("location_search", ""))
                meta_type = normalize_str(d.metadata.get("property_type", ""))
                
                if loc_norm:
                    valid_location = True
                    loc_terms = [t.strip() for t in loc_norm.replace(",", " ").split() if t.strip()]
                    for term in loc_terms:
                        if term not in meta_loc and term not in page_norm:
                            valid_location = False
                            break
                    if not valid_location:
                        continue
                type_matched = True
                if type_norm:
                    if meta_type:
                        if type_norm not in meta_type:
                            type_matched = False
                    else:
                        if type_norm not in page_norm:
                            type_matched = False
                
                if type_matched:
                    filtered_docs.append(d)
                else:
                    fallback_docs.append(d)
                    
                if len(filtered_docs) >= 100:
                    break
                    
        is_fallback = False
        if not filtered_docs and fallback_docs:
            filtered_docs = fallback_docs[:100]
            is_fallback = True
        
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
            
            # Filtro Matemático de Presupuesto (Tolerancia extendida del 15% para suavizar bordes)
            if max_price_val < 100000000000 and precio_int > (max_price_val * 1.15):
                continue
            if min_price_val > 0 and precio_int < (min_price_val * 0.85):
                continue
            
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
                        sale_price = int(float(v.get("sale_price", 0) or 0))
                        rent_price = int(float(v.get("rent_price", 0) or 0))
                        final_price = rent_price if rent_price > 0 else sale_price
                        
                        user_data = v.get("user_data", {})
                        
                        return pid, {
                            "images": images, # Send ALL images without slicing
                            "live_price": final_price,
                            "status_label": v.get("status_on_page_label", "Activo"),
                            "agent_id_user": v.get("id_user"),
                            "agent_first": user_data.get("first_name", ""),
                            "agent_last": user_data.get("last_name", "")
                        }
            except Exception as e:
                print(f"Error fetching live WASI property {pid}: {e}")
                pass
            return pid, None
            
        if raw_properties:
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
            req_currency = getattr(request_data, 'currency', 'COP')
            rate = {'COP': 1, 'USD': 4000, 'EUR': 4300}.get(req_currency, 1)

            for rp in top_properties:
                live_info = live_data_map.get(str(rp["id"]))
                if live_info is None:
                    # Inmueble bajado de WASI o inactivo, lo ignoramos para no mandar basura a la IA
                    continue
                    
                # Update with verified fresh data
                rp["images"] = live_info["images"]
                if live_info["live_price"] > 0:
                    rp["price"] = int(live_info["live_price"] / rate)
                else:
                    rp["price"] = int(rp["price"] / rate)
                    
                rp["agent_id_user"] = live_info["agent_id_user"]
                rp["agent_first"] = live_info["agent_first"]
                rp["agent_last"] = live_info["agent_last"]
                rp["ui_currency"] = req_currency
                
                valid_live_properties.append(rp)
                
            raw_properties = valid_live_properties
            llm_docs = [d for d in filtered_docs if str(d.metadata.get("property_id")) in [rp["id"] for rp in raw_properties]]
            
            if len(llm_docs) == 0:
                result_text = f"Revisé la base de datos extensamente pero los inmuebles disponibles superan tu presupuesto estricto o ya fueron vendidos según WASI. Infórmale al cliente que no pudimos encontrar nada con ese presupuesto en {location}."
            else:
                result_text = f"RESULTADO DE BASE DE DATOS: Encontré opciones. Aquí tienes las top {len(llm_docs)}:\\n"
                for i, d in enumerate(llm_docs):
                    prop_id = d.metadata.get("property_id", "DESCONOCIDO")
                    snippet = d.page_content[:350] + "..." if len(d.page_content) > 350 else d.page_content
                    # Agregamos los datos del asesor y precio convertido recuperados dinámicamente si están disponibles
                    agent_str = ""
                    current_price = 0
                    for rp in raw_properties:
                        if rp["id"] == prop_id:
                            if rp.get("agent_first"):
                                agent_str = f" [Asesor: {rp.get('agent_first')} {rp.get('agent_last')}]"
                            current_price = rp.get("price", 0)
                            break
                            
                    currency_str = f" [PRECIO MÁXIMO EN {req_currency}: {current_price}]" if req_currency != 'COP' else ""
                    result_text += f"\\n[{i+1}] (ID_INMUEBLE: {prop_id}){agent_str}{currency_str} {snippet}\\n"
                
                result_text += "\\nREGLA: Describe estas opciones de forma atractiva. Diles el precio y barrio. MEMORIZA EL ID_INMUEBLE de cada opción por si el usuario pide seleccionar, agendar o ver detalles."
                if is_fallback:
                    result_text += f"\\n\\n**¡CRÍTICO! ALERTA DE FALLBACK:** Como asistente, NO CUMPLES con el tipo exacto de '{tipo}' que el usuario pidió (Te lo informamos porque estas propiedades mostradas son aproxmaciones de tipo distinto). ESTÁS OBLIGADO A HACER ESTO A CONTINUACIÓN: Diles de frente 'No contamos  actualmente con {tipo} exacto en {location}, pero no te preocupes, tengo estas excelentes opciones similares...'. Luego descríbelas empáticamente."
        else:
            result_text = f"Revisé la base de datos extensamente pero NO hay ningún inmueble tipo {tipo} o similares disponibles en el sector de {location}. Infórmale esto de inmediato."
            
        return {"status": "success", "result_text": result_text, "raw_properties": raw_properties}
    elif function_name == "open_property_details":
        listing_id = args.get("listing_id")
        return {
            "status": "success",
            "result_text": "Dile amablemente al usuario: '¡Claro! Aquí tienes los detalles e imágenes de la propiedad en pantalla.'",
            "action": "view_details",
            "listing_id": listing_id
        }
        
    elif function_name == "close_property_details":
        return {
            "status": "success",
            "result_text": "Dile amablemente al usuario: 'Con gusto. He cerrado los detalles de la propiedad, ahora estás de vuelta en la lista principal.'",
            "action": "close_details"
        }
        
    elif function_name == "select_properties_for_appointment":
        listing_ids = args.get("listing_ids", [])
        return {
            "status": "success",
            "result_text": "Dile amablemente al usuario: 'He marcado esas propiedades en pantalla para ti. ¿Te gustaría agendar una visita para alguna fecha y hora en específico?'",
            "action": "select_properties",
            "listing_ids": listing_ids
        }
        
    elif function_name == "schedule_visits":
        client_name = args.get("client_name", "")
        client_email = args.get("client_email", "")
        client_phone = args.get("client_phone", "+57 300 000 0000")
        appointments = args.get("appointments", [])
        
        if not client_email or client_email.strip() == "":
            return {
                "status": "success",
                "result_text": "Dile enérgicamente al usuario: '¡Claro que sí! Para agendar tus visitas, por favor inicia sesión o regístrate en la ventana que acaba de aparecer en tu pantalla.'",
                "action": "open_login"
            }
        
        from app.db.session import SessionLocal
        from app.db.models import Lead, Appointment
        from app.services.email_service import send_appointment_emails
        
        db = SessionLocal()
        try:
            from app.services.wasi_api import WasiAPI
            import requests
            wasi = WasiAPI()

            lead = db.query(Lead).filter(Lead.email == client_email, Lead.project_id == project_id).first()
            if not lead:
                lead = Lead(project_id=project_id, name=client_name, email=client_email, phone=client_phone)
                db.add(lead)
                db.commit()
                db.refresh(lead)
            else:
                lead.name = client_name
                lead.phone = client_phone
                db.commit()
            
            for appt in appointments:
                import ast
                appt_id = ""
                if isinstance(appt, dict):
                    appt_id = str(appt.get('listing_id', appt.get('id', '')))
                elif isinstance(appt, str) and '{' in appt:
                    try:
                        appt_val = ast.literal_eval(appt)
                        appt_id = str(appt_val.get('listing_id', appt_val.get('id', '')))
                    except:
                        appt_id = appt
                else:
                    appt_id = str(appt)
                    
                # 1. Fetch property from WASI to get id_user
                agent_id_user = None
                agent_name = None
                agent_email = None
                agent_phone = None
                
                try:
                    payload = wasi._get_payload({"id_property": appt_id})
                    r = requests.post(f"{wasi.base_url}/property/search", data=payload, headers=wasi._get_headers(), timeout=4.0)
                    for _, v in r.json().items():
                        if isinstance(v, dict) and str(v.get("id_property")) == str(appt_id):
                            agent_id_user = str(v.get("id_user", ""))
                            user_data = v.get("user_data", {})
                            agent_name = f"{user_data.get('first_name','')} {user_data.get('last_name','')}".strip()
                            break
                            
                    # 2. If we found an agent, fetch their details explicitly
                    if agent_id_user:
                        info = wasi.get_user_info(agent_id_user)
                        if info:
                            agent_email = info.get("email")
                            agent_phone = info.get("phone")
                except Exception as e:
                    print(f"Sub-error fetching agent info for appointment {appt_id}: {e}")

                new_app = Appointment(
                    project_id=project_id, 
                    lead_id=lead.id, 
                    property_id=str(appt), # Grabamos raw para compatibilidad original
                    agent_id_user=agent_id_user,
                    agent_name=agent_name,
                    agent_email=agent_email,
                    agent_phone=agent_phone
                )
                db.add(new_app)
            db.commit()
            
            if background_tasks:
                background_tasks.add_task(send_appointment_emails, project_id, client_name, client_email, client_phone, appointments)
            else:
                import threading
                threading.Thread(target=send_appointment_emails, args=(project_id, client_name, client_email, client_phone, appointments)).start()
        except Exception as e:
            print("Error saving appointments:", e)
        finally:
            db.close()

        return {
            "status": "success", 
            "result_text": "Citas procesadas y pre-agendadas exitosamente en el borrador virtual. Confírmale al usuario que hemos registrado sus datos para las citas, y mantén el ciclo conversacional abierto.",
            "appointments": appointments
        }
        

    else:
        raise HTTPException(status_code=404, detail="Tool not found")
