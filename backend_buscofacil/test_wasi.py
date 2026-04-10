import asyncio
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.services.wasi_api import WasiAPI
import requests

wasi_client = WasiAPI()

for pid in ["9224304", "9505387"]:
    payload = wasi_client._get_payload({"id_property": pid})
    res = requests.post(f"{wasi_client.base_url}/property/search", data=payload, headers=wasi_client._get_headers())
    data = res.json()
    print(f"WASI response for {pid}:")
    active = False
    for v in data.values():
        if isinstance(v, dict) and str(v.get("id_property")) == str(pid):
            print(f"  FOUND! status_on_page_label: {v.get('status_on_page_label', 'Unknown')}")
            active = True
    if not active:
        print("  NOT FOUND in /property/search")
