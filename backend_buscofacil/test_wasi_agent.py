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
for k, v in data.items():
    if k != "total" and k != "status" and isinstance(v, dict):
        print("====== FULL RAW ASESOR INFO ======")
        print(json.dumps({
            "id_user": v.get("id_user"),
            "user_data": v.get("user_data", {}),
            "owner": v.get("owner")
        }, indent=2, ensure_ascii=False))
        print("====== OTHER PROPERTY CONTACT INFO ======")
        contact_fields = {}
        for prop_key, prop_val in v.items():
            if any(term in prop_key.lower() for term in ["email", "phone", "cell", "contact", "agent", "asesor"]):
                contact_fields[prop_key] = prop_val
        print(json.dumps(contact_fields, indent=2, ensure_ascii=False))
        break
