"""Drug interaction check।

প্রতিটা ওষুধ-জোড়ার জন্য তিন ধাপে প্রমাণ খোঁজা হয়, ভরসার ক্রম অনুযায়ী:
  ১. Verified    : KnownInteraction টেবিল (যাচাই করা উৎস, severity সহ)।
  ২. Documented  : generic.csv-এর monograph-এ একটা ওষুধের interaction অংশে অন্যটার নাম আছে কি না।
                   এটা "লেখা আছে" প্রমাণ, ঝুঁকির মাত্রা নয়; তাই category = "documented"।
  ৩. Predicted   : Model 1 (semi-supervised Label Spreading, DDInter 2.0 data; set_predictor দিয়ে লাগানো)।
                   DDInter-এ যে pair-এর severity "Unknown", সেগুলোর risk অনুমান করে। Documented pair-এও
                   prediction থাকলে সেটা যোগ হয়। Model-এর JSON না থাকলে connected = false।
  DDInter-এর জানা severity (Major/Moderate/Minor) import-data দিয়ে KnownInteraction-এ আসে, তাই ওগুলো Verified।
কিছু না পেলে "unknown" — কখনো "safe" বলা হয় না।
"""
import re
from types import SimpleNamespace

from flask import Blueprint, g, jsonify, request

from . import safety
from .ai import live_api
from .auth import error, login_required
from .models import Generic, KnownInteraction, Notification, Product, db, log

bp = Blueprint("interactions", __name__, url_prefix="/api/interactions")

_predictor = None
CONFIDENCE_THRESHOLD = 0.6
ORDER = ["low", "moderate", "high"]
MAX_ITEMS = 10  # ১০টা ওষুধ = ৪৫টা জোড়া; এর বেশি হলে request ধীর হয়


def normalize_level(lvl):
    l = (lvl or "").lower()
    if l in ("major", "high"):
        return "high"
    if l in ("minor", "low"):
        return "low"
    if l == "moderate":
        return "moderate"
    return "moderate" if l in ORDER else "unknown"


def set_predictor(fn):
    """AI risk model লাগানোর জায়গা: fn(generic_a, generic_b) -> {"category", "confidence"} বা None।"""
    global _predictor
    _predictor = fn


def ingredients(product):
    """'Paracetamol + Caffeine' → ['paracetamol', 'caffeine']"""
    return [x.strip().casefold() for x in product.generic.split("+") if x.strip()]


def mention(text, term):
    """text-এ term পুরো শব্দ হিসেবে থাকলে (বহুবচনসহ) সেই বাক্যটা ফেরত দেয়।"""
    if not text or len(term) < 4:
        return None
    m = re.search(r"(?<![\w])" + re.escape(term) + r"(?:s|es)?(?![\w])", text, re.IGNORECASE)
    if not m:
        return None
    start = max(text.rfind(".", 0, m.start()) + 1, m.start() - 220)
    end = text.find(".", m.end())
    end = len(text) if end == -1 else min(end + 1, m.end() + 220)
    return text[start:end].strip()


STOP = {"oral", "drugs", "drug", "preparations", "preparation", "other", "topical", "combined", "specific", "&", "and"}


def name_terms(gen):
    """'Warfarin Sodium' → ['warfarin sodium', 'warfarin']"""
    terms = [gen.name_key]
    first = gen.name_key.split()[0]
    if len(first) >= 5 and first != gen.name_key:
        terms.append(first)
    return terms


def class_term(gen):
    """'Oral Anti-coagulants' → 'anticoagulant' (monograph প্রায়ই শ্রেণির নাম লেখে)"""
    words = [w for w in (gen.drug_class or "").lower().replace("-", "").split() if w not in STOP]
    if not words or len(words) > 3:
        return None
    term = " ".join(words)
    term = term[:-1] if term.endswith("s") else term
    return term if len(term) >= 8 else None


def documented(ings_a, ings_b):
    """A-এর monograph-এর interaction অংশে B-এর নাম বা B-এর drug class লেখা আছে কি না।"""
    found = []
    for a in ings_a:
        ga = Generic.query.filter_by(name_key=a).first()
        if not ga or not ga.interaction_text:
            continue
        text = ga.interaction_text.replace("-", "")
        for b in ings_b:
            gb = Generic.query.filter_by(name_key=b).first()
            terms = name_terms(gb) if gb else [b]
            hit = next((s for t in terms if (s := mention(text, t))), None)
            kind = "names"
            if not hit and gb and (ct := class_term(gb)):
                hit, kind = mention(text, ct), f"mentions the class of {gb.name} ({gb.drug_class})"
            if hit:
                label = f"names {gb.name if gb else b}" if kind == "names" else kind
                found.append(f"{ga.name} monograph {label}: “{hit}” (Source: generic.csv)")
    return found


