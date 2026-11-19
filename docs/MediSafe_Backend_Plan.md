# MediSafe — Backend Design and Implementation Plan

| | |
|---|---|
| **Project** | MediSafe: An AI-Powered Personal Medical Record Management, Drug Interaction Risk Prediction, and Alternative Medicine Recommendation System |
| **Course** | SE3331 — Software Engineering Design Capstone Project (Fall 2026, Batch 41, Section F1) |
| **Course Teacher** | Rittik Chandra Das Turjy, Lecturer |
| **Backend Owner** | Siddhartho Sen (232-35-803) |
| **Team** | Monisha Debnath (232-35-241), Sadiya Khanom Kanta (232-35-771), Siddhartho Sen (232-35-803) |
| **Related document** | Project Proposal (submitted 11/10/2026) |

---

## 1. Purpose of This Document

This document is the detailed plan for the **application layer and data layer** of MediSafe, as described in Section 5.2 (System Architecture) of the proposal. It explains:

1. **What** the backend will contain: modules, database, APIs and AI integration.
2. **Why** each technology and design decision was chosen, and which alternatives were rejected.
3. **How** each functional requirement (FR), AI requirement (AIR) and non-functional requirement (NFR) in the proposal is met.
4. **When** each part will be delivered within the 8-week timeline.
5. **How** the backend will be tested and evaluated.

The backend lead (Siddhartho Sen) owns the Flask application, the MySQL schema, authentication, record management, file handling, and the API integration of both AI models (proposal Section 4.2, "Member 3"). The AI model owners provide trained models that plug into the interfaces defined in Section 8.

---

## 2. Backend Responsibilities

| Responsibility | Related proposal items |
|---|---|
| User registration, login, sessions, roles | FR-01, Security NFR |
| Patient medical profile, allergies, conditions | FR-02 |
| Prescription and report upload and storage | FR-03, Privacy NFR |
| Current and previous medication lists | FR-04, FR-05 |
| Medicine catalog and search | FR-06, Data Quality NFR |
| Serving Model 1 (interaction risk) through an API | FR-07, FR-08, AIR-01, AIR-06, AIR-08 |
| Drug–condition and drug–allergy safety rules | FR-09, FR-13 |
| Serving Model 2 (alternative medicines) through an API | FR-10, FR-11, FR-12, AIR-04, AIR-05, AIR-07 |
| Admin management of medicine data | FR-14 |
| Disclaimers on every AI output | FR-15, Explainability NFR |

**Out of scope for the backend** (matching proposal Section 1.4): OCR of reports, automatic diagnosis, prescription generation, pharmacy inventory or payment, and integration with hospital systems.

---

## 3. System Architecture

MediSafe follows the **three-layer architecture** stated in proposal Section 5.2. The backend covers the Application Layer and the Data and AI Layer.

```
┌──────────────────────────────────────────────────────────────┐
│ PRESENTATION LAYER  (HTML5, CSS3, JavaScript, Bootstrap)     │
│   index.html · auth.html · app.html · assets/js/api.js       │
└───────────────────────────────┬──────────────────────────────┘
                                │  HTTPS, JSON, session cookie
┌───────────────────────────────▼──────────────────────────────┐
│ APPLICATION LAYER  (Python, Flask)                           │
│                                                              │
│  API Blueprints ──► Validation (marshmallow) ──► Services    │
│  auth · user · records · meds · catalog · interactions ·     │
│  alternatives · notifications · admin                        │
│                                                              │
│  Services: safety_rules · interaction_service ·              │
│            recommendation_service · storage · audit          │
└──────────────┬─────────────────────────────┬─────────────────┘
               │ SQLAlchemy ORM              │ Python function calls
┌──────────────▼───────────────┐   ┌─────────▼─────────────────┐
│ DATA LAYER                   │   │ AI LAYER                  │
│  MySQL 8 (structured data)   │   │  Model 1: LabelSpreading  │
│  uploads/ (private files)    │   │   (interaction risk)      │
│                              │   │  Model 2: filter + rank   │
│                              │   │   (alternatives)          │
│                              │   │  artifacts/*.joblib       │
└──────────────────────────────┘   └───────────────────────────┘
```

**Why this architecture?**

- **It is required by the proposal.** Section 5.2 and the Maintainability NFR ask for the two AI models, backend services and medicine database to be "organized into separate modules".
- **The work can be split.** The three team members can develop the frontend, the backend and the models in parallel. They only need to agree on the API contract (Section 7) and the model interface (Section 8).
- **ML stays separate from verified knowledge.** Model predictions and verified safety rules live in separate modules. This makes it simple to label each result as *predicted*, *verified* or *unknown*, which FR-13 requires.
- **It is a monolith, not microservices.** A single Flask application is easier to build, test and demonstrate in 8 weeks. Microservices would add deployment and networking work with no benefit at this scale.

