from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")  # carga si existe

APP_NAME = os.getenv("APP_NAME", "pest_auto_report")
APP_ENV  = os.getenv("APP_ENV", "dev")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# QBench
QBENCH_BASE_URL      = os.getenv("QBENCH_BASE_URL", "").rstrip("/")
QBENCH_CLIENT_ID     = os.getenv("QBENCH_CLIENT_ID", "")
QBENCH_CLIENT_SECRET = os.getenv("QBENCH_CLIENT_SECRET", "")
QBENCH_JWT_LEEWAY_S  = int(os.getenv("QBENCH_JWT_LEEWAY_S", "20"))
QBENCH_JWT_TTL_S     = int(os.getenv("QBENCH_JWT_TTL_S", "3580"))


def ensure_env():
    missing = []
    if not SUPABASE_URL: missing.append("SUPABASE_URL")
    if not SUPABASE_ANON_KEY: missing.append("SUPABASE_ANON_KEY")
    if missing:
        raise RuntimeError(f"Faltan variables en .env: {', '.join(missing)}")
