"""Dataset → database import।

    flask --app run import-data          # model2/ ফোল্ডারের CSV + model1/data/ddinter থেকে

কোন ফাইল কোথায় যায়:
  medicine.csv  → products   (ব্র্যান্ড, generic, strength, form, কোম্পানি, দাম, package)
  generic.csv   → generics   (drug class, indication, interaction ও contraindication-এর বর্ণনা)
  data/ddinter/*.csv → known_interaction (DDInter 2.0-এর Major/Moderate/Minor pair; Verified)
বাকি CSV (manufacturer, dosage form, drug class, indication) শুধু নামের তালিকা; ওই নামগুলো
উপরের দুই টেবিলেই আছে, তাই আলাদা টেবিল বানানো হয়নি।
"""
import csv
import glob
import html
import os
import re

import click
from flask import current_app
from flask.cli import with_appcontext

from .ai import load_module
from .ai.model2_adapter import extract_price
from .models import Generic, KnownInteraction, Product, db

TAG = re.compile(r"<[^>]+>")


def clean_html(text):
    text = TAG.sub(" ", text or "")
    return " ".join(html.unescape(text).split())


def import_medicines(path):
    db.session.query(Product).delete()
    batch = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("brand name") or "").strip() or not (r.get("generic") or "").strip():
                continue
            pkg = (r.get("package container") or "").strip().rstrip(",")
            batch.append(dict(source_id=r["brand id"], brand=r["brand name"].strip(), generic=r["generic"].strip(),
                              strength=r["strength"].strip(), form=r["dosage form"].strip(),
                              maker=r["manufacturer"].strip(), type=r["type"].strip() or "allopathic",
                              price=extract_price(pkg), package=pkg[:255], source="medicine.csv (MedEx)"))
    db.session.bulk_insert_mappings(Product, batch)
    return len(batch)


def import_generics(path):
    db.session.query(Generic).delete()
    batch = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            name = (r.get("generic name") or "").strip()
            if not name:
                continue
            batch.append(dict(source_id=r["generic id"], name=name, name_key=name.casefold(),
                              drug_class=(r.get("drug class") or "").strip()[:255],
                              indication=(r.get("indication") or "").strip()[:255],
                              interaction_text=clean_html(r.get("interaction description")),
                              contraindication_text=clean_html(r.get("contraindications description"))))
    db.session.bulk_insert_mappings(Generic, batch)
    return len(batch)


DDINTER_LEVELS = {"Major": "high", "Moderate": "moderate", "Minor": "low"}  # "Unknown" = model-এর কাজ
DDINTER_SOURCE = "DDInter 2.0 (CC BY-NC-SA 4.0)"


def import_ddinter(folder):
    """DDInter 2.0-এর জানা severity-র pair → KnownInteraction (Verified)।

    DDInter-এ নাম "Amlodipine", আমাদের catalog-এ "Amlodipine Besilate"; তাই model1/drug_names.py দিয়ে
    আমাদের প্রতিটা উপাদানের নাম DDInter-এর নামের সাথে মেলানো হয়, আর row লেখা হয় আমাদের নামেই
    (interactions.py যেভাবে খোঁজে)। ফাইল না থাকলে (download হয়নি) কিছুই করে না।"""
    files = sorted(glob.glob(os.path.join(folder, "data", "ddinter", "ddinter_downloads_code_*.csv")))
    if not files:
        return None
    names = load_module("MODEL1_DIR", "drug_names")

    rows = {}
    for path in files:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                sev = DDINTER_LEVELS.get((r.get("Level") or "").strip())
                if sev:
                    a, b = sorted([names.normalize(r["Drug_A"]), names.normalize(r["Drug_B"])])
                    rows[(a, b)] = (r.get("Level").strip(), sev)
    known = {n for pair in rows for n in pair}

    # আমাদের সব উপাদানের নাম (product-এর generic ভেঙে + generic.csv) → DDInter নাম
    local = {x.strip().casefold() for (g,) in db.session.query(Product.generic).distinct()
             for x in g.split("+") if x.strip()}
    local |= {k for (k,) in db.session.query(Generic.name_key) if k and "+" not in k}
    to_local = {}
    for key in local:
        hit = names.resolve(key, known)
        if hit:
            to_local.setdefault(hit, []).append(key)

    db.session.query(KnownInteraction).filter_by(source=DDINTER_SOURCE).delete()
    batch = []
    for (a, b), (level, sev) in rows.items():
        for x in to_local.get(a, ()):
            for y in to_local.get(b, ()):
                if x != y:
                    k1, k2 = sorted([x, y])
                    batch.append(dict(generic_a=k1[:120], generic_b=k2[:120], severity=sev,
                                      text=f"Listed in DDInter 2.0 as {level} interaction", source=DDINTER_SOURCE))
    db.session.bulk_insert_mappings(KnownInteraction, batch)
    for ix in KnownInteraction.__table__.indexes:
        ix.create(db.session.connection(), checkfirst=True)  # একই transaction, তাই SQLite lock হয় না
    return len(batch), len(to_local)


@click.command("import-data")
@with_appcontext
@click.option("--folder", default=None, help="CSV ফোল্ডার (ডিফল্ট: config-এর MODEL2_DIR)")
def import_command(folder):
    folder = folder or current_app.config["MODEL2_DIR"]
    db.create_all()
    n_med = import_medicines(os.path.join(folder, "medicine.csv"))
    n_gen = import_generics(os.path.join(folder, "generic.csv"))
    db.session.flush()
    ddi = import_ddinter(current_app.config["MODEL1_DIR"])
    db.session.commit()
    click.echo(f"Imported {n_med:,} medicines and {n_gen:,} generics from {folder}")
    if ddi:
        click.echo(f"Imported {ddi[0]:,} verified DDInter 2.0 interactions ({ddi[1]:,} DDInter drugs matched)")
    else:
        click.echo("DDInter files not found (run model1/download_ddi.py); verified interactions skipped")


@click.command("check-live-apis")
@with_appcontext
def check_live_apis_command():
    from .ai import live_api
    status = live_api.get_live_apis_status()
    click.echo("=== MediSafe Live External APIs Status ===")
    for k, v in status.items():
        click.echo(f"[{v['name']}] Provider: {v['provider']} | Tier: {v['tier']} | Connected: {v['connected']}")
        click.echo(f"  Capabilities: {', '.join(v['capabilities'])}")


# ---- শুধু automated test-এর জন্য ছোট কাল্পনিক data ----
def seed_sample():
    db.session.add_all([
        Product(source_id="t1", brand="Sample Brand A", generic="Sampleamol", strength="500 mg", form="Tablet",
                maker="Demo Pharma", type="allopathic", price=1.2),
        Product(source_id="t2", brand="Sample Brand D", generic="Demozole", strength="20 mg", form="Capsule",
                maker="Example Labs", type="allopathic", price=6),
        Product(source_id="t3", brand="Sample Brand F", generic="Testicillin", strength="250 mg", form="Capsule",
                maker="Test Healthcare", type="allopathic", price=8),
        Generic(name="Demozole", name_key="demozole",
                interaction_text="Co-administration with Testicillin may raise plasma levels.", contraindication_text=""),
        KnownInteraction(generic_a="sampleamol", generic_b="testicillin", severity="moderate",
                         text="Sample verified warning", source="Sample data"),
    ])
    db.session.commit()
