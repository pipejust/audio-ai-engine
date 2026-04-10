import os
import sys

# Add backend directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from dotenv import load_dotenv
load_dotenv(override=True)

from app.db.session import engine, SessionLocal
from app.db.models import Base, TrainingSource

def main():
    print(f"Connecting to database: {engine.url}")
    print("Creating tables if they don't exist...")
    
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully.")
        
        db = SessionLocal()
        sources = db.query(TrainingSource).all()
        print(f"📊 Query successful. Total training sources in Supabase PostgreSQL: {len(sources)}")
        db.close()
        print("🚀 Connection test PASSED!")
    except Exception as e:
        print(f"❌ Connection test FAILED: {str(e)}")

if __name__ == "__main__":
    main()