---

## 4. Technology Stack and Justification

### 4.1 Core stack (as stated in proposal Section 3)

| Component | Choice | Why we chose it | Alternatives considered |
|---|---|---|---|
| **Language** | Python 3.11+ | Both AI models are built with scikit-learn, Pandas and NumPy, which are Python libraries. Using one language for the backend and the ML lets the backend load trained models directly, with no separate ML server and no data conversion between languages. The whole team already knows Python. | **Node.js:** the models would need a separate Python service, adding a network call and a second runtime. **Java/Spring:** heavier, slower to develop in 8 weeks, and poor ML integration. |
| **Web framework** | Flask 3.x | A lightweight "micro" framework: we add only what we need. **Blueprints** map directly onto our feature modules (auth, records, meds, interactions…). It is easy to learn, well documented, and widely used to serve scikit-learn models. | **Django:** includes its own templates, admin and ORM, but much of it is unused because our frontend is already separate HTML/JS; it is also more opinionated and has a steeper learning curve. **FastAPI:** a strong option with async and auto docs, but it has fewer ready-made extensions for sessions and CSRF, and async gives no advantage for CPU-bound scikit-learn calls. |
| **Database** | MySQL 8.0 (InnoDB, utf8mb4) | Our data is highly **relational**: patients → medications → products → ingredients → interactions. A relational database enforces these links with foreign keys. InnoDB gives **ACID transactions**, so a failed save never leaves half-written medical data. `utf8mb4` supports Bangla text for future Bangla-language support (proposal 5.4). MySQL is free, taught in our curriculum, and supported by XAMPP and most hosts. | **MongoDB:** schema-less, but our data has a fixed structure and relies on joins, and medical data needs strict integrity. **PostgreSQL:** equally capable, but the team is more experienced with MySQL. **SQLite:** used for fast automated tests only, because it does not handle several users at once well. |
| **Data processing** | Pandas, NumPy | Used to clean, normalize and import the medicine catalog and interaction datasets, and to build feature vectors for Model 1. These are the standard tools for tabular data. | Plain Python loops: slower and harder to read. |
| **Machine learning** | scikit-learn | It provides `LabelSpreading` and `LabelPropagation` for semi-supervised learning (proposal 1.7.2), baseline classifiers, similarity functions for Model 2, and evaluation metrics, all through one consistent API. Trained models can be saved to a file and loaded by Flask. | **PyTorch/TensorFlow:** built for deep learning on large datasets; too heavy for a few thousand tabular drug pairs and harder to explain to evaluators. |
| **Model evaluation** | scikit-learn metrics, Matplotlib, Seaborn | Precision, recall, F1 and confusion matrices as required by AIR-03; plots for the evaluation report. | — |
| **Data collection** | Requests, BeautifulSoup | Used only if MedEx's terms and robots.txt allow it (proposal 3.2). Otherwise we use a manually curated CSV file. | Selenium: only needed for JavaScript-heavy sites, and heavier. |
| **Testing** | Pytest + Flask test client | Pytest fixtures give a clean database for each test; the Flask test client calls APIs without starting a server. | unittest: more boilerplate code. |
| **Version control** | Git + GitHub | Branches for each member, pull requests for code review (proposal 4.2 "code review"). | — |

### 4.2 Supporting libraries (added by the backend lead)

The proposal names the main frameworks. The libraries below are small, widely used Flask extensions chosen to meet the proposal's **Security, Privacy, Reliability and Maintainability NFRs** without writing security-sensitive code from scratch.

| Library | Purpose | Why we chose it (NFR satisfied) |
|---|---|---|
| **Flask-SQLAlchemy** | ORM (object-relational mapper) | Database tables become Python classes. Queries are parameterized automatically, which **prevents SQL injection** (Security). Code is shorter and easier to maintain than raw SQL. |
| **PyMySQL** | MySQL driver | Pure-Python driver; installs on Windows and Linux without compiling, which avoids setup problems across team laptops. |
| **Flask-Migrate (Alembic)** | Database schema migrations | Every schema change is a versioned script kept in Git, so all three members' databases stay identical (Maintainability, Scalability). |
| **Flask-Login** | Session management | Handles login state, `@login_required`, and loading the current user. Well tested; we do not write session logic ourselves (Security). |
| **Werkzeug security** (included with Flask) | Password hashing | Stores only a salted hash (scrypt/PBKDF2), never the plain password (Security). |
| **Flask-WTF (CSRFProtect)** | CSRF protection | Because we use cookie sessions, CSRF tokens stop other websites from sending requests on a logged-in user's behalf (Security). |
| **marshmallow** | Input validation and output formatting | Every request body is checked (types, required fields, date formats, lengths) before it reaches business logic, and invalid input returns a clear 400 error (Reliability NFR: "validate inputs and handle missing, invalid, or unsupported medication information"). |
| **Flask-Limiter** | Rate limiting | Limits login and registration attempts, for example 5 per minute, to slow down password guessing (Security). |
| **joblib** | Model saving and loading | The standard way to save scikit-learn models. The model is loaded once at startup, so predictions are fast (Performance NFR: under 5 s). |
| **rapidfuzz** | Fuzzy string matching | Users type medicine names with spelling variations ("Napa" vs. "NAPA 500"). Fuzzy matching finds the correct catalog product, and unmatched names are reported as unsupported (AIR-08). |
| **python-dotenv** | Configuration | Database passwords and secret keys are kept in a `.env` file that is not committed to Git (Security). |

