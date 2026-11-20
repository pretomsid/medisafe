"""Vercel Serverless Function entrypoint for MediSafe."""
import json
import os
import shutil
import sys

# Add project root and backend to sys.path
API_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(API_DIR)
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

for p in [ROOT_DIR, BACKEND_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from app import create_app
from app.config import Config

# Temporary directory is writable on Vercel
TMP_DIR = "/tmp"
TMP_DB = os.path.join(TMP_DIR, "medisafe.db")
TMP_UPLOADS = os.path.join(TMP_DIR, "uploads")
try:
    os.makedirs(TMP_UPLOADS, exist_ok=True)
except Exception:
    pass

# Locate pre-seeded database
candidate_dbs = [
    os.path.join(API_DIR, "medisafe.db"),
    os.path.join(BACKEND_DIR, "instance", "medisafe.db"),
    os.path.join(ROOT_DIR, "backend", "instance", "medisafe.db"),
    os.path.join(ROOT_DIR, "instance", "medisafe.db"),
]

db_src = None
for c in candidate_dbs:
    if os.path.exists(c):
        db_src = c
        break

# Seed database to /tmp if not already present
if db_src and not os.path.exists(TMP_DB):
    try:
        shutil.copyfile(db_src, TMP_DB)
    except Exception as e:
        print(f"Failed to copy DB from {db_src} to {TMP_DB}: {e}")

class VercelConfig(Config):
    SECRET_KEY = os.environ.get("SECRET_KEY", "medisafe-production-session-secret-key-2026")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{TMP_DB}" if os.path.exists(TMP_DB) else (
        f"sqlite:///{db_src}" if db_src else "sqlite:////tmp/medisafe.db"
    )
    UPLOAD_FOLDER = TMP_UPLOADS
    FRONTEND_DIR = ROOT_DIR
    MODEL1_DIR = os.path.join(ROOT_DIR, "model1")
    MODEL2_DIR = os.path.join(ROOT_DIR, "model2")
    INTERACTION_MODEL_PATH = os.path.join(ROOT_DIR, "model1", "models", "interaction_risk_model.json")
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

# Top-level Flask instance required by Vercel static analyzer
app = create_app(VercelConfig)
