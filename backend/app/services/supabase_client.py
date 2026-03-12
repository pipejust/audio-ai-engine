import os
from supabase import create_client, Client
from app.core.config import settings

def get_supabase_client() -> Client:
    """
    Returns a configured Supabase client using the URL and Key from the settings.
    """
    url: str = settings.SUPABASE_URL
    key: str = settings.SUPABASE_KEY
    if not url or not key:
        raise ValueError("Supabase URL and Key must be provided in the environment variables.")
    return create_client(url, key)

supabase_client = get_supabase_client()
