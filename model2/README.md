# MediSafe Model 2: alternative medicine comparison (+ MedEx data)

This folder contains six medicine-information CSV files (MedEx, Bangladesh) and
**Model 2** of the proposal: a content-based medicine comparison/ranking
component. The backend also imports `medicine.csv` and `generic.csv` from here.

**Model 1** (semi-supervised drug-interaction risk prediction) lives in
`../model1/`. It is trained on DDInter 2.0 because the files here have
interaction text but no labeled drug pairs.

**Notebook:** [`model2_alternative_medicine.ipynb`](model2_alternative_medicine.ipynb) covers Model 2 end to
end, with outputs saved:
- data and price formats;
- building the eligibility index;
- the eligibility correctness check (0 violations);
- hand-made test cases;
- listed price vs. price per unit (`price_units.py`);
- savings analysis;
- limitations.

## What this dataset can support

`medicine.csv` contains generic name, strength, dosage form, medicine type,
manufacturer, and package-price descriptions. `train.py` builds an exact-match
comparison index using generic, strength, dosage form, and type. It only groups
records with a listed price, then sorts matching products by the first price
amount in their package description.

This is a content-based comparison/ranking baseline, not a supervised ML model:
the CSVs do not contain user preferences or verified substitution labels.
Package sizes and price bases can differ, so inspect each package description
before comparing prices.

`generic.csv` includes free-text interaction descriptions, but no labeled drug
pairs and risk categories, so it cannot train the interaction-risk classifier.
That model is in `../model1/` and uses the DDInter 2.0 dataset (drug A, drug B,
severity level). The backend still shows the `generic.csv` interaction text as
"documented" evidence.

## Train/build the comparison index

The training script uses only Python's standard library:

```powershell
python train.py
```

It reports dataset coverage and writes
`models/alternative_recommendation.json`. The coverage counts describe how many
priced products can be grouped; they are not accuracy or clinical-safety
metrics.

## Query the index

For example:

```powershell
python predict.py --generic "Bromhexine Hydrochloride" --strength "4 mg/5 ml" --dosage-form "Syrup" --type allopathic
```

The result is a price comparison among products with the same normalized
generic, strength, dosage form, and medicine type. It is not a recommendation
to start, stop, or substitute a medicine. A doctor or pharmacist should verify
any medication change.

## Connect it to a website backend

The Flask API loads the JSON index once when the app starts and exposes:

`POST /api/medicine-comparisons`

Install Flask if it is not already installed:

```powershell
python -m pip install "Flask>=3.0,<4.0"
```

Start the standalone API:

```powershell
python model_api.py
```

Send a JSON request from your website backend:

```json
{
  "generic": "Bromhexine Hydrochloride",
  "strength": "4 mg/5 ml",
  "dosage_form": "Syrup",
  "type": "allopathic",
  "limit": 10
}
```

Example response fields are `count`, `comparisons`, and `disclaimer`. The
comparison records include brand, manufacturer, listed price, and package
details. The endpoint returns HTTP 400 for invalid input and an empty
`comparisons` list when no matching group is available.

To register the endpoint in an existing Flask application instead of starting
a separate server:

```python
from model_api import register_model_routes

register_model_routes(app)
```

By default, the API reads `models/alternative_recommendation.json` next to the
project scripts. Set `MEDISAFE_MODEL_PATH` before starting the app to use a
different model file. Restart the backend after rebuilding the index so it
loads the updated file.

## Step-by-step project workflow

1. Inspect and clean each CSV; confirm the data source and its permitted use.
2. Build the exact-match product index with `python train.py`.
3. Use `python predict.py` to compare matching products and review package
   details.
4. Connect the Flask endpoint to the website backend and test representative
   requests. Evaluate recommendation coverage; do not report
   classification accuracy for this rule-based baseline.
5. The interaction risk classifier is built in `../model1/` on DDInter 2.0.
   Keep unknown interactions marked unknown.
6. Present comparisons and future model outputs as decision support only, with
   evidence and professional-verification warnings.

The scripts do not diagnose conditions or determine whether a product is
clinically appropriate for an individual patient.
