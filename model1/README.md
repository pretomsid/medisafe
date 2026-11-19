# MediSafe Model 1: drug interaction risk prediction (semi-supervised)

Proposal objective 2 / AI Model 1: classify a drug pair into a risk category using
**labeled and unlabeled** drug-interaction data with semi-supervised learning
(Label Spreading).

**Notebook:** [`model1_interaction_risk.ipynb`](model1_interaction_risk.ipynb) runs the whole pipeline step by
step, with outputs saved:
- data and EDA;
- name matching;
- features;
- tuning;
- test evaluation and baselines;
- calibration;
- the label-fraction experiment;
- the final predictions.

It uses the same functions as `train_interaction.py`.

## Dataset: DDInter 2.0

| | |
|---|---|
| Source | https://ddinter2.scbdd.com/download/ (8 CSV files, one per ATC group A, B, D, H, L, P, R, V) |
| Paper | Tian Y. et al., *DDInter 2.0*, Nucleic Acids Research 53(D1):D1356, 2025. doi:10.1093/nar/gkae1004 |
| License | CC BY-NC-SA 4.0 (non-commercial, attribution, share-alike) |
| Columns | `DDInterID_A, Drug_A, DDInterID_B, Drug_B, Level` |
| Unique pairs | 160,235 (222,383 rows; the same pair appears in several ATC files, with no conflicting levels) |
| Labeled | 130,422: Major 26,914 → **high**, Moderate 96,675 → **moderate**, Minor 6,833 → **low** |
| Unlabeled | 29,813 pairs with level **Unknown** |
| Drugs | 1,939 |

`download_ddi.py` saves the raw files unchanged in `data/ddinter/` with `SOURCE.json`
(download date, sha256 checksum, row and level counts).

## Method (`train_interaction.py`)

1. **Graph of pairs.** Every drug pair is one node. Pair features come from the
   drug-drug interaction network:
   - drug embedding: TruncatedSVD (32 dimensions) of the drug × drug adjacency matrix
     (which drugs interact, with no severity labels);
   - drug risk profile: the share of high / moderate / low among the drug's
     *training* pairs. It is leave-one-out, so a pair never sees its own label;
   - pair vector: a symmetric combination of the two drugs (sum, product, min, max,
     degree), so A+B gives the same result as B+A.
2. **Model.** `sklearn.semi_supervised.LabelSpreading` on a k-nearest-neighbour graph
   of the pair vectors (a precomputed, symmetric kNN graph). Labels spread from labeled
   pairs to similar unlabeled ones.
3. **Split.** The labeled pairs are split stratified 70 / 15 / 15 into train, val and
   test. The val set picks:
   - `k ∈ {10, 20}`;
   - `alpha ∈ {0.1, 0.3, 0.6, 0.9}`;
   - an optional class-prior correction;
   - a weight on the **high** class score (1–3×).

   **Selection rule:** keep the settings within 0.01 of the best val macro-F1, then
   take the one with the highest val **high-class recall**. Missing a dangerous
   interaction is worse than a false alarm.

   Chosen settings: **k = 10, alpha = 0.1, high weight = 2.0, no prior correction**.
   The test set is used once.
4. **Calibration.** A temperature is fitted on the val set by minimising log-loss.
   The scores were already well calibrated:
   - test ECE (expected calibration error) is **0.022**;
   - the fitted temperature is 1.0, so the scores are left unchanged.

   The confidence shown in the app can therefore be read roughly as "how often this
   kind of prediction is right".
5. **Final model.** It is refit with all labels, then predicts every Unknown pair.
   Those predictions are written to `models/interaction_risk_model.json`.

## Results (held-out test set, 19,564 pairs)

| Model | Accuracy | Macro-F1 | High-risk recall |
|---|---|---|---|
| **Label Spreading (semi-supervised)** | **0.927** | **0.881** | **0.922** |
| Logistic Regression (labeled only, class-balanced) | 0.807 | 0.713 | 0.846 |
| Majority class ("moderate") | 0.741 | 0.284 | 0.000 |

Per class for Label Spreading:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| low | 0.911 | 0.755 | 0.826 | 1,025 |
| moderate | 0.964 | 0.941 | 0.952 | 14,502 |
| high | 0.816 | 0.922 | 0.866 | 4,037 |

