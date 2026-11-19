"""ছোট automated test: `.venv/bin/pytest` দিয়ে চালান।"""
import io

import pytest

from app import create_app
from app.config import TestConfig


MED_CSV = """brand id,brand name,type,slug,dosage form,generic,strength,manufacturer,package container,Package Size
1,Alpha,allopathic,a,Tablet,Paracetamol,500 mg,Maker A,"Unit Price: ৳ 1.20,",
2,Beta,allopathic,b,Tablet,Paracetamol,500 mg,Maker B,"Unit Price: ৳ 0.90,",
3,Gamma,allopathic,c,Syrup,Paracetamol,500 mg,Maker C,100 ml bottle: ৳ 40.00,
4,Delta,allopathic,d,Tablet,Probenecid,500 mg,Maker D,"Unit Price: ৳ 3.00,",
5,Epsi,allopathic,e,Tablet,Acyclovir,400 mg,Maker E,"Unit Price: ৳ 9.00,",
"""
GEN_CSV = """generic id,generic name,drug class,indication,interaction description,contraindications description
1,Acyclovir,Antiviral,Herpes,"<div>Co-administration of probenecid with Acyclovir increases half-life.</div>","<p>Hypersensitivity. Use with caution in severe renal impairment.</p>"
"""


@pytest.fixture(autouse=True)
def reset_login_limits():
    """Login-এর ভুল চেষ্টার হিসাব memory-তে থাকে; এক test-এর হিসাব যেন অন্য test-এ না যায়।"""
    from app import auth
    auth._fails.clear()


@pytest.fixture
def client(tmp_path):
    """ছোট একটা CSV দিয়ে আসল import আর আসল model2 train.py চালানো হয়। Model 1 নেই (খালি model1/)।"""
    import shutil, subprocess, sys, os
    model_dir = tmp_path / "model2"
    model_dir.mkdir()
    (tmp_path / "model1").mkdir()
    real = os.path.join(os.path.dirname(__file__), "..", "..", "model2")
    for f in ("train.py", "predict.py", "price_units.py"):
        shutil.copy(os.path.join(real, f), model_dir)
    (model_dir / "medicine.csv").write_text(MED_CSV, encoding="utf-8")
    (model_dir / "generic.csv").write_text(GEN_CSV, encoding="utf-8")
    subprocess.run([sys.executable, "train.py"], cwd=model_dir, check=True, capture_output=True)

    class C(TestConfig):
        UPLOAD_FOLDER = str(tmp_path / "up")
        MODEL2_DIR = str(model_dir)
        MODEL1_DIR = str(tmp_path / "model1")
    app = create_app(C)
    app.test_cli_runner().invoke(args=["import-data"])
    return app.test_client()


def pid(c, brand):
    return next(p["id"] for p in c.get(f"/api/catalog?q={brand}").get_json() if p["brand"] == brand)


def register(c, email="a@test.com"):
    return c.post("/api/auth/register", json={"name": "Test", "email": email, "password": "secret123"})


def test_must_login_first(client):
    assert client.get("/api/meds").status_code == 401


def test_register_login_and_wrong_password(client):
    assert register(client).status_code == 201
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "a@test.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "a@test.com", "password": "secret123"}).status_code == 200


def test_medication_crud(client):
    register(client)
    m = client.post("/api/meds", json={"name": "Sample Brand A", "status": "Current"}).get_json()
    client.put(f"/api/meds/{m['id']}", json={"status": "Previous"})
    assert client.get("/api/meds").get_json()[0]["status"] == "Previous"
    assert client.delete(f"/api/meds/{m['id']}").status_code == 200


def test_user_cannot_see_others_data(client):
    register(client, "a@test.com")
    mid = client.post("/api/meds", json={"name": "X"}).get_json()["id"]
    client.post("/api/auth/logout")
    register(client, "b@test.com")
    assert client.get("/api/meds").get_json() == []
    assert client.delete(f"/api/meds/{mid}").status_code == 404


