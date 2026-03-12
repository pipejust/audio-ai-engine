import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    WASI_TOKEN: str = os.getenv("WASI_TOKEN", "")
    WASI_ID_COMPANY: str = os.getenv("WASI_ID_COMPANY", "")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_STORAGE_BUCKET: str = os.getenv("SUPABASE_STORAGE_BUCKET", "documents")

settings = Settings()
