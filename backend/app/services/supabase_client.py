import os
from supabase import create_client, Client
from app.core.config import settings

def get_supabase_client():
    """
    Returns a configured Supabase client using the URL and Key from the settings.
    """
    url: str = os.getenv("SUPABASE_URL")
    key: str = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("Mocking Supabase for local testing")
        return None
    return create_client(url, key)

supabase_client = get_supabase_client()
