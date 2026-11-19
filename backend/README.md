# MediSafe Backend

## চালানোর নিয়ম
```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# (একবার) Model 1-এর dataset ও model: cd ../model1 && python download_ddi.py && python train_interaction.py
.venv/bin/python run.py                   # Starts MediSafe server on http://127.0.0.1:5000
.venv/bin/pytest -q                       # ১৭টা unit test
```
Browser-এ http://127.0.0.1:5000 খুলুন → Register → Dashboard।

## Dataset → database
| ফাইল | Database টেবিল | কেন |
|---|---|---|
| `medicine.csv` (২১,৭১৪ সারি) | `product` (২১,৭১২টি; নাম বা generic ফাঁকা থাকা ২টা বাদ) | Search, interaction checker, বিকল্প ওষুধ |
| `generic.csv` (১,৭১১) | `generic` | Drug class, indication, interaction ও contraindication-এর বর্ণনা (HTML বাদ দিয়ে) |
| manufacturer / dosage form / drug class / indication.csv | — | শুধু নামের তালিকা; নামগুলো উপরের দুই টেবিলেই আছে |
| `model1/data/ddinter/*.csv` (DDInter 2.0) | `known_interaction` | Major/Moderate/Minor pair = Verified warning। নাম মেলানো হয় `model1/drug_names.py` দিয়ে (Paracetamol → Acetaminophen) |

CSV ফোল্ডার: `model2/` (Model 2 + MedEx data)। DDInter ও Model 1: `model1/`।

## Model সংযোগ
- **Model 2** (`model2/`): দাম-তুলনা model (`train.py` → `models/alternative_recommendation.json`), যুক্ত `app/ai/model2_adapter.py` দিয়ে।
- API: `GET /api/alternatives/<product_id>`। একই generic, strength, dosage form আর type মিলিয়ে কম দামের ওষুধ আগে দেখায়।
- Model আবার train করলে (`cd model2 && python train.py`) শুধু server restart দিন।
- **Model 1** (`model1/`): semi-supervised interaction risk model (LabelSpreading, DDInter 2.0)। `train_interaction.py` DDInter-এর "Unknown" pair-গুলোর prediction `models/interaction_risk_model.json`-এ লেখে; `app/ai/interaction_adapter.py` শুধু ওই JSON পড়ে (backend-এ scikit-learn লাগে না) আর `set_predictor()` দিয়ে লাগে। JSON না থাকলে `connected = false`।
- Checker-এর ক্রম: Verified (DDInter-এর জানা severity) → Predicted (model, confidence ≥ 0.6) + Documented (generic.csv monograph) → Unknown। কখনো "safe" বলা হয় না।
- `GET /api/model-info`: দুই model-এর বিবরণ ও Model 1-এর test metrics।
- Model 2-এর দাম: package-এর আকার আলাদা হতে পারে (60 ml বনাম 100 ml), তাই backend প্রতি একক (tablet/capsule, ml, gm, dose) দাম বের করে (`model2_adapter.normalized_price`) আর একই এককের মধ্যেই তুলনা ও ranking করে। একক না মিললে "different unit" দেখায়।

## Safety screening (rule-based, ML নয়)
- `app/safety.py`: রোগীর profile-এর allergy বনাম ওষুধের উপাদান, drug class আর একটা ছোট allergy-group তালিকা (যেমন penicillin → amoxicillin); রোগীর condition বনাম `generic.csv`-এর contraindication লেখা (প্রতিশব্দসহ, যেমন kidney → renal)। Keyword screening, সম্পূর্ণ নয়।
- একই active ingredient দুই ওষুধে থাকলে `duplicate` (dose দ্বিগুণের ঝুঁকি)।
- নতুন ওষুধ যোগ বা বদলালে (Current হলে) বাকি current ওষুধ আর allergy/condition-এর সাথে নিজে থেকে check হয়; ঝুঁকি পেলে Notification তৈরি হয় (proposal workflow step 4)।

## Security
- `SECRET_KEY` env-এ না দিলে `instance/secret_key`-এ random key তৈরি হয় (কোডে লেখা key নেই)।
- Login: একই IP + email থেকে ১৫ মিনিটে ৫ বার ভুল হলে 429। Session ৮ ঘণ্টা; HTTPS-এ `SESSION_COOKIE_SECURE=1`।
- Debugger শুধু `FLASK_DEBUG=1` দিলে চালু।
- Password: ৮+ অক্ষর, অক্ষর ও সংখ্যা দুটোই (frontend-এর নিয়মের সাথে এক)।
- Upload: extension ছাড়াও ফাইলের ভেতরের signature (PDF/PNG/JPG) যাচাই; সব input-এ দৈর্ঘ্য, তারিখ, সংখ্যার সীমা যাচাই (ভুল হলে 400, 500 নয়)।

## ফাইল
| ফাইল | কাজ |
|---|---|
| `app/__init__.py` | App factory, blueprint register, frontend serve |
| `app/config.py` | সেটিং: `DATABASE_URL`, `MODEL1_DIR`, `MODEL2_DIR`, upload folder |
| `app/models.py` | টেবিল: User, Record, Medication, Product, Generic, KnownInteraction, Notification, Activity |
| `app/seed.py` | `import-data` command (CSV + DDInter → database) |
| `app/ai/model2_adapter.py` | Model 2 (দাম-তুলনা)-র সাথে সংযোগ |
| `app/ai/interaction_adapter.py` | Model 1 (interaction risk)-এর সাথে সংযোগ |
| `app/auth.py` | Register, login, logout, password বদল |
| `app/routes.py` | Profile, records, medications, catalog search, alternatives, model-info |
| `app/interactions.py` | Interaction check (duplicate → verified → predicted + documented → unknown) + নতুন ওষুধের auto-check |
| `app/safety.py` | Allergy ও condition screening (rule-based) |
| `tests/test_api.py` | ১৭টা test; ছোট CSV দিয়ে আসল import আর আসল `train.py` চালায়; Model 1-এর জন্য ছোট কাল্পনিক DDInter ফাইল ও model JSON |