### 4.3 Why session cookies instead of JWT tokens?

The frontend and the API are served from the **same origin** (Flask serves the static HTML), so a browser session cookie is the simplest secure option:

- The cookie is `HttpOnly`, so JavaScript cannot read it. This protects against token theft through XSS.
- With JWT stored in `localStorage`, any XSS bug would expose the token. Logout and token revocation also need extra work with JWT.

JWT would make sense only if a separate mobile app were added. That is listed as future work.

---

## 5. Project Folder Structure

```
medisafe/
├── index.html, auth.html, app.html, assets/     # existing frontend
├── docs/                                        # this plan, reports
└── backend/
    ├── app/
    │   ├── __init__.py           # create_app(): app factory
    │   ├── config.py             # DevConfig, TestConfig, ProdConfig
    │   ├── extensions.py         # db, migrate, login_manager, csrf, limiter
    │   ├── models/               # SQLAlchemy models
    │   │   ├── user.py           # User, PatientProfile, Allergy, Condition
    │   │   ├── record.py         # Document, PatientMedication
    │   │   ├── catalog.py        # Ingredient, Product, ProductIngredient
    │   │   ├── knowledge.py      # DdiKnown, ConditionTerm, Contraindication
    │   │   └── activity.py       # InteractionCheck, Notification, AuditLog
    │   ├── schemas/              # marshmallow schemas (validation)
    │   ├── api/                  # Flask Blueprints (HTTP layer only)
    │   │   ├── auth.py  user.py  records.py  meds.py  catalog.py
    │   │   ├── interactions.py  alternatives.py  notifications.py
    │   │   └── admin.py
    │   ├── services/             # business logic (no HTTP code here)
    │   │   ├── interaction_service.py
    │   │   ├── recommendation_service.py
    │   │   ├── safety_rules.py
    │   │   ├── normalization.py  # strength/unit/name normalization
    │   │   ├── storage.py        # secure file save/serve
    │   │   └── audit.py
    │   ├── ai/
    │   │   ├── registry.py       # loads model artifacts once at startup
    │   │   ├── interaction/      # Model 1: features.py, predict.py
    │   │   └── recommendation/   # Model 2: eligibility.py, rank.py
    │   └── utils/                # decorators (role_required), errors
    ├── ml/                       # notebooks, train.py, evaluate.py, reports
    ├── data/                     # seed CSVs: catalog, DDI, contraindications
    ├── artifacts/                # interaction_model.joblib + metadata.json
    ├── uploads/                  # private files (not public, git-ignored)
    ├── migrations/               # Alembic scripts
    ├── tests/                    # unit/, api/, ml/
    ├── requirements.txt
    ├── .env.example
    └── run.py
```

**Why this layout?**

- **Blueprints → Services → Models** is a layered design that separates concerns. API files only handle HTTP (parse the request, return JSON). Services hold the rules and can be unit-tested without a web server. Models only describe data.
- **The `ai/` package is separate from `ml/`.**
  - `ml/` is where models are *trained*: notebooks and experiments, owned by the AI model members.
  - `ai/` is where trained models are *used* in production, owned by the backend lead.
  - The only link between them is the saved artifact file plus `metadata.json`. Retraining a model therefore never requires changing backend code (Scalability NFR).
- **The app factory (`create_app`)** lets tests start the app with a separate test database.

---

## 6. Database Design

### 6.1 Entity overview

```
users 1──1 patient_profiles
users 1──* allergies          *──1 ingredients (optional link)
users 1──* conditions         *──1 condition_terms (optional link)
users 1──* documents
users 1──* patient_medications *──1 products
products *──* ingredients  (via product_ingredients)
ingredients *──* ingredients (via ddi_known: verified interactions)
ingredients *──* condition_terms (via contraindications)
users 1──* interaction_checks 1──* interaction_results
users 1──* notifications
users 1──* audit_log
```

### 6.2 Tables

**A. Users and medical records**

