"""AI/model adapters। Model-এর নিজের কোড আলাদা ফোল্ডারে থাকে; এখানে শুধু backend-এর সাথে জোড়া লাগানোর adapter।
  model1/ (MODEL1_DIR): Model 1, drug interaction risk (semi-supervised) → interaction_adapter.py
  model2/ (MODEL2_DIR): Model 2, বিকল্প ওষুধ/দাম-তুলনা + MedEx CSV   → model2_adapter.py
"""
import importlib
import sys

from flask import current_app


def load_module(config_key, name):
    """config-এ দেওয়া model ফোল্ডার থেকে একটা Python module import করে (যেমন model2/predict.py)।"""
    folder = current_app.config[config_key]
    if folder not in sys.path:
        sys.path.insert(0, folder)
    return importlib.import_module(name)
