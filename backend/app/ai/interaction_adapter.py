"""Model 1 (drug interaction risk, semi-supervised) কে backend-এর সাথে যুক্ত করে।

Model train হয় model1/train_interaction.py দিয়ে (scikit-learn লাগে শুধু ওখানে)। Train শেষে
DDInter-এর যেসব pair-এর severity "Unknown", সেগুলোর prediction একটা JSON-এ লেখা থাকে:
    model1/models/interaction_risk_model.json
Backend শুধু ওই JSON পড়ে, তাই এখানে scikit-learn install করতে হয় না।

নামের মিল (Paracetamol → acetaminophen, Amlodipine Besilate → amlodipine) model1/drug_names.py
দিয়ে হয়, train-এর সময়ও একই নিয়ম, তাই দুই জায়গায় নাম একইভাবে মেলে।
JSON না থাকলে predict() সবসময় None দেয় আর available() False, তখন UI-তে "not connected" দেখায়।
"""
import json
import os

from flask import current_app

from . import load_module

_cache = {}


def _path():
    try:
        from flask import current_app
        return current_app.config.get("INTERACTION_MODEL_PATH") or os.path.join(
            current_app.config["MODEL1_DIR"], "models", "interaction_risk_model.json")
    except Exception:
        from ..config import Config
        return Config.INTERACTION_MODEL_PATH or os.path.join(
            Config.MODEL1_DIR, "models", "interaction_risk_model.json")


def available():
    return os.path.exists(_path())


def _model():
    path = _path()
    if path not in _cache:
        _cache.clear()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                m = json.load(f)
            m["_known"] = set(m.get("drugs", []))
            _cache[path] = m
        else:
            _cache[path] = None
    return _cache[path]


def predict(generic_a, generic_b):
    """দুটো active ingredient-এর নাম → {"category", "confidence"} অথবা None (prediction নেই)।"""
    m = _model()
    if not m:
        return None
    names = load_module("MODEL1_DIR", "drug_names")
    a, b = names.resolve(generic_a, m["_known"]), names.resolve(generic_b, m["_known"])
    if not a or not b or a == b:
        return None
    return m["predictions"].get(names.pair_key(a, b))


def info():
    """Report/UI-র জন্য model-এর বিবরণ আর test metrics (prediction তালিকা বাদে)।"""
    m = _model()
    if not m:
        return {"loaded": False}
    return {"loaded": True, "model_type": m.get("model_type"), "created_at_utc": m.get("created_at_utc"),
            "dataset": m.get("dataset"), "classes": m.get("classes"), "params": m.get("params"),
            "metrics": m.get("metrics"), "clinical_note": m.get("clinical_note"),
            "unknown_pairs_predicted": len(m.get("predictions", {}))}