| Table | Key columns | Notes |
|---|---|---|
| `users` | id PK, name, email UNIQUE, password_hash, role ENUM('patient','admin'), created_at, last_login | Role-based access control |
| `patient_profiles` | user_id PK/FK, phone, dob, gender, blood_group, height_cm, weight_kg, ec_name, ec_phone | One-to-one with users (FR-02) |
| `allergies` | id, user_id FK, substance, ingredient_id FK NULL, reaction, severity | `ingredient_id` lets the rule engine match allergies exactly |
| `conditions` | id, user_id FK, name, condition_term_id FK NULL, diagnosed_on, status | Entered by the user, linked to a standard term when possible |
| `documents` | id, user_id FK, title, category ENUM('Prescription','Report','Other'), record_date, stored_name, original_name, mime_type, size_bytes, sha256, note, created_at | Only metadata is stored in the database; the file itself is on disk (proposal Section 3: "controlled file storage with database metadata") |
| `patient_medications` | id, user_id FK, product_id FK NULL, free_text_name, dose, frequency, start_date, end_date, status ENUM('Current','Previous') | Rows are never deleted when a medicine is stopped; status changes to "Previous" and `end_date` is set. This keeps the medication history required by FR-05. |

**B. Medicine catalog (Bangladesh market)**

| Table | Key columns | Notes |
|---|---|---|
| `ingredients` | id, name UNIQUE (normalized, lower-case), synonyms JSON, atc_code NULL | Generic or active ingredient |
| `products` | id, brand_name, manufacturer, dosage_form, strength_text, price_bdt, pack_size, unit_price_bdt, source, source_url, last_updated, is_active | `source` and `last_updated` meet the Data Quality NFR |
| `product_ingredients` | product_id FK, ingredient_id FK, strength_value DECIMAL, strength_unit | Supports **combination drugs** (for example paracetamol + caffeine). Strength is stored per ingredient in a normalized unit (mg, mcg, ml, IU). |

**C. Knowledge base and AI results**

| Table | Key columns | Notes |
|---|---|---|
| `ddi_known` | ingredient_a_id, ingredient_b_id (a < b), severity, description, source | **Verified** interactions. Storing each pair with the smaller ID first means one row covers both A+B and B+A. |
| `condition_terms` | id, name, synonyms JSON | Small controlled list of medical conditions |
| `contraindications` | ingredient_id, condition_term_id, severity, warning_text, source | Verified drug–condition warnings (FR-09) |
| `interaction_checks` | id, user_id, created_at, model_version | History of checks; records which model version produced each result |
| `interaction_results` | id, check_id FK, ingredient_a, ingredient_b, basis ENUM('verified','predicted','unknown'), category, confidence | Supports the evaluation and audit of AI outputs |
| `notifications` | id, user_id, type, title, body, is_read, created_at | For example, a warning after a high-risk check |
| `audit_log` | id, user_id, action, entity, entity_id, created_at | Tracks who changed what; also feeds the dashboard activity list |

### 6.3 Design decisions

- **Third Normal Form (3NF).**
  - Ingredients are stored once and linked to products, so a spelling fix or interaction update applies everywhere.
  - Prices belong to products, not to patients' medications.
- **Ingredient-level interactions.** Drug interactions are caused by active ingredients, not brand names. Checking at ingredient level means a single verified rule covers *every* brand that contains that ingredient. This is essential for the Bangladesh market, which has many brands per generic.
- **Free text is allowed but flagged.** A patient may take a medicine that is not in our catalog. It is stored as `free_text_name` with `product_id = NULL`, and the interaction checker reports it as "unsupported" instead of guessing (AIR-08).
- **Indexes** on `products.brand_name`, `ingredients.name`, and every `user_id` foreign key keep searches and per-user queries fast (Performance NFR).
- **ON DELETE CASCADE** from `users` to all patient tables means that deleting an account removes all of that user's private data (Privacy).

---

## 7. REST API Specification

### 7.1 Conventions

- **Base path:** `/api`. All bodies are JSON, except file uploads, which use `multipart/form-data`.
- **Authentication:** session cookie. Every endpoint except register and login requires a logged-in user.
- **Ownership rule:** every patient-data query is filtered by `current_user.id`. If a user asks for a record they do not own, the API returns **404** (not 403), so it does not even reveal that the record exists.
- **Error format** (same for every error):
  ```json
  { "error": { "code": "VALIDATION_ERROR", "message": "start_date is required", "fields": {"start_date": ["Missing data"]} } }
  ```
- **HTTP status codes:**

  | Code | Meaning |
  |---|---|
  | 200 / 201 | Success / created |
  | 400 | Invalid input |
  | 401 | Not logged in |
  | 403 | Not an admin |
  | 404 | Not found or not owned |
  | 413 | File too large |
  | 429 | Too many requests |
  | 500 | Server error, logged; no internal details are sent to the client |

