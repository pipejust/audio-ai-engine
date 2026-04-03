import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)
from app.services.wasi_api import WasiAPI
import requests

wasi_client = WasiAPI()
prop_id = "9863643"
payload = wasi_client._get_payload({"id_property": prop_id})

res = requests.post(f"{wasi_client.base_url}/property/search", data=payload, headers=wasi_client._get_headers(), timeout=4.0)
data = res.json()

# Identify the property dict
prop_data = {}
for k, v in data.items():
    if k != "total" and k != "status" and isinstance(v, dict):
        prop_data = v
        break

# Escribir el resultado formateado a un artifact markdown en la carpeta principal
output_file = "/Users/felipecortes/.gemini/antigravity/brain/8181b02a-4b64-4ddb-ae91-1b9256426b3b/artifacts/wasi_property_dump.md"

md_content = f"""# 📦 Datos Crudos del Inmueble (WASI)

A continuación te presento todo el diccionario de datos (JSON) completo que retorna WASI por cada propiedad al hacer una petición a su API.

> [!NOTE]
> ID de la Propiedad testeada: **{prop_id}**
> Puedes observar que la mayoría de datos exhaustivos como 'rooms', 'bathrooms', o descripciones vienen en variables nativas, y los datos del asesor (`user_data`) o zonas se encadenan como sub-objetos.

```json
{json.dumps(prop_data, indent=2, ensure_ascii=False)}
```
"""

os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, "w", encoding="utf-8") as f:
    f.write(md_content)
    
print("Dump realizado exitosamente en", output_file)
