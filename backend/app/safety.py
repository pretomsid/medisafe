"""Rule-based safety screening: রোগীর allergy আর medical condition বনাম নির্বাচিত ওষুধ।

এটা ML নয় (proposal: "Safety screening against verified drug–condition and drug-allergy information")।
  Allergy   : রোগীর লেখা allergy (যেমন "Penicillin") ওষুধের উপাদান, তার drug class, বা নিচের
              allergy-group তালিকার সাথে মেলে কিনা। যেমন penicillin allergy → amoxicillin।
  Condition : রোগীর রোগ (যেমন "Kidney disease") ওষুধের monograph-এর contraindication অংশে
              (generic.csv, MedEx) লেখা আছে কিনা। প্রতিশব্দ দিয়েও খোঁজা হয় (kidney → renal)।
এটা keyword screening, সম্পূর্ণ তালিকা নয়: কিছু না পাওয়া মানে "নিরাপদ" নয়।
"""
import re

from .models import Generic

# allergy শব্দ → যে উপাদান/শব্দাংশ মিললে সতর্ক করা হবে (সাধারণ cross-reactive group)
ALLERGY_GROUPS = {
    "penicillin": ["penicillin", "amoxicillin", "ampicillin", "cloxacillin", "flucloxacillin", "piperacillin",
                   "pivmecillinam", "mecillinam", "benzathine"],
    "cephalosporin": ["cef", "ceph"],
    "sulfa": ["sulfa", "sulpha", "co-trimoxazole", "cotrimoxazole"],
    "sulpha": ["sulfa", "sulpha", "co-trimoxazole", "cotrimoxazole"],
    "nsaid": ["ibuprofen", "naproxen", "diclofenac", "aceclofenac", "ketorolac", "indometacin", "indomethacin",
              "piroxicam", "meloxicam", "etoricoxib", "celecoxib", "mefenamic", "flurbiprofen", "ketoprofen",
              "aspirin", "acetylsalicylic", "tenoxicam", "lornoxicam", "nimesulide", "etodolac", "dexketoprofen"],
    "aspirin": ["aspirin", "acetylsalicylic"],
    "macrolide": ["azithromycin", "clarithromycin", "erythromycin", "roxithromycin"],
    "quinolone": ["floxacin"],
    "fluoroquinolone": ["floxacin"],
    "tetracycline": ["cycline"],
    "opioid": ["morphine", "codeine", "tramadol", "pethidine", "fentanyl", "oxycodone", "tapentadol", "nalbuphine"],
    "iodine": ["iodine", "povidone", "iohexol", "iopamidol"],
}
ALLERGY_GROUPS["penicillins"] = ALLERGY_GROUPS["penicillin"]
ALLERGY_GROUPS["sulfonamide"] = ALLERGY_GROUPS["sulfa"]
ALLERGY_GROUPS["nsaids"] = ALLERGY_GROUPS["nsaid"]

# রোগীর রোগের শব্দ → monograph-এ যে শব্দ (শুরুর অংশ) খোঁজা হবে
CONDITION_TERMS = {
    "kidney": ["renal", "kidney", "nephro"], "renal": ["renal", "kidney"], "ckd": ["renal", "kidney"],
    "liver": ["hepatic", "liver", "cirrho"], "hepat": ["hepatic", "liver", "hepatitis"], "cirrhosis": ["cirrho", "hepatic"],
    "pregnan": ["pregnan"], "breastfeed": ["breast-feed", "breastfeed", "lactat", "nursing"],
    "lactation": ["lactat", "breast"],
    "heart": ["heart", "cardiac"], "cardiac": ["cardiac", "heart"],
    "asthma": ["asthma", "bronchospasm"], "copd": ["obstructive pulmonary", "copd"],
    "diabet": ["diabet", "ketoacidosis"], "hypertension": ["hypertension"], "blood pressure": ["hypertension"],
    "hypotension": ["hypotension"], "epilep": ["epilep", "seizure", "convuls"], "seizure": ["seizure", "epilep"],
    "glaucoma": ["glaucoma"], "ulcer": ["ulcer"], "gastric": ["gastric", "peptic"], "peptic": ["peptic", "ulcer"],
    "bleeding": ["bleeding", "haemorrha", "hemorrha"], "porphyria": ["porphyria"],
    "myasthenia": ["myasthenia"], "thyroid": ["thyroid"], "gout": ["gout"], "prostat": ["prostat"],
    "g6pd": ["g6pd", "glucose-6-phosphate"],
}


def _find(text, term):
    """text-এ term কোনো শব্দের শুরুতে আছে কিনা; থাকলে আশেপাশের বাক্যটুকু ফেরত দেয়।"""
    if not text or len(term) < 3:
        return None
    m = re.search(r"(?<![\w])" + re.escape(term), text, re.IGNORECASE)
    if not m:
        return None
    start = max(text.rfind(".", 0, m.start()) + 1, m.start() - 160)
    end = text.find(".", m.end())
    end = len(text) if end == -1 else min(end + 1, m.end() + 160)
    return text[start:end].strip()


def _generic(name_key):
    return Generic.query.filter_by(name_key=name_key).first()


def allergy_hits(allergies, brand, ingredient_keys):
    out = []
    for allergy in allergies or []:
        a = allergy.strip().casefold()
        if len(a) < 3:
            continue
        group = next((v for k, v in ALLERGY_GROUPS.items() if k in a), None)
        terms = (group or []) + [a]
        for ing in ingredient_keys:
            gen = _generic(ing)
            hay = f"{ing} {(gen.drug_class or '') if gen else ''}".casefold()
            if any(t in hay for t in terms):
                why = f"class: {gen.drug_class}" if gen and gen.drug_class and a in gen.drug_class.casefold() else ing
                out.append({"brand": brand, "kind": "allergy", "severity": "high",
                            "text": f"You recorded an allergy to “{allergy}”. {brand} contains {ing.title()} ({why}).",
                            "source": "Allergy screening rule (patient profile + drug name/class)"})
                break
    return out


def condition_hits(conditions, brand, ingredient_keys):
    out = []
    for cond in conditions or []:
        c = cond.strip().casefold()
        if len(c) < 3:
            continue
        terms = next((v for k, v in CONDITION_TERMS.items() if k in c), None) or [c]
        for ing in ingredient_keys:
            gen = _generic(ing)
            if not gen or not gen.contraindication_text:
                continue
            hit = next((s for t in terms if (s := _find(gen.contraindication_text, t))), None)
            if hit:
                out.append({"brand": brand, "kind": "condition", "severity": "moderate",
                            "text": f"Your condition “{cond}”: {gen.name} monograph contraindications mention it: “{hit}”",
                            "source": "generic.csv (MedEx monograph)"})
                break
    return out


def screen(user, items):
    """items: [(brand, [ingredient name_key, ...])] → allergy + condition সতর্কতা।"""
    found = []
    for brand, ings in items:
        found += allergy_hits(user.allergies, brand, ings)
        found += condition_hits(user.conditions, brand, ings)
    return found