### 7.2 Endpoints

| Method & Path | Description | Req. |
|---|---|---|
| `POST /api/auth/register` | Create a patient account | FR-01 |
| `POST /api/auth/login` | Log in (rate limited) | FR-01 |
| `POST /api/auth/logout` | Log out | FR-01 |
| `GET /api/auth/me` | Current user | FR-01 |
| `POST /api/auth/change-password` | Change password | FR-01 |
| `GET /api/user` · `PUT /api/user` | View or update medical profile, allergies, conditions | FR-02 |
| `GET /api/records` · `POST /api/records` | List or upload documents | FR-03 |
| `GET/PUT/DELETE /api/records/<id>` | View, edit or delete a document | FR-03 |
| `GET /api/records/<id>/file` | Download the file (owner only) | FR-03 |
| `GET /api/meds?status=Current\|Previous` | Medication list or history | FR-04, FR-05 |
| `POST /api/meds` · `PUT/DELETE /api/meds/<id>` | Add, update or remove a medication | FR-04 |
| `GET /api/catalog?q=&ingredient=&strength=&form=&page=` | Search medicines (paginated) | FR-06 |
| `POST /api/interactions/check` | Model 1 + safety rules | FR-07, 08, 09, 13, 15 |
| `GET /api/alternatives/<product_id>` | Model 2 ranked alternatives | FR-10, 11, 12, 15 |
| `GET /api/notifications` · `POST /api/notifications/<id>/read` | Notifications | — |
| `GET /api/activity` | Recent activity for the dashboard | — |
| `GET/POST/PUT/DELETE /api/admin/products` | Manage products and prices | FR-14 |
| `GET/POST/PUT/DELETE /api/admin/ingredients` | Manage ingredients | FR-14 |
| `POST /api/admin/import` | Bulk CSV import of the catalog | FR-14 |
| `GET/POST/DELETE /api/admin/ddi`, `/api/admin/contraindications` | Manage verified safety knowledge | FR-14 |

### 7.3 Example: interaction check

Request:
```json
POST /api/interactions/check
{ "items": [ {"product_id": 12}, {"name": "napa extra"} ], "include_current_meds": true }
```

Response:
```json
{
  "connected": true,
  "model_version": "ddi-labelspreading-1.0",
  "pairs": [
    {
      "a": "Warfarin", "b": "Aspirin",
      "basis": "verified",
      "category": "major",
      "verified": [{"severity": "major", "text": "Increased bleeding risk", "source": "DDInter"}],
      "predicted": null
    },
    {
      "a": "Omeprazole", "b": "Paracetamol",
      "basis": "predicted",
      "category": "minor",
      "predicted": {"category": "minor", "confidence": 0.74, "factors": ["similar pairs in training data are mostly minor"]},
      "verified": []
    },
    {
      "a": "Ingredient X", "b": "Paracetamol",
      "basis": "unknown",
      "category": "unknown",
      "message": "Not enough information. This does not mean the combination is safe."
    }
  ],
  "condition_warnings": [{"ingredient": "Ibuprofen", "condition": "Peptic ulcer", "severity": "major", "source": "..."}],
  "allergy_warnings": [],
  "unsupported": [{"input": "xyz syrup", "reason": "Not found in medicine database"}],
  "disclaimer": "MediSafe provides decision support only. Consult a doctor or pharmacist before starting, stopping or changing any medicine."
}
```

This response format matches what the existing frontend (`assets/js/api.js`) already expects: `connected`, and `pairs[]` with `a`, `b`, `category`, `predicted` and `verified`. Moving from mock data to the real backend therefore needs changes only in `api.js`.

---

## 8. AI Integration Design

### 8.1 Model interface (contract between ML members and backend)

Each model is delivered as an artifact file plus metadata. The backend calls it only through these functions:

```python
# ai/interaction/predict.py
def predict_pair(ingredient_a: str, ingredient_b: str) -> dict | None:
    """Returns {"category": str, "confidence": float, "factors": list[str]}
       or None if either ingredient is outside the model's vocabulary."""

# ai/recommendation/rank.py
def recommend(product_id: int, patient_id: int | None) -> list[dict]:
    """Returns ranked eligible alternatives with price data and reasons."""
```

`metadata.json` contains the model version, training date, label set, vocabulary, confidence threshold, and test metrics. `ai/registry.py` loads it **once at application startup** rather than on every request, which keeps responses well under the 5-second Performance NFR.

**Why a fixed interface?** Members 1 and 2 can retrain or improve their models in `ml/` independently. As long as the function signature stays the same, the backend does not change.

### 8.2 Interaction check pipeline (FR-07, FR-08, FR-09, FR-13)