def test_upload_rejects_bad_file(client):
    register(client)
    bad = {"title": "x", "file": (io.BytesIO(b"x"), "virus.exe")}
    assert client.post("/api/records", data=bad, content_type="multipart/form-data").status_code == 400
    fake = {"title": "x", "file": (io.BytesIO(b"MZ\x90\x00 not a pdf"), "report.pdf")}  # নাম .pdf, ভেতরে অন্য কিছু
    assert client.post("/api/records", data=fake, content_type="multipart/form-data").status_code == 400
    ok = {"title": "Report", "cat": "Report", "file": (io.BytesIO(b"%PDF-1.7\n"), "r.pdf")}
    assert client.post("/api/records", data=ok, content_type="multipart/form-data").status_code == 201


def test_catalog_imported_from_csv(client):
    register(client)
    items = client.get("/api/catalog?q=para").get_json()
    assert {p["brand"] for p in items} == {"Alpha", "Beta", "Gamma"}
    assert next(p for p in items if p["brand"] == "Beta")["price"] == 0.9


def test_alternatives_use_model2(client):
    register(client)
    r = client.get(f"/api/alternatives/{pid(client, 'Alpha')}").get_json()
    # শুধু একই generic + strength + form; Syrup (Gamma) বাদ, নিজেও বাদ
    assert [a["brand"] for a in r["alternatives"]] == ["Beta"]
    assert round(r["alternatives"][0]["price_diff"], 2) == -0.3
    assert r["alternatives"][0]["unit"] == "unit" and r["alternatives"][0]["comparable"] is True


def test_interaction_documented_and_unknown(client):
    register(client)
    r = client.post("/api/interactions/check",
                    json={"items": [pid(client, "Epsi"), pid(client, "Delta")]}).get_json()
    assert r["pairs"][0]["category"] == "documented" and "probenecid" in r["pairs"][0]["verified"][0].lower()
    r = client.post("/api/interactions/check",
                    json={"items": [pid(client, "Alpha"), pid(client, "Delta")]}).get_json()
    assert r["pairs"][0]["category"] == "unknown"  # তথ্য নেই মানে "safe" নয়


# ---- Model 1: DDInter verified + semi-supervised prediction (ছোট কাল্পনিক DDInter ফাইল ও model JSON) ----
DDI_CSV = """DDInterID_A,Drug_A,DDInterID_B,Drug_B,Level
DDInter1,Acetaminophen,DDInter2,Probenecid,Major
DDInter1,Acetaminophen,DDInter3,Acyclovir,Unknown
DDInter2,Probenecid,DDInter3,Acyclovir,Unknown
"""


@pytest.fixture
def client_ddi(tmp_path):
    import json, shutil, os
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    m2 = tmp_path / "model2"
    m2.mkdir()
    for f in ("train.py", "predict.py", "price_units.py"):
        shutil.copy(os.path.join(root, "model2", f), m2)
    (m2 / "medicine.csv").write_text(MED_CSV, encoding="utf-8")
    (m2 / "generic.csv").write_text(GEN_CSV, encoding="utf-8")
    m1 = tmp_path / "model1"
    (m1 / "data" / "ddinter").mkdir(parents=True)
    (m1 / "models").mkdir()
    shutil.copy(os.path.join(root, "model1", "drug_names.py"), m1)
    (m1 / "data" / "ddinter" / "ddinter_downloads_code_A.csv").write_text(DDI_CSV, encoding="utf-8")
    (m1 / "models" / "interaction_risk_model.json").write_text(json.dumps({
        "model_type": "test", "classes": ["low", "moderate", "high"],
        "drugs": ["acetaminophen", "acyclovir", "probenecid"],
        "predictions": {"acetaminophen|acyclovir": {"category": "moderate", "confidence": 0.8},
                        "acyclovir|probenecid": {"category": "high", "confidence": 0.4}}}), encoding="utf-8")

    class C(TestConfig):
        UPLOAD_FOLDER = str(tmp_path / "up")
        MODEL2_DIR = str(m2)
        MODEL1_DIR = str(m1)
    app = create_app(C)
    out = app.test_cli_runner().invoke(args=["import-data"])
    assert "verified DDInter" in out.output
    c = app.test_client()
    register(c)
    return c