Confusion matrix (rows = true class, columns = predicted class):

| | low | moderate | high |
|---|---|---|---|
| **low** | 774 | 209 | 42 |
| **moderate** | 68 | 13,639 | 795 |
| **high** | 8 | 307 | 3,722 |

**What the unlabeled data adds.** This experiment trains with only part of the
training labels and reports test macro-F1 (see `models/interaction_label_curve.png`):

| Labels used | 5 % | 10 % | 25 % | 50 % | 100 % |
|---|---|---|---|---|---|
| Label Spreading | 0.691 | 0.760 | 0.816 | 0.861 | 0.881 |
| Logistic Regression | 0.586 | 0.634 | 0.674 | 0.697 | 0.713 |

The semi-supervised model is ahead at every label fraction.

**Unknown pairs predicted:** 29,813 (low 3,944 / moderate 21,986 / high 3,883).
86.5 % of them have confidence ≥ 0.6, which is the backend threshold for showing a
prediction.

**Effect of the high-recall selection.** It replaced a pure macro-F1 choice.

| | Before | After |
|---|---|---|
| High recall | 0.841 | 0.922 |
| Macro-F1 | 0.886 | 0.881 |
| High precision | 0.910 | 0.816 |

More moderate pairs are now flagged as high (795 instead of 320). This is a
deliberate trade: a false alarm is safer than a missed danger.

## Limitations (report these honestly)

- **Missed and over-flagged high-risk pairs.**
  - About 8 % of truly major interactions are still predicted as moderate
    (high recall 0.922).
  - About 18 % of the pairs predicted as high are not major in DDInter (precision 0.816).
- **Calibration is measured only on labeled pairs.** It shows ECE 0.022 there. It
  may not hold for the Unknown pairs (see below).
- **No ground truth for Unknown pairs.** Test metrics are measured on labeled pairs.
  DDInter's Unknown pairs come mostly from a different source (a Sci Transl Med
  data-mining study), so accuracy on them cannot be measured and may be lower.
- **Coverage.**
  - Only pairs listed in DDInter are predicted. A pair that DDInter does not list
    gets no prediction, and the system shows "unknown", never "safe".
  - DDInter publishes only 8 ATC groups. For example, a cardiovascular–cardiovascular
    pair is present only if one of the drugs is also in another group.
  - Some Bangladesh-specific generics are not in DDInter at all (e.g. etoricoxib,
    aceclofenac, gliclazide, domperidone, flucloxacillin).
  - 76.9 % of allopathic products in `../model2/medicine.csv` have every active
    ingredient matched to a DDInter drug.
- **Feature leakage control.** The drug risk profiles use training labels only, with
  leave-one-out. Edge *presence* of all pairs is used in the embedding: this is
  transductive, and presence is not a label.
- **Decision support only.** The model does not diagnose, prescribe, or replace a
  doctor or pharmacist.

## Name matching (`drug_names.py`)

MedEx writes salts and INN names ("Amlodipine Besilate", "Paracetamol"). DDInter uses
base names and sometimes US names ("Amlodipine", "Acetaminophen"). `resolve()` tries
these in order:
1. the full name;
2. the name without salt or hydrate words, keeping route notes such as "(topical)";
3. two-way INN ↔ US synonyms;
4. the first word.

It returns `None` when nothing matches. Training and the backend use the same file.

## Run

```bash
cd model1
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python download_ddi.py            # about 12 MB, saved in data/ddinter/
.venv/bin/python train_interaction.py       # about 20 min on a laptop (8 kNN graphs of 160k nodes)
.venv/bin/python train_interaction.py --sample 15000   # quick check, under 30 s
```

Outputs in `models/`:
- `interaction_risk_model.json`: read by the backend;
- `interaction_metrics.json`;
- `interaction_confusion.png`;
- `interaction_label_curve.png`.

## Backend connection

- `backend/app/ai/interaction_adapter.py` loads the JSON once and connects through
  `set_predictor()`. The backend does not need scikit-learn.
- `flask --app run import-data` loads DDInter's known levels into `known_interaction`.
  Those are shown as **Verified**.
- The checker order is:
  1. Verified (DDInter level);
  2. Predicted (this model, confidence ≥ 0.6), shown together with Documented
     (monograph text in `generic.csv`);
  3. Unknown.
- Restart the server after retraining.
