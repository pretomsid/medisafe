"""Vercel Serverless Function entrypoint for MediSafe."""
import os
import sys
import shutil

# Add project root and backend to sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app
from app.config import Config

# Vercel serverless runtime has a read-only filesystem except /tmp
TMP_DIR = "/tmp"
DB_SRC = os.path.join(BACKEND_DIR, "instance", "medisafe.db")
DB_DEST = os.path.join(TMP_DIR, "medisafe.db")

# Seed database to /tmp if running in serverless environment
if os.path.exists(DB_SRC) and not os.path.exists(DB_DEST):
    try:
        shutil.copyfile(DB_SRC, DB_DEST)
    except Exception as e:
        print("Vercel DB setup note:", e)

class VercelConfig(Config):
    if os.path.exists(DB_DEST):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_DEST}"
    elif os.path.exists(DB_SRC):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_SRC}"
    UPLOAD_FOLDER = os.path.join(TMP_DIR, "uploads")
    FRONTEND_DIR = ROOT_DIR

os.makedirs(os.path.join(TMP_DIR, "uploads"), exist_ok=True)
app = create_app(VercelConfig)
