"""Bring package prices to one unit so they can be compared fairly.

MedEx lists prices per package: "Unit Price: ৳ 1.20" (per tablet/capsule), "100 ml bottle: ৳ 40",
"15 gm tube: ৳ 120", "200 metered doses: ৳ 350" ... A 60 ml and a 100 ml bottle cannot be
compared by their listed price, so normalized_price() returns the price per unit, ml, gm or dose.
The backend compares two products only when both have the same unit.
Only the standard library is used.
"""
import re

_UNIT_PRICE = re.compile(r"Unit Price:\s*৳\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_PACK_PRICE = re.compile(r"^\s*([\d.]+)\s*(ml|gm|mg|iu|metered doses?|metered sprays?|tablets?)\b[^:]*:\s*৳\s*([\d,]+(?:\.\d+)?)",
                         re.IGNORECASE)
_UNIT_NAME = {"ml": "ml", "gm": "gm", "mg": "mg", "iu": "IU", "tablet": "tablet", "tablets": "tablet",
              "metered dose": "dose", "metered doses": "dose", "metered spray": "dose", "metered sprays": "dose"}


def normalized_price(package):
    """'100 ml bottle: ৳ 40.12' -> (0.4012, 'ml'); 'Unit Price: ৳ 1.20' -> (1.2, 'unit'); unknown -> (None, None)."""
    text = package or ""
    m = _UNIT_PRICE.search(text)
    if m:
        return float(m.group(1).replace(",", "")), "unit"
    m = _PACK_PRICE.search(text)
    if m:
        size, unit, price = float(m.group(1)), m.group(2).lower(), float(m.group(3).replace(",", ""))
        if size > 0:
            return price / size, _UNIT_NAME.get(unit, unit)
    return None, None
