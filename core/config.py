from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")  # carga si existe

APP_NAME = os.getenv("APP_NAME", "pest_auto_report")
APP_ENV  = os.getenv("APP_ENV", "dev")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

def ensure_env():
    missing = []
    if not SUPABASE_URL: missing.append("SUPABASE_URL")
    if not SUPABASE_ANON_KEY: missing.append("SUPABASE_ANON_KEY")
    if missing:
        raise RuntimeError(f"Faltan variables en .env: {', '.join(missing)}")