```
Input medicines + patient's current medicines
        │
        ▼
1. Resolve names → products → ingredients   (rapidfuzz; unmatched → "unsupported")
        │
        ▼
2. Build all ingredient pairs
        │
        ▼
3. For each pair:
     ├─ Found in ddi_known?        → basis = "verified"   (trusted source first)
     ├─ Else model returns result
     │    with confidence ≥ 0.60?  → basis = "predicted"
     └─ Else                       → basis = "unknown"    (never "safe")
        │
        ▼
4. Safety rules: each ingredient vs patient's conditions (contraindications)
                 and allergies (ingredient + synonym match)
        │
        ▼
5. Save check + results, create notification if any major/moderate result
        │
        ▼
6. Return JSON with basis labels, sources, and disclaimer
```

**Why does verified knowledge come before the ML model?** The proposal (Sections 1.6 and 5.3) states that the system must "separate ML predictions from verified safety rules". A documented interaction is stronger evidence than a prediction, so the model is used only to fill gaps where no verified data exists.

**Why a confidence threshold?** AIR-06 says the system "shall not classify an unknown interaction as safe merely because the model has insufficient information". Low-confidence predictions are reported as "unknown" instead of guessed. The threshold (starting at 0.60) will be tuned on the validation set in Week 7.

### 8.3 Model 1 — Drug Interaction Risk Prediction (semi-supervised)

*The model is built by the Model 1 owner. The backend lead integrates it and checks it against these specifications.*

| Item | Plan | Reason |
|---|---|---|
| Dataset | A drug-pair dataset with severity labels, such as DDInter (Major / Moderate / Minor / Unknown); the licence is checked in Week 1 | Severity labels match the proposal's risk categories |
| Labeled data | Pairs with a known severity | — |
| Unlabeled data | Pairs with unknown severity (label `-1`) | This is the reason to use semi-supervised learning: there are many more known pairs than known severities |
| Features | Per ingredient: ATC therapeutic class, plus target/enzyme information if available. Pair vector = `[f_a + f_b, |f_a − f_b|]` | Symmetric: (A, B) gives the same result as (B, A) |
| Algorithm | `sklearn.semi_supervised.LabelSpreading(kernel="knn")` | Named in the proposal (1.7.2). The kNN kernel scales to thousands of pairs, and LabelSpreading is more robust to noisy labels than LabelPropagation |
| Baseline | Logistic Regression or Random Forest trained on labeled data only | The proposal (3.1) requires comparison with a simple baseline; this shows whether unlabeled data actually helps |
| Evaluation | Held-out labeled test set (never used during training); precision, recall, F1 per class, macro-F1, confusion matrix | AIR-03. **Recall on the "major" class** is the main metric, because missing a dangerous interaction is worse than a false alarm |
| Fallback | If the data does not support reliable semi-supervised learning, the model design is revised and documented | As stated in proposal 3.1 |

**Implementation status (20 Nov 2026).** Model 1 is built in `model1/` on DDInter 2.0. The dataset has 160,235 unique pairs: 130,422 labeled and 29,813 Unknown (unlabeled).

- **Features.** ATC class was not available per drug, so the pair features come from the interaction network instead: an SVD drug embedding plus leave-one-out drug risk profiles.
- **Results.** On the held-out test set (19,564 pairs), LabelSpreading (k = 10, alpha = 0.1, high-class weight 2.0) reaches:
  - accuracy 0.927, macro-F1 0.881, **high-class recall 0.922**;
  - the Logistic Regression baseline: macro-F1 0.713, high-class recall 0.846;
  - majority class: macro-F1 0.284.
- **Model selection.** Settings are chosen on the val set: the highest high-class recall among those within 0.01 of the best macro-F1. This follows the "recall on the major class" rule above.
- **Calibration.** Confidence scores are checked on the val set, with test ECE 0.022.
- **Value of unlabeled data.** With only 5 % of the labels, LabelSpreading still scores 0.691 macro-F1, against 0.586 for Logistic Regression.
- **Integration.** The backend reads precomputed predictions for the Unknown pairs (`interaction_adapter.py`). Known DDInter levels are imported as verified rows.

Full details and limitations are in `model1/README.md`.

### 8.4 Model 2 — Alternative Medicine Recommendation

| Step | Logic | Requirement |
|---|---|---|
| 1. Eligibility filter (**hard constraint**) | Same set of active ingredients, same normalized strength for each ingredient, same dosage form, product is active | AIR-04 |
| 2. Safety re-check | Remove candidates that match a patient's allergy or contraindication | FR-09 |
| 3. Ranking (only after the filter) | `score = 0.6 × price_saving + 0.25 × feature_similarity + 0.15 × data_freshness` | AIR-05: price never overrides eligibility |
| 4. Explanation | Each item includes `reasons[]`, e.g. "Same ingredient (Paracetamol 500 mg), same form (Tablet), 17% cheaper per unit", plus the source and last-updated date | FR-12, AIR-07 |

