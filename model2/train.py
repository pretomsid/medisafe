"""Build a content-based medicine alternative index from medicine.csv."""

import argparse
import csv
import json
import os
from datetime import datetime, timezone


MATCH_FIELDS = ("generic", "strength", "dosage form", "type")
PRICE_MARKER = "\u09f3"


def normalize(value):
    return " ".join((value or "").casefold().split())


def extract_unit_price(value):
    """Return the first BDT amount in a package description, or None."""
    if not value:
        return None
    marker = value.find(PRICE_MARKER)
    if marker < 0:
        return None

    start = marker + len(PRICE_MARKER)
    while start < len(value) and value[start].isspace():
        start += 1
    end = start
    while end < len(value) and (value[end].isdigit() or value[end] in ".,"):
        end += 1
    amount = value[start:end].replace(",", "")
    if not amount or amount == ".":
        return None
    try:
        price = float(amount)
    except ValueError:
        return None
    return price if price > 0 else None


def group_key(values):
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def build_recommendation_model(medicine_csv, output_path):
    groups = {}
    row_count = 0
    rows_with_core_fields = 0
    rows_with_price = 0

    with open(medicine_csv, encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required_columns = {
            "brand id", "brand name", "generic", "strength", "dosage form",
            "manufacturer", "type", "package container",
        }
        missing_columns = required_columns.difference(reader.fieldnames or [])
        if missing_columns:
            raise ValueError(
                "medicine.csv is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        for row in reader:
            row_count += 1
            features = [normalize(row.get(field)) for field in MATCH_FIELDS]
            if not all(features):
                continue
            rows_with_core_fields += 1

            price = extract_unit_price(row.get("package container", ""))
            if price is None:
                continue
            rows_with_price += 1

            key = group_key(features)
            product = {
                "brand_id": row["brand id"],
                "brand_name": row["brand name"].strip(),
                "generic": row["generic"].strip(),
                "strength": row["strength"].strip(),
                "dosage_form": row["dosage form"].strip(),
                "manufacturer": row["manufacturer"].strip(),
                "type": row["type"].strip(),
                "listed_price_bdt": round(price, 2),
                "package_container": row["package container"].strip(),
                "package_size": row["Package Size"].strip(),
            }
            groups.setdefault(key, []).append(product)

    eligible_groups = {
        key: sorted(
            products,
            key=lambda product: (
                product["listed_price_bdt"],
                normalize(product["brand_name"]),
            ),
        )
        for key, products in groups.items()
        if len(products) >= 2
    }
    products_with_alternatives = sum(
        len(products) for products in eligible_groups.values()
    )
    model = {
        "model_type": "exact-match content-based medicine comparison",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_file": os.path.basename(medicine_csv),
        "matching_fields": list(MATCH_FIELDS),
        "ranking": (
            "ascending first listed BDT amount after exact normalized feature "
            "matching; inspect package details because price basis can vary"
        ),
        "clinical_note": (
            "Price-ranked candidates are comparisons only, not medical advice "
            "or a determination that a medicine is an appropriate substitute."
        ),
        "interaction_model_status": "separate model in ../model1",
        "interaction_model_reason": (
            "These MedEx files have no labeled drug pairs, so the interaction "
            "risk model (Model 1) is trained on DDInter 2.0 in "
            "../model1/train_interaction.py."
        ),
        "statistics": {
            "medicine_rows": row_count,
            "rows_with_matching_fields": rows_with_core_fields,
            "rows_with_valid_price": rows_with_price,
            "eligible_groups_with_alternatives": len(eligible_groups),
            "products_in_eligible_groups": products_with_alternatives,
            "risk_classifier_metrics": None,
        },
        "groups": eligible_groups,
    }

    output_directory = os.path.dirname(output_path)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as destination:
        json.dump(model, destination, ensure_ascii=False, separators=(",", ":"))
        destination.write("\n")

    return model


def main():
    parser = argparse.ArgumentParser(
        description="Build the eligible, price-ranked medicine comparison index."
    )
    parser.add_argument("--data", default="medicine.csv", help="Medicine CSV path")
    parser.add_argument(
        "--output",
        default=os.path.join("models", "alternative_recommendation.json"),
        help="Output model/index path",
    )
    args = parser.parse_args()

    model = build_recommendation_model(args.data, args.output)
    stats = model["statistics"]
    print("Alternative medicine comparison index created.")
    print(f"Medicine rows: {stats['medicine_rows']:,}")
    print(f"Rows with match fields: {stats['rows_with_matching_fields']:,}")
    print(f"Rows with valid prices: {stats['rows_with_valid_price']:,}")
    print(
        "Eligible exact-match groups with alternatives: "
        f"{stats['eligible_groups_with_alternatives']:,}"
    )
    print(f"Products in those groups: {stats['products_in_eligible_groups']:,}")
    print(f"Saved: {args.output}")
    print(
        "Drug-interaction risk model (Model 1) is separate: see ../model1/"
    )


if __name__ == "__main__":
    main()
