import sys, os, requests
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(override=True)
from app.services.wasi_api import WasiAPI
wasi = WasiAPI()

payload = wasi._get_payload({"id_user": 19962})
res = requests.post(f"{wasi.base_url}/user/search", data=payload, headers=wasi._get_headers())
print("USER SEARCH:", res.json())

res2 = requests.post(f"{wasi.base_url}/user/get/19962", data=wasi._get_payload(), headers=wasi._get_headers())
print("USER GET:", res2.json())
