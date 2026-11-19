"""Flask endpoint for exact-match medicine price comparisons."""

import os

from flask import Flask, jsonify, request

from predict import DEFAULT_MODEL, find_comparisons_from_model, load_model


DISCLAIMER = (
    "Price comparison only. Package sizes and price bases may differ. "
    "This is not medical advice or a recommendation to switch medicines; "
    "consult a doctor or pharmacist."
)
MODEL_PATH = os.environ.get("MEDISAFE_MODEL_PATH", DEFAULT_MODEL)


def register_model_routes(app, model_path=MODEL_PATH):
    model = load_model(model_path)

    @app.post("/api/medicine-comparisons")
    def medicine_comparisons():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be a JSON object."}), 400

        required_fields = ("generic", "strength", "dosage_form")
        for field in required_fields:
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                return jsonify({"error": f"'{field}' must be a non-empty string."}), 400

        med_type = payload.get("type", "allopathic")
        if not isinstance(med_type, str) or not med_type.strip():
            return jsonify({"error": "'type' must be a non-empty string."}), 400

        limit = payload.get("limit", 10)
        if type(limit) is not int or not 1 <= limit <= 50:
            return jsonify({"error": "'limit' must be an integer from 1 to 50."}), 400

        results = find_comparisons_from_model(
            model,
            payload["generic"],
            payload["strength"],
            payload["dosage_form"],
            med_type,
            limit,
        )
        return jsonify(
            {
                "query": {
                    "generic": payload["generic"].strip(),
                    "strength": payload["strength"].strip(),
                    "dosage_form": payload["dosage_form"].strip(),
                    "type": med_type.strip(),
                },
                "count": len(results),
                "comparisons": results,
                "disclaimer": DISCLAIMER,
            }
        )

    return app


def create_app(model_path=MODEL_PATH):
    return register_model_routes(Flask(__name__), model_path)


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
