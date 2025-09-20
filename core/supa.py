from supabase import create_client, Client
from .config import SUPABASE_URL, SUPABASE_ANON_KEY, ensure_env

_client: Client | None = None

def get_client() -> Client:
    global _client
    if _client is None:
        ensure_env()
        _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _client
