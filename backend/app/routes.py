"""Patient data API: profile, records, medications, catalog, notifications, activity।
প্রতিটা query-তে user_id দিয়ে filter করা হয়, তাই কেউ অন্যের data দেখতে পারে না।"""
import io
import os
import uuid
from datetime import date

from flask import Blueprint, current_app, g, jsonify, request, send_file, send_from_directory

from . import interactions
from .auth import error, login_required, phone_problem
from .ai import interaction_adapter, live_api
from .ai import prescription_extract, text_match
from .ai import model2_adapter as model2
from .models import Activity, Generic, Medication, Notification, Product, Record, db, log

bp = Blueprint("data", __name__, url_prefix="/api")

ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png"}
# ফাইলের প্রথম কয়েকটা byte (magic number): নাম .pdf হলেও ভেতরে আসলে PDF কিনা
MAGIC = {"pdf": [b"%PDF-"], "png": [b"\x89PNG\r\n\x1a\n"], "jpg": [b"\xff\xd8\xff"], "jpeg": [b"\xff\xd8\xff"]}
CATEGORIES = ("Report", "Prescription")
GENDERS = ("", "Female", "Male", "Other")
BLOOD = ("", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")


def text(v, limit):
    """যেকোনো input → trimmed string; বেশি লম্বা হলে None (তখন 400 দেওয়া হয়)।"""
    s = "" if v is None else str(v).strip()
    return s if len(s) <= limit else None


def valid_date(s, allow_future=False):
    """'' বা YYYY-MM-DD; ভবিষ্যতের তারিখ (যেখানে অর্থহীন) বাদ।"""
    if not s:
        return True
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return False
    return allow_future or d <= date.today()


def number(v, lo, hi):
    """'' / None → None; সংখ্যা সীমার মধ্যে না হলে ValueError।"""
    if v in ("", None):
        return None
    x = float(v)
    if not lo <= x <= hi:
        raise ValueError
    return x


def owned(model, item_id):
    """শুধু নিজের record পাওয়া যাবে; অন্যেরটা চাইলে 404।"""
    return model.query.filter_by(id=item_id, user_id=g.user.id).first_or_404()


# ---------- Profile ----------
@bp.get("/user")
@login_required
def get_user():
    return jsonify(g.user.to_dict())


@bp.put("/user")
@login_required
def update_user():
    d = request.get_json(silent=True) or {}
    u = g.user
    limits = {"name": ("name", 120), "phone": ("phone", 20), "dob": ("dob", 10), "gender": ("gender", 10),
              "blood": ("blood", 4), "ecName": ("ec_name", 120), "ecPhone": ("ec_phone", 20)}
    for key, (attr, limit) in limits.items():
        if key in d:
            v = text(d[key], limit)
            if v is None:
                return error(f"{key} is too long")
            setattr(u, attr, v)
    if not u.name:
        return error("Name is required")
    if (u.gender or "") not in GENDERS or (u.blood or "") not in BLOOD:
        return error("Invalid gender or blood group")
    if not valid_date(u.dob or ""):
        return error("Date of birth must be a valid past date (YYYY-MM-DD)")
    if msg := phone_problem(u.phone) or phone_problem(u.ec_phone):
        return error(msg)
    try:
        if "height" in d:
            u.height = number(d["height"], 30, 250)
        if "weight" in d:
            u.weight = number(d["weight"], 1, 400)
    except (TypeError, ValueError):
        return error("Height must be 30-250 cm and weight 1-400 kg")
    for key in ("allergies", "conditions"):
        if key in d:
            if not isinstance(d[key], list) or len(d[key]) > 50:
                return error(f"{key} must be a list of at most 50 items")
            items = [text(x, 100) for x in d[key]]
            if None in items:
                return error(f"Each item in {key} must be at most 100 characters")
            setattr(u, key, [x for x in items if x])
    log(u.id, "Updated medical profile")
    db.session.commit()
    return jsonify(u.to_dict())


# ---------- Medical records (file upload) ----------
@bp.get("/records")
@login_required
def list_records():
    return jsonify([r.to_dict() for r in Record.query.filter_by(user_id=g.user.id).order_by(Record.record_date.desc())])


@bp.post("/records")
@login_required
def upload_record():
    f = request.files.get("file")
    title = text(request.form.get("title"), 200)
    cat = request.form.get("cat") or "Report"
    rdate = (request.form.get("date") or "").strip()
    if not f or not f.filename or not title:
        return error("Title (max 200 characters) and file are required")
    if cat not in CATEGORIES:
        return error("Category must be Report or Prescription")
    if not valid_date(rdate):
        return error("Date must be a valid date that is not in the future")
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ALLOWED_EXT:
        return error("Only PDF, JPG or PNG files are allowed")
    head = f.stream.read(16)
    f.stream.seek(0)
    if not any(head.startswith(m) for m in MAGIC[ext]):
        return error("The file content does not match its type (PDF, JPG or PNG)")
    data = f.stream.read()
    stored = f"{uuid.uuid4().hex}.{ext}"
    try:  # disk copy is best-effort; the DB copy below is what survives on serverless hosts
        os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
        with open(os.path.join(current_app.config["UPLOAD_FOLDER"], stored), "wb") as out:
            out.write(data)
    except OSError:
        pass
    r = Record(user_id=g.user.id, title=title, category=cat, file_data=data,
               record_date=rdate or None, original_name=f.filename[:255], stored_name=stored)
    if cat == "Prescription" and not (request.form.get("mode") or "").startswith("Store"):
        r.extracted = _read_prescription(data, ext)   # "Store only (manual)" skips automatic reading
    db.session.add(r)
    log(g.user.id, f"Uploaded {title}")
    db.session.commit()
    return jsonify(r.to_dict()), 201


def _read_prescription(data, ext):
    """Run the AI reader and match each medicine to the catalog (so ingredient/strength can be filled in)."""
    res = prescription_extract.extract(data, ext)
    for m in res.get("medicines", []):
        m["match"] = _catalog_match(m.get("name"))
    res["imported"] = False
    return res


def _catalog_match(name):
    n = (name or "").strip()
    if len(n) < 2:
        return None
    p = (Product.query.filter(db.func.lower(Product.brand) == n.lower()).first()
         or Product.query.filter(Product.brand.ilike(n + "%")).order_by(db.func.length(Product.brand)).first())
    return {"id": p.id, "brand": p.brand, "generic": p.generic, "strength": p.strength} if p else None


_BRANDS = {}


def _brand_index():
    """{lowercase brand: brand} for text matching; loaded once per process (about 21k names)."""
    if not _BRANDS:
        for (b,) in db.session.query(Product.brand).distinct():
            if b and len(b) >= 4:
                _BRANDS.setdefault(b.strip().lower(), b.strip())
    return _BRANDS


@bp.post("/records/<int:rid>/read-text")
@login_required
def read_record_text(rid):
    """Free reader: the browser OCRs the photo (Tesseract.js) and sends only the text; medicines are found by
    matching words against the catalog. Works without any paid API key."""
    r = owned(Record, rid)
    if r.category != "Prescription":
        return error("Only prescriptions can be read automatically")
    txt = (request.get_json(silent=True) or {}).get("text")
    if not isinstance(txt, str) or not txt.strip() or len(txt) > 30000:
        return error("No readable text was sent")
    meds = text_match.find_medicines(txt, _brand_index())
    for m in meds:
        m["match"] = _catalog_match(m["name"])
    if meds:
        r.extracted = {"status": "ok", "message": "", "doctor": None, "date": None, "diagnosis": None,
                       "medicines": meds, "imported": False, "engine": "browser-ocr"}
    else:
        r.extracted = {"status": "error", "engine": "browser-ocr", "imported": False,
                       "message": "No medicine names from the catalog were recognised in this photo. Use a clearer, "
                                  "well-lit photo of a printed prescription, or add the medicines manually."}
    db.session.commit()
    return jsonify(r.to_dict())


@bp.post("/records/<int:rid>/extract")
@login_required
def extract_record(rid):
    """Read (or re-read) a stored prescription."""
    r = owned(Record, rid)
    if r.category != "Prescription":
        return error("Only prescriptions can be read automatically")
    data = r.file_data
    if not data and r.stored_name:
        path = os.path.join(current_app.config["UPLOAD_FOLDER"], r.stored_name)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                data = fh.read()
    if not data:
        return error("The stored file is no longer available. Please upload it again.", 404)
    r.extracted = _read_prescription(data, (r.stored_name or "x.jpg").rsplit(".", 1)[-1])
    db.session.commit()
    return jsonify(r.to_dict())


@bp.post("/records/<int:rid>/import-meds")
@login_required
def import_record_meds(rid):
    """Add the medicines the user confirmed from a prescription to their medication list (with safety screening)."""
    r = owned(Record, rid)
    items = (request.get_json(silent=True) or {}).get("items")
    if not isinstance(items, list) or not items or len(items) > 30:
        return error("Select 1-30 medicines to add")
    existing = {(m.name or "").lower() for m in Medication.query.filter_by(user_id=g.user.id, status="Current")}
    added, skipped, warnings = [], [], []
    for d in items:
        if not isinstance(d, dict):
            return error("Invalid medicine entry")
        m = Medication(user_id=g.user.id)
        payload = {"name": d.get("name"), "ingredient": d.get("ingredient"), "strength": d.get("strength"),
                   "dose": d.get("dose"), "freq": d.get("freq"), "start": r.record_date or "", "status": "Current"}
        payload = {k: (v if v is not None else "") for k, v in payload.items()}
        if (payload["name"] or "").strip().lower() in existing:
            skipped.append(payload["name"])
            continue
        if msg := _apply_med(m, payload):
            db.session.rollback()
            return error(f"{payload['name'] or 'Medicine'}: {msg}")
        db.session.add(m)
        db.session.flush()
        log(g.user.id, f"Added medication from prescription: {m.name}")
        warnings += _screen(m)
        existing.add(m.name.lower())
        added.append(m)
    if added and r.extracted:
        r.extracted = {**r.extracted, "imported": True}
    db.session.commit()
    return jsonify(added=[m.to_dict() for m in added], skipped=skipped, warnings=warnings)


@bp.get("/records/<int:rid>/file")
@login_required
def download_record(rid):
    r = owned(Record, rid)
    if r.file_data:
        return send_file(io.BytesIO(r.file_data), as_attachment=True, download_name=r.original_name or "record")
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], r.stored_name,
                               as_attachment=True, download_name=r.original_name)


