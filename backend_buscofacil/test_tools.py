import asyncio
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from dotenv import load_dotenv; load_dotenv()
from app.services.agent_manager import AgentManager
from app.routers.tools import execute_tool, ToolRequest
from fastapi import Request

class DummyRequest:
    def __init__(self, am):
        self.app = type("App", (), {"state": type("State", (), {"agent_manager": am})})()

async def test():
    am = AgentManager()
    
    # Simulate tools call
    req = ToolRequest(
        project_id="buscofacil",
        args={
            "city": "Cali",
            "neighborhood": "Ciudad Jardín",
            "property_type": "apartamento",
            "limit": 15
        }
    )
    res = execute_tool("search_properties", req, DummyRequest(am))
    print(res["result_text"])
    for p in res.get("raw_properties", []):
        print("  -->", p["id"], p["title"])
        
asyncio.run(test())
