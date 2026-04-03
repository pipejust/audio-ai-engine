import os
import sys

# Change to the backend_buscofacil root programmatically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)
from app.services.wasi_api import WasiAPI
import requests

wasi_client = WasiAPI()

def fetch_live_wasi_property(pid):
    try:
        payload = wasi_client._get_payload({"id_property": pid})
        print("Payload:", payload)
        res = requests.post(f"{wasi_client.base_url}/property/search", data=payload, headers=wasi_client._get_headers(), timeout=4.0)
        data = res.json()
        print(f"Response keys for {pid}:", data.keys())
        for v in data.values():
            if isinstance(v, dict) and str(v.get("id_property")) == str(pid):
                return pid, {"status_label": v.get("status_on_page_label", "Activo")}
    except Exception as e:
        print(f"Error fetching live WASI property {pid}: {e}")
        pass
    return pid, None

print(fetch_live_wasi_property("9863643"))
