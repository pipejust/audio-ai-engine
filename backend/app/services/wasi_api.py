import os
import requests
import json
from bs4 import BeautifulSoup

from dotenv import load_dotenv

class WasiAPI:
    def __init__(self):
        dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        load_dotenv(dotenv_path, override=True)
        self.id_company = os.getenv("WASI_ID_COMPANY")
        self.wasi_token = os.getenv("WASI_TOKEN")
        self.base_url = "https://api.wasi.co/v1"
        self.property_url_template = os.getenv("WASI_PROPERTY_URL_TEMPLATE", "https://facilinmobiliaria.com/main-inmueble-info-[id].htm")

    def _get_headers(self):
        return {
            "Accept": "application/json"
        }

    def _get_payload(self, additional_params=None):
        payload = {
            "id_company": self.id_company,
            "wasi_token": self.wasi_token
        }
        if additional_params:
            payload.update(additional_params)
        return payload

    def search_properties(self, take=50, skip=0):
        url = f"{self.base_url}/property/search"
        payload = self._get_payload({
            "take": take,
            "skip": skip
        })
        
        try:
            # Wasi APi usually takes application/x-www-form-urlencoded
            response = requests.post(url, data=payload, headers=self._get_headers())
            
            if response.status_code != 200:
                print(f"❌ Error en Wasi API: Status {response.status_code} - {response.text}")
                return []
                
            data = response.json()
            if data.get("status") == "error":
                print(f"❌ Error devuelto por Wasi API: {data.get('message')}")
                return []
                
            properties = []
            # Wasi returns an object where keys are property IDs or numeric indices, and values are property sub-objects
            for key, val in data.items():
                if isinstance(val, dict) and "id_property" in val:
                    properties.append(val)
                    
            return properties
        except Exception as e:
            print(f"❌ Excepción consultando Wasi API: {e}")
            return []

    def clean_html(self, raw_html):
        if not raw_html:
            return ""
        soup = BeautifulSoup(raw_html, "html.parser")
        return soup.get_text(separator=" ", strip=True)

    def format_property_for_rag(self, prop: dict) -> str:
        """
        Toma el payload JSON crudo de Wasi y lo convierte en un texto semántico
        muy bien estructurado para que el LLM lo pueda leer correctamente.
        """
        prop_id = prop.get("id_property", "Desconocido")
        title = prop.get("title", "Propiedad sin título")
        
        # Precio
        rent_price = prop.get("rent_price", "")
        sale_price = prop.get("sale_price", "")
        price_str = ""
        if rent_price and rent_price != "0":
            price_str += f"Alquiler: {rent_price} "
        if sale_price and sale_price != "0":
            price_str += f"Venta: {sale_price} "
            
        # Ubicación
        country = prop.get("country_label", "")
        region = prop.get("region_label", "")
        city = prop.get("city_label", "")
        zone = prop.get("zone_label", "")
        address = prop.get("address", "")
        location = f"{address}, {zone}, {city}, {region}, {country}".strip(", ")
        
        # Detalles
        bedrooms = prop.get("bedrooms", "0")
        bathrooms = prop.get("bathrooms", "0")
        garages = prop.get("garages", "0")
        area = prop.get("area", "0")
        stratum = prop.get("stratum", "N/A")
        built_time = prop.get("built_time", "N/A")
        
        # Características
        features_dict = prop.get("features", {})
        features_list = []
        if isinstance(features_dict, dict):
            for feature_group in features_dict.values():
                if isinstance(feature_group, dict):
                    for feature in feature_group.values():
                        if isinstance(feature, dict) and "nombre" in feature:
                            features_list.append(feature["nombre"])
        
        features_str = ", ".join(features_list) if features_list else "No listadas"
        
        # Descripción
        observations = self.clean_html(prop.get("observations", ""))
        
        # URL
        url = self.property_url_template.replace("[id]", str(prop_id))
        
        # Estructura del Documento
        formatted_text = f"""
---
PROPIEDAD ID: {prop_id}
TÍTULO: {title}
TIPO DE NEGOCIO: {price_str}
UBICACIÓN: {location}
CARACTERÍSTICAS PRINCIPALES:
- Habitaciones: {bedrooms}
- Baños: {bathrooms}
- Garajes: {garages}
- Área: {area} m2
- Estrato: {stratum}
- Tiempo de construcción: {built_time}
AMENIDADES: {features_str}
DESCRIPCIÓN: {observations}
ENLACE PARA EL CLIENTE: {url}
---
"""
        # Tipo de inmueble (Fallback usando el título si label no existe)
        title_lower = title.lower()
        if "casa" in title_lower:
            prop_type = "casa"
        elif "apartamento" in title_lower or "apto" in title_lower:
            prop_type = "apartamento"
        elif "lote" in title_lower:
            prop_type = "lote"
        elif "local" in title_lower:
            prop_type = "local"
        elif "finca" in title_lower:
            prop_type = "finca"
        else:
            prop_type = prop.get("property_type_label", "").lower()

        return {
            "text": formatted_text.strip(),
            "metadata": {
                "property_id": str(prop_id),
                "location_search": location.lower(),
                "property_type": prop_type
            }
        }

# Prueba local si se ejecuta directamente
if __name__ == "__main__":
    wasi = WasiAPI()
    props = wasi.search_properties(take=2)
    print(f"Se encontraron {len(props)} propiedades de muestra.")
    if props:
        print("\nEjemplo de normalización:")
        print(wasi.format_property_for_rag(props[0]))