@bp.delete("/records/<int:rid>")
@login_required
def delete_record(rid):
    r = owned(Record, rid)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], r.stored_name or "")
    if r.stored_name and os.path.exists(path):
        os.remove(path)
    db.session.delete(r)
    log(g.user.id, f"Deleted record: {r.title}")
    db.session.commit()
    return jsonify(ok=True)


# ---------- Medications ----------
MED_LIMITS = {"name": 120, "ingredient": 120, "strength": 40, "dose": 60, "freq": 60, "start": 10, "end": 10,
              "status": 10}


def _apply_med(m, d):
    for f in Medication.FIELDS:
        if f in d:
            v = text(d[f], MED_LIMITS[f])
            if v is None:
                return f"{f} must be at most {MED_LIMITS[f]} characters"
            setattr(m, f, v)
    m.status = m.status or "Current"
    if not m.name:
        return "Medicine name is required"
    if m.status not in ("Current", "Previous"):
        return "Status must be Current or Previous"
    if not valid_date(m.start or "", allow_future=True) or not valid_date(m.end or "", allow_future=True):
        return "Dates must be in YYYY-MM-DD format"
    if m.end and m.start and m.end < m.start:
        return "End date cannot be before start date"


def _screen(m):
    """Current ওষুধ হলে বাকি current ওষুধ আর allergy/condition-এর সাথে check (ঝুঁকি পেলে notification)।"""
    if m.status != "Current":
        return []
    others = Medication.query.filter(Medication.user_id == g.user.id, Medication.status == "Current",
                                     Medication.id != m.id).all() if m.id else \
        Medication.query.filter_by(user_id=g.user.id, status="Current").all()
    return interactions.screen_medication(g.user, m, [o for o in others if o is not m])