def check(c, a, b):
    return c.post("/api/interactions/check", json={"items": [pid(c, a), pid(c, b)]}).get_json()


def test_ddinter_known_level_is_verified(client_ddi):
    # Paracetamol (আমাদের নাম) = Acetaminophen (DDInter-এর নাম)
    r = check(client_ddi, "Alpha", "Delta")
    assert r["connected"] is True
    assert r["pairs"][0]["category"] == "high" and "DDInter" in r["pairs"][0]["verified"][0]
    assert r["pairs"][0]["predicted"] is None


def test_unknown_ddinter_pair_gets_model_prediction(client_ddi):
    r = check(client_ddi, "Alpha", "Epsi")
    assert r["pairs"][0]["category"] == "moderate" and "80%" in r["pairs"][0]["predicted"]


def test_low_confidence_prediction_is_not_shown(client_ddi):
    # confidence 0.4 < 0.6 → prediction বাদ, monograph-এর "documented" প্রমাণটাই থাকে
    r = check(client_ddi, "Epsi", "Delta")
    assert r["pairs"][0]["category"] == "documented" and r["pairs"][0]["predicted"] is None


def test_model_not_connected_without_json(client):
    register(client)
    r = check(client, "Alpha", "Delta")
    assert r["connected"] is False and r["pairs"][0]["category"] == "unknown"
    assert client.get("/api/model-info").get_json()["interaction"] == {"loaded": False}


# ---- Safety screening, duplicate, auto-check, validation ----
def test_duplicate_ingredient_is_flagged(client):
    register(client)
    r = check(client, "Alpha", "Beta")  # দুটোই Paracetamol
    assert r["pairs"][0]["category"] == "duplicate"


def test_allergy_and_condition_screening(client):
    register(client)
    client.put("/api/user", json={"allergies": ["Acyclovir"], "conditions": ["Kidney disease"]})
    r = client.post("/api/interactions/check", json={"items": [pid(client, "Epsi")]}).get_json()
    kinds = {w["kind"] for w in r["safety"]}
    assert kinds == {"allergy", "condition"} and r["pairs"] == []
    assert "renal" in next(w["text"] for w in r["safety"] if w["kind"] == "condition").lower()


def test_adding_medication_auto_checks_and_notifies(client):
    register(client)
    client.post("/api/meds", json={"name": "Alpha", "ingredient": "Paracetamol", "status": "Current"})
    r = client.post("/api/meds", json={"name": "Beta", "ingredient": "Paracetamol", "status": "Current"}).get_json()
    assert r["warnings"] and "Alpha" in r["warnings"][0]["title"]
    titles = [n["title"] for n in client.get("/api/notifications").get_json()]
    assert any("Possible interaction" in t for t in titles)


def test_input_validation(client):
    assert client.post("/api/auth/register", json={"name": "A", "email": "x@test.com",
                                                   "password": "abcdefgh"}).status_code == 400  # সংখ্যা নেই
    register(client)
    assert client.put("/api/user", json={"height": "tall"}).status_code == 400
    assert client.put("/api/user", json={"dob": "2999-01-01"}).status_code == 400
    assert client.put("/api/user", json={"blood": "Z+"}).status_code == 400
    assert client.get("/api/catalog?limit=abc").status_code == 200
    assert client.post("/api/meds", json={"name": "X", "start": "yesterday"}).status_code == 400
    many = {"items": list(range(1, 13))}
    assert client.post("/api/interactions/check", json=many).status_code == 400


def test_login_lockout_after_repeated_failures(client):
    register(client)
    client.post("/api/auth/logout")
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "a@test.com", "password": "wrong"})
    r = client.post("/api/auth/login", json={"email": "a@test.com", "password": "secret123"})
    assert r.status_code == 429
