"""model2/ ফোল্ডারের দাম-তুলনা model (Model 2)-কে backend-এর সাথে যুক্ত করে।

Model-এর কোড (train.py, predict.py) বদলানো হয়নি। এখানে শুধু:
  - model2/predict.py থেকে তাদের নিজের function import করা হয়,
  - তৈরি করা index (models/alternative_recommendation.json) server চালুর পর একবারই load হয়,
  - ফলাফল database-এর Product-এর সাথে মেলানো হয় (brand id দিয়ে)।
Model আবার train করলে (python train.py) শুধু server restart দিলেই নতুন index চলে আসবে।
"""
import os

from flask import current_app

from . import load_module

_cache = {}


def _module(name):
    """model2/ ফোল্ডার থেকে train বা predict module import করে।"""
    return load_module("MODEL2_DIR", name)


def extract_price(text):
    """Model যেভাবে দাম পড়ে, catalog-এও ঠিক সেভাবে পড়া হয় (দুই জায়গায় একই নিয়ম)।"""
    return _module("train").extract_unit_price(text)


def _index():
    try:
        from flask import current_app
        m2_dir = current_app.config["MODEL2_DIR"]
    except Exception:
        from ..config import Config
        m2_dir = Config.MODEL2_DIR
    path = os.path.join(m2_dir, "models", "alternative_recommendation.json")
    if path not in _cache:
        _cache.clear()
        _cache[path] = _module("predict").load_model(path) if os.path.exists(path) else None
    return _cache[path]


def info():
    m = _index()
    if not m:
        return {"loaded": False}
    return {"loaded": True, "model_type": m.get("model_type"), "created_at_utc": m.get("created_at_utc"),
            "matching_fields": m.get("matching_fields"), "ranking": m.get("ranking"),
            "statistics": m.get("statistics")}


def comparisons(generic, strength, form, med_type, limit=50):
    """Model-কে জিজ্ঞেস করে: একই generic + strength + dosage form + type-এর পণ্যগুলো, কম দাম আগে।
    Index load না হলে None ফেরত দেয়।"""
    m = _index()
    if not m:
        return None
    return _module("predict").find_comparisons_from_model(m, generic, strength, form, med_type, limit)



def normalized_price(package):
    """প্রতি একক দাম: model2/price_units.py (60 ml বনাম 100 ml বোতল সরাসরি তুলনা করা যায় না)।"""
    return _module("price_units").normalized_price(package)
