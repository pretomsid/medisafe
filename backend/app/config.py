"""সব সেটিং এক জায়গায়। Environment variable দিয়ে বদলানো যায়, কোড বদলাতে হয় না।"""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/


def _secret_key():
    """SECRET_KEY env-এ না থাকলে instance/secret_key ফাইলে একবার random key বানিয়ে রাখা হয়।
    কোডে লেখা একটা জানা key দিয়ে যে কেউ session cookie বানিয়ে অন্যের account-এ ঢুকতে পারত।"""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(BASE_DIR, "instance", "secret_key")
    try:
        if os.path.exists(path):
            with open(path) as f:
                return f.read().strip()
    except Exception:
        pass

    import secrets
    key = secrets.token_hex(32)
    for p in [path, os.path.join("/tmp", "secret_key")]:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(key)
            return key
        except Exception:
            continue
    return key


class Config:
    SECRET_KEY = _secret_key()
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///medisafe.db")
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {
            "timeout": 30.0,
            "check_same_thread": False
        }
    }
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE") == "1"  # HTTPS-এ deploy করলে 1
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8                                # ৮ ঘণ্টা পর আবার login
    # model2 ফোল্ডার: MedEx dataset CSV + Model 2 দাম-তুলনা model (train.py / predict.py / models/*.json)
    MODEL2_DIR = os.environ.get("MODEL2_DIR", os.path.join(os.path.dirname(BASE_DIR), "model2"))
    # model1 ফোল্ডার: Model 1 drug interaction risk (DDInter data, drug_names.py, train_interaction.py)
    MODEL1_DIR = os.environ.get("MODEL1_DIR", os.path.join(os.path.dirname(BASE_DIR), "model1"))
    # model1/train_interaction.py এই JSON লেখে।
    # None হলে MODEL1_DIR/models/interaction_risk_model.json ধরা হয়
    INTERACTION_MODEL_PATH = os.environ.get("INTERACTION_MODEL_PATH")
    # Frontend ফোল্ডার; পরে frontend আলাদা হলে এটা None করে দিলেই হবে
    FRONTEND_DIR = os.environ.get("FRONTEND_DIR", os.path.dirname(BASE_DIR))


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
