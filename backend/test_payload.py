from fastapi.testclient import TestClient
from app.main import app
import json

client = TestClient(app)

response = client.post(
    "/chat",
    json={
        "query": "Quiero ver las fotos de la segunda casa",
        "project_id": "buscofacil",
        "client_name": "Test User",
        "client_email": "test@example.com",
        "context_listing_ids": ["uuid-111", "uuid-222", "uuid-333"]
    }
)

print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