**Why a transparent weighted score instead of a trained recommender?** The proposal (3.1) notes that "if suitable training labels are unavailable, the initial implementation will use a clearly defined ranking algorithm". We have no history of user preferences to train on. A rule-based score is honest, explainable and easy to test. The weights are stored in configuration so they can be adjusted.

**Why is price compared per unit?** Pack sizes differ (10 tablets vs. 30 tablets). Comparing pack prices would be misleading, so `unit_price_bdt = price_bdt / pack_size` is used.

---

## 9. Security and Privacy Design

Medical data is sensitive (proposal 5.3). The measures below meet the Security and Privacy NFRs.

| Threat | Countermeasure |
|---|---|
| Password theft from the database | Salted password hashing (Werkzeug scrypt); plain passwords are never stored or logged |
| Brute-force login | Flask-Limiter: 5 attempts/minute per IP; the error message is the same for a wrong email and a wrong password |
| Session hijacking | `HttpOnly`, `SameSite=Lax`, and `Secure` (in production) cookies; the session is regenerated on login |
| CSRF | Flask-WTF CSRF token required on all POST/PUT/DELETE requests |
| SQL injection | Only ORM / parameterized queries; no SQL built from strings |
| Accessing another patient's data (IDOR) | One shared helper, `get_owned_or_404(Model, id)`, used for every patient resource; tested explicitly |
| Malicious file upload | Only PDF, JPG and PNG are allowed (checked by extension **and** file signature); 10 MB limit; random stored filename; stored outside public folders; downloaded only through an authenticated endpoint with `Content-Disposition: attachment` |
| Admin abuse | `@role_required("admin")` decorator; all admin changes are written to `audit_log` |
| Secret leakage | `SECRET_KEY` and the database password are kept in `.env` (git-ignored); `.env.example` has placeholders only |
| Real patient data in development | Only synthetic demo users (`flask seed-demo`), as stated in proposal 3.2; private records are never used for model training |

---

## 10. Data Collection and Import

1. **Catalog source.** MedEx Bangladesh is the preferred source (proposal 3.2), but only if its robots.txt and terms of use allow it. Otherwise, a manually curated CSV of about 200–500 commonly used medicines is built from permitted sources.
2. **Import command.** `flask import-catalog data/catalog.csv`:
   - Pandas cleans the data: trims spaces, lower-cases ingredient names, and splits combination products.
   - Strength is normalized to a value and unit (`"500mg"` → `500, mg`; `"1 g"` → `1000, mg`).
   - The cleaned data is inserted into `ingredients`, `products` and `product_ingredients`, with `source` and `last_updated` set.
   - The command reports the number of rows imported, skipped and failed.
3. **Safety knowledge.** `data/ddi_known.csv` and `data/contraindications.csv` are curated by the team, with a source for every row.
4. **Demo data.** `flask seed-demo` creates synthetic patients, records and medications for testing and the final presentation.

**Why a CLI import instead of entering data through the admin screen?** Hundreds of products cannot be entered by hand. A repeatable script means any team member can rebuild the database from the CSV files in seconds.

---

## 11. Testing Strategy

| Level | What is tested | Tool |
|---|---|---|
| **Unit** | Strength normalization; the eligibility filter (must reject different strength or form); ranking order; the safety rule engine; the confidence threshold mapping low confidence to "unknown"; that no code path returns "safe" for an unknown pair | Pytest |
| **API / integration** | Register → login → profile → add medication → interaction check → alternatives; validation errors return 400; unauthenticated requests return 401 | Pytest + Flask test client + test database |
| **Security** | User A cannot read, edit or download user B's records or medications (returns 404); a non-admin cannot reach `/api/admin/*` (returns 403); `.exe` and oversized uploads are rejected; login rate limit returns 429 | Pytest |
| **Model** | Model 1 classification report and confusion matrix vs. the baseline on the held-out set; Model 2 checked on hand-made cases with known correct alternatives | `ml/evaluate.py`, Seaborn |
| **Performance** | Interaction check with 5 medicines and the alternatives request each finish in under 5 seconds on the demo dataset | Pytest timing test |
| **Manual / acceptance** | Full user workflow through the real frontend, using the proposal's 9-step system workflow (Section 1.6) as the test script | Manual checklist |

Target: **at least 80% line coverage** on `services/` and `ai/` (measured with `pytest-cov`).

---

## 12. Requirements Traceability Matrix

