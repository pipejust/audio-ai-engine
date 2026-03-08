import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    WASI_TOKEN: str = os.getenv("WASI_TOKEN", "")
    WASI_ID_COMPANY: str = os.getenv("WASI_ID_COMPANY", "")
    DATABASE_URL: str = "sqlite:///../wasi_inventory.db"

settings = Settings()
