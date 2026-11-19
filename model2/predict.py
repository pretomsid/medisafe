"""Show exact-match medicine price comparisons from the built index."""

import argparse
import json
import os

from train import group_key, normalize


DEFAULT_MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models",
    "alternative_recommendation.json",
)


def load_model(model_path):
    with open(model_path, encoding="utf-8") as source:
        return json.load(source)


def find_comparisons_from_model(model, generic, strength, dosage_form, med_type, limit):
    key = group_key(
        [
            normalize(generic),
            normalize(strength),
            normalize(dosage_form),
            normalize(med_type),
        ]
    )
    return model["groups"].get(key, [])[:limit]


def find_comparisons(model_path, generic, strength, dosage_form, med_type, limit):
    model = load_model(model_path)
    return find_comparisons_from_model(
        model, generic, strength, dosage_form, med_type, limit
    )


def main():
    parser = argparse.ArgumentParser(
        description="Compare listed prices for exact-match medicine products."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Built model/index path")
    parser.add_argument("--generic", required=True, help="Exact generic/ingredient")
    parser.add_argument("--strength", required=True, help="Exact medicine strength")
    parser.add_argument("--dosage-form", required=True, help="Exact dosage form")
    parser.add_argument("--type", default="allopathic", dest="med_type")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if not os.path.exists(args.model):
        parser.error(
            f"Index not found at {args.model!r}; run `python train.py` first."
        )

    products = find_comparisons(
        args.model,
        args.generic,
        args.strength,
        args.dosage_form,
        args.med_type,
        args.limit,
    )
    if not products:
        print(
            "No priced comparison group found for that exact generic, strength, "
            "dosage form, and type."
        )
        return

    print("Exact-match product price comparisons (lowest listed price first):")
    for rank, product in enumerate(products, start=1):
        print(
            f"{rank}. {product['brand_name']} — BDT "
            f"{product['listed_price_bdt']:.2f} "
            f"({product['manufacturer']}; "
            f"{product['package_container'] or 'package details unavailable'})"
        )
    print(
        "Comparison only: package sizes/price bases may differ. This is not a "
        "medical recommendation or advice to switch medicines; consult a "
        "doctor or pharmacist."
    )


if __name__ == "__main__":
    main()
