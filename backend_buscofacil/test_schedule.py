import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from app.routers.tools import execute_tool, ToolRequest
from app.db.session import SessionLocal
from app.db.models import Appointment

def run_test():
    try:
        from app.routers.tools import execute_tool
        from collections import namedtuple
        Req = namedtuple("Req", ["project_id", "args"])
        data = Req(project_id="buscofacil", args={
            "client_name": "Test User",
            "client_email": "test@felipe.com",
            "client_phone": "3000000",
            "appointments": ["9863643"]
        })
        
        from fastapi import Request
        class MockApp:
            state = type('obj', (object,), {'agent_manager': None})
        class MockReq:
            app = MockApp()
            
        execute_tool("schedule_visits", data, MockReq())
    except Exception as e:
        print("Error scheduling:", e)
        
def view_db():
    db = SessionLocal()
    apps = db.query(Appointment).all()
    for app in apps:
        print(f"Propiedad: {app.property_id} | Asesor: {app.agent_name} ({app.agent_email}) | Lead ID: {app.lead_id}")
    db.close()

if __name__ == "__main__":
    run_test()
    view_db()
