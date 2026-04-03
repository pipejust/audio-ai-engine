import asyncio
import requests
from app.services.wasi_api import WasiAPI

async def test():
    print("Iniciando test")
    context_listing_ids = ["", "undefined", "1234"]
    hydrated_mapping_text = ""
    if context_listing_ids:
        wasi = WasiAPI()
        
        def fetch_prop(pid):
            try:
                payload = wasi._get_payload({"id_property": pid})
                res = requests.post(f"{wasi.base_url}/property/search", data=payload, headers=wasi._get_headers(), timeout=2.5)
                data = res.json()
                for v in data.values():
                    if isinstance(v, dict) and str(v.get("id_property")) == str(pid):
                        return f"ID \"{pid}\" - Encontrado!"
            except Exception as e:
                print(f"Error inside fetch_prop: {e}")
                pass
            return f"ID \"{pid}\""
            
        print("Spawning threads...")
        tasks = [asyncio.to_thread(fetch_prop, pid) for pid in context_listing_ids]
        results = await asyncio.gather(*tasks)
        print(f"Threads fnished: {results}")

asyncio.run(test())