| Req. | Backend implementation | Verified by |
|---|---|---|
| FR-01 | `api/auth.py`, Flask-Login, Werkzeug hashing | API tests: auth flow |
| FR-02 | `api/user.py`, `patient_profiles`, `allergies`, `conditions` | API tests |
| FR-03 | `api/records.py`, `services/storage.py`, `documents` | Upload and download tests |
| FR-04 | `api/meds.py`, `patient_medications` | API tests |
| FR-05 | Status and dates on `patient_medications` (no deletion when stopped) | History test |
| FR-06 | `api/catalog.py`, indexed search | Search tests |
| FR-07 | `services/interaction_service.py` → `ai/interaction` | Pipeline unit tests |
| FR-08 | `pairs[]` with category, confidence, factors | API test |
| FR-09 | `services/safety_rules.py`, `contraindications`, `allergies` | Rule unit tests |
| FR-10 | `ai/recommendation/eligibility.py` | Eligibility tests |
| FR-11 | Unit price and price difference in `/alternatives` | API test |
| FR-12 | `reasons[]` in each alternative | API test |
| FR-13 | `basis`: verified / predicted / unknown | Unit test |
| FR-14 | `api/admin.py`, `role_required`, CSV import | Admin API tests |
| FR-15 | `disclaimer` field on every AI response | API test |
| AIR-01 | `predict_pair()` interface | Unit test |
| AIR-03 | `ml/evaluate.py` held-out evaluation | Evaluation report |
| AIR-04 | Hard eligibility filter before ranking | Unit test |
| AIR-05 | Ranking runs only on filtered candidates | Unit test |
| AIR-06 | Confidence threshold → "unknown", never "safe" | Unit test |
| AIR-07 | `factors[]`, `reasons[]`, `source` fields | API test |
| AIR-08 | Out-of-vocabulary and unmatched names → `unsupported` with a message | Unit test |
| Security / Privacy NFR | Section 9 measures | Security tests |
| Performance NFR | Models loaded once, database indexes | Timing test |
| Maintainability NFR | Blueprints / services / ai modules, migrations | Code review |
| Data Quality NFR | `source` and `last_updated` on products, normalization | Import report |

---

## 13. Backend Timeline (aligned with proposal Section 4.1)

| Week | Backend tasks (Siddhartho Sen) | Deliverable |
|---|---|---|
| 1 | Finalize API contract with frontend; agree model interface with Model 1 and 2 owners; check dataset licences | API contract (Section 7), interface spec (Section 8.1) |
| 2 | Project skeleton, app factory, config, MySQL schema + first migration, seed CSV format | Running empty app, ER diagram, migrations |
| 3 | Catalog import command, normalization service, catalog search API; support Model 1 owner with feature data from the database | Searchable medicine catalog |
| 4 | Eligibility and ranking service (with the Model 2 owner); `ddi_known` and contraindication import | Model 2 working in Python |
| 5 | Auth, profile, records (upload), medications, notifications APIs; connect `api.js` to real endpoints | Working core web app (proposal W5 milestone) |
| 6 | `/interactions/check` pipeline, safety rules, `/alternatives`, admin APIs, model registry | Both AI models integrated (proposal W6 milestone) |
| 7 | Unit, API, security and performance tests; tune confidence threshold; bug fixes | Test report, coverage report |
| 8 | Code cleanup, README and setup guide, API documentation, demo seed data, presentation support | Final backend, documentation |

---

## 14. Risks and Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| MedEx scraping not permitted | No price data | Manually curated CSV of common medicines (proposal 3.2) |
| Interaction dataset has few severity labels | Model 1 performs poorly | Compare with the baseline; rely more on verified `ddi_known`; report results honestly (proposal 3.1) |
| Ingredient names differ between catalog and DDI dataset | Many "unknown" results | Synonym table + rapidfuzz matching; mapping report generated during import |
| API contract changes late | Frontend and backend mismatch | Contract fixed in Week 1; changes only through a GitHub pull request reviewed by all members |
| Different database states on each laptop | "Works on my machine" bugs | Alembic migrations + seed commands; same `.env.example` |
| Model loading slows responses | Breaks the 5 s NFR | Load once at startup; cache catalog lookups |

---

## 15. Setup and Run (for evaluators)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # set DATABASE_URL, SECRET_KEY
flask db upgrade                                     # create tables
flask import-catalog data/catalog.csv
flask seed-demo                                      # synthetic demo users
flask run                                            # http://127.0.0.1:5000
pytest --cov=app                                     # run tests
```

Demo login details are printed by `flask seed-demo`. All demo data is synthetic.

---

## 16. Limitations

- The safety knowledge base covers only the medicines and conditions the team has curated; coverage of the Bangladesh market will be partial.
- Model 1 predictions depend on the quality and coverage of the public dataset and may not represent all local medicines (proposal 5.3, "Model Bias").
- Uploaded reports are stored, but their content is not read automatically (OCR is future work).
- The system is a decision-support prototype. It does not diagnose, prescribe, or replace a doctor or pharmacist.
