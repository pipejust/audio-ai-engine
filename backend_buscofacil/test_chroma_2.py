import os
import sys

# Change to the backend_buscofacil root programmatically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.services.vector_store import VectorStoreManager
from app.routers.tools import execute_tool, ToolRequest
import asyncio

def test_manual():
    print("Testing Vector Store")
    vs = VectorStoreManager()
    retriever = vs.get_retriever(k=10, project_id="buscofacil")
    docs = retriever.invoke("casa Pance")
    print(f"Docs from retriever (Chroma): {len(docs)}")
    if docs:
        for doc in docs:
            print("MATCHED DOC PID:", doc.metadata.get("property_id"))
    else:
        print("NO DOCS MATCHED!")

if __name__ == "__main__":
    test_manual()