@bp.get("/meds")
@login_required
def list_meds():
    return jsonify([m.to_dict() for m in Medication.query.filter_by(user_id=g.user.id)])


@bp.post("/meds")
@login_required
def add_med():
    m = Medication(user_id=g.user.id)
    if msg := _apply_med(m, request.get_json(silent=True) or {}):
        return error(msg)
    db.session.add(m)
    log(g.user.id, f"Added medication: {m.name}")
    warnings = _screen(m)
    db.session.commit()
    return jsonify({**m.to_dict(), "warnings": warnings}), 201


@bp.put("/meds/<int:mid>")
@login_required
def update_med(mid):
    m = owned(Medication, mid)
    if msg := _apply_med(m, request.get_json(silent=True) or {}):
        db.session.rollback()
        return error(msg)
    log(g.user.id, f"Updated medication: {m.name}")
    warnings = _screen(m)
    db.session.commit()
    return jsonify({**m.to_dict(), "warnings": warnings})


@bp.delete("/meds/<int:mid>")
@login_required
def delete_med(mid):
    m = owned(Medication, mid)
    db.session.delete(m)
    log(g.user.id, f"Removed medication: {m.name}")
    db.session.commit()
    return jsonify(ok=True)


# ---------- Catalog (server-side search; ২১ হাজার ওষুধ একবারে পাঠানো হয় না) ----------
@bp.get("/catalog")
@login_required
def catalog():
    q = (request.args.get("q") or "").strip()
    form = (request.args.get("form") or "").strip()
    limit = request.args.get("limit", "30")
    limit = max(1, min(int(limit), 100)) if limit.isdigit() else 30
    query = Product.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Product.brand.ilike(like), Product.generic.ilike(like)))
        # নাম দিয়ে শুরু হলে আগে দেখাও
        query = query.order_by(db.case((Product.brand.ilike(f"{q}%"), 0), else_=1), Product.brand)
    else:
        query = query.order_by(Product.brand)
    if form:
        query = query.filter(Product.form == form)
    return jsonify([p.to_dict() for p in query.limit(limit)])