def check_pair(a, b):
    ia, ib = ingredients(a), ingredients(b)
    result = {"a": a.brand, "b": b.brand, "category": "unknown", "predicted": None, "verified": [],
              "management": None, "references": []}

    # একই active ingredient দুই ওষুধে = dose দ্বিগুণ হওয়ার ঝুঁকি (যেমন দুই brand-এর paracetamol)
    same = sorted(set(ia) & set(ib))
    if same:
        result["category"] = "duplicate"
        result["verified"].append(f"Both medicines contain {', '.join(s.title() for s in same)}. Taking both may "
                                  f"exceed the safe dose (therapeutic duplication rule).")
        result["references"] = [{
            "citation": "World Health Organization (WHO) Guidelines for ATC/DDD Therapeutic Duplication Screening",
            "source": "Clinical Pharmacy Practice Guidelines",
            "link": None
        }]
        return result

    ddinter_live = None
    # 1. KnownInteraction (local DDInter verified)
    for x in ia:
        for y in ib:
            k1, k2 = sorted([x, y])
            for r in KnownInteraction.query.filter_by(generic_a=k1, generic_b=k2):
                result["verified"].append(f"{r.severity.title()}: {r.text} (Source: {r.source})")
                sev = normalize_level(r.severity)
                if sev in ORDER and (result["category"] not in ORDER or ORDER.index(sev) > ORDER.index(result["category"])):
                    result["category"] = sev

    # 2. DDInter Live API (https://ddinter.scbdd.com/): details, management & literature references
    for x in ia:
        for y in ib:
            ddinter_live = live_api.check_ddinter_live_interaction(x, y)
            if ddinter_live:
                if ddinter_live.get("description") and not any(ddinter_live["description"][:40] in v for v in result["verified"]):
                    result["verified"].append(f"{ddinter_live['category'].title()}: {ddinter_live['description']} (Source: {ddinter_live['source']})")
                cat = normalize_level(ddinter_live["category"])
                if cat in ORDER and (result["category"] not in ORDER or ORDER.index(cat) > ORDER.index(result["category"])):
                    result["category"] = cat
                if ddinter_live.get("management"):
                    result["management"] = ddinter_live["management"]
                break
        if ddinter_live:
            break

    # 3. Documented (local generic.csv monographs)
    docs = documented(ia, ib) + documented(ib, ia)
    if docs:
        if result["category"] == "unknown":
            result["category"] = "documented"
        result["verified"].extend(docs[:3])

    # 4. Model 1 semi-supervised prediction (DDInter 2.0)
    best = predict_pair(ia, ib)
    if best:
        result["category"] = best["category"]
        result["predicted"] = (f"{best['category'].title()} (confidence {best['confidence']:.0%}; "
                               f"{best['a'].title()} + {best['b'].title()}; semi-supervised model, DDInter 2.0)")

    # 5. OpenFDA Live Drug Interactions
    for x in ia:
        for y in ib:
            live = live_api.check_openfda_interaction(x, y)
            if live:
                result["verified"].append(f"{live['category'].title()}: {live['snippet']} (Source: {live['source']})")
                cat = normalize_level(live["category"])
                if cat in ORDER and (result["category"] not in ORDER or ORDER.index(cat) > ORDER.index(result["category"])):
                    result["category"] = cat
                break

    # Build primary literature references and guidelines for clinical evidence
    result["references"] = live_api.build_interaction_references(result["verified"], ddinter_live=ddinter_live)
    return result


def predict_pair(ia, ib):
    if not _predictor:
        return None
    best = None
    for x in ia:
        for y in ib:
            p = _predictor(x, y)
            if not p or p["confidence"] < CONFIDENCE_THRESHOLD:
                continue
            if best is None or ORDER.index(p["category"]) > ORDER.index(best["category"]):
                best = {**p, "a": x, "b": y}
    return best


@bp.post("/check")
@login_required
def check():
    ids = (request.get_json(silent=True) or {}).get("items") or []
    if not isinstance(ids, list):
        return error("items must be a list of medicine ids")
    ids = list(dict.fromkeys(int(i) for i in ids if str(i).isdigit()))
    if len(ids) > MAX_ITEMS:
        return error(f"Select at most {MAX_ITEMS} medicines at a time")
    products = [p for p in (db.session.get(Product, i) for i in ids) if p]
    if not products:
        return error("Select at least one medicine from the catalog")
    pairs = [check_pair(products[i], products[j])
             for i in range(len(products)) for j in range(i + 1, len(products))]
    warnings = safety.screen(g.user, [(p.brand, ingredients(p)) for p in products])
    log(g.user.id, "Ran interaction check: " + ", ".join(p.brand for p in products))
    db.session.commit()
    return jsonify(connected=_predictor is not None, pairs=pairs, safety=warnings,
                   live_apis=live_api.get_live_apis_status())


# ---------- নতুন ওষুধ যোগ করলে নিজে থেকে check (proposal workflow step 4) ----------
def as_item(med):
    """রোগীর Medication → check_pair যা বোঝে (brand + generic)। Catalog-এ brand মিললে সেটার generic,
    না মিললে রোগীর লেখা active ingredient।"""
    p = Product.query.filter(db.func.lower(Product.brand) == (med.name or "").strip().lower()).first()
    generic = p.generic if p else (med.ingredient or "")
    return SimpleNamespace(brand=med.name, generic=generic) if generic.strip() else None


def screen_medication(user, med, others):
    """নতুন/বদলানো ওষুধ বনাম রোগীর অন্য current ওষুধ + allergy/condition। ঝুঁকি পেলে Notification।"""
    item = as_item(med)
    if not item:
        return []
    found = []
    for other in others:
        o = as_item(other)
        if not o:
            continue
        r = check_pair(item, o)
        if r["category"] != "unknown":
            label = r["category"].title() if r["category"] in ORDER else r["category"]
            found.append({"title": f"Possible interaction: {item.brand} + {o.brand}",
                          "text": f"{label}. {(r['predicted'] or (r['verified'] or [''])[0])}"[:255]})
    for w in safety.screen(user, [(item.brand, ingredients(item))]):
        found.append({"title": f"{w['kind'].title()} warning: {item.brand}", "text": w["text"][:255]})
    for f in found:
        exists = Notification.query.filter_by(user_id=user.id, title=f["title"][:200], read=False).first()
        if not exists:
            db.session.add(Notification(user_id=user.id, type="Interaction", title=f["title"][:200], text=f["text"]))
    return found