@bp.get("/catalog/forms")
@login_required
def catalog_forms():
    rows = db.session.query(Product.form, db.func.count()).group_by(Product.form).order_by(db.func.count().desc())
    return jsonify([f for f, _ in rows if f])


@bp.get("/catalog/<int:pid>")
@login_required
def catalog_item(pid):
    p = db.get_or_404(Product, pid)
    gens = [Generic.query.filter_by(name_key=x.strip().casefold()).first() for x in p.generic.split("+")]
    first_generic = p.generic.split("+")[0].strip()
    live_mono = live_api.get_live_drug_monograph(first_generic)
    return jsonify({**p.to_dict(), "generics": [
        {"name": x.name, "drug_class": x.drug_class, "indication": x.indication} for x in gens if x],
        "live_info": live_mono})


@bp.get("/catalog/<int:pid>/live")
@login_required
def catalog_live(pid):
    p = db.get_or_404(Product, pid)
    first_generic = p.generic.split("+")[0].strip()
    return jsonify(live_api.get_live_drug_monograph(first_generic))


# ---------- Alternative medicines (Model 2 দাম-তুলনা model, model2/) ----------
@bp.get("/alternatives/<int:pid>")
@login_required
def alternatives(pid):
    p = db.get_or_404(Product, pid)
    found = model2.comparisons(p.generic, p.strength, p.form, p.type)
    if found is None:
        return error("The comparison model is not available. Run `python train.py` in model2/.", 503)
    ids = {x["brand_id"] for x in found}
    by_source = {x.source_id: x for x in Product.query.filter(Product.source_id.in_(ids))}
    # Model 2 প্রথম লেখা দাম দিয়ে সাজায়; package-এর আকার আলাদা হতে পারে (60 ml বনাম 100 ml)।
    # তাই এখানে প্রতি একক (unit / ml / gm / dose) দাম বের করে একই এককের মধ্যেই তুলনা করা হয়।
    base_price, base_unit = model2.normalized_price(p.package)
    alts = []
    for x in found:
        prod = by_source.get(x["brand_id"])
        if not prod or prod.id == p.id:
            continue
        unit_price, unit = model2.normalized_price(prod.package)
        comparable = unit is not None and unit == base_unit
        diff = round(unit_price - base_price, 4) if comparable else None
        alts.append({**prod.to_dict(), "unit_price": unit_price, "unit": unit, "comparable": comparable,
                     "price_diff": diff,
                     "reason": f"Same generic, strength ({p.strength}), form ({p.form}) and type"})
    # একই এককের দামগুলো আগে, কম দাম আগে; বাকিগুলো (তুলনা করা যায় না) শেষে
    alts.sort(key=lambda a: (not a["comparable"], a["unit_price"] if a["unit_price"] is not None else float("inf")))
    for rank, a in enumerate(alts, start=1):
        a["rank"] = rank
    return jsonify(selected={**p.to_dict(), "unit_price": base_price, "unit": base_unit},
                   alternatives=alts, model=model2.info()["model_type"],
                   disclaimer="Price comparison only. Prices are compared per unit (tablet/capsule, ml, gm or dose) "
                              "only when both packages use the same unit. Consult a doctor or pharmacist before "
                              "changing any medicine.")


@bp.get("/model-info")
@login_required
def model_info():
    return jsonify(alternatives=model2.info(), interaction=interaction_adapter.info(),
                   live_apis=live_api.get_live_apis_status(),
                   database={"products": Product.query.count(), "generics": Generic.query.count()})


# ---------- Notifications, activity ----------
@bp.get("/notifications")
@login_required
def notifications():
    q = Notification.query.filter_by(user_id=g.user.id).order_by(Notification.id.desc())
    return jsonify([n.to_dict() for n in q])


@bp.post("/notifications/read-all")
@login_required
def read_all():
    Notification.query.filter_by(user_id=g.user.id).update({"read": True})
    db.session.commit()
    return jsonify(ok=True)


@bp.get("/activity")
@login_required
def activity():
    q = Activity.query.filter_by(user_id=g.user.id).order_by(Activity.id.desc()).limit(10)
    return jsonify([a.to_dict() for a in q])
