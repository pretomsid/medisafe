"""Model 1: semi-supervised drug-interaction risk prediction (Label Spreading).

    python download_ddi.py              # once: get DDInter 2.0 into data/ddinter/
    python train_interaction.py         # train, evaluate, write models/interaction_*
    python train_interaction.py --sample 20000   # quick run on a small random subset

Data   : DDInter 2.0 drug pairs. Major / Moderate / Minor = labeled (-> high / moderate / low),
         Unknown = unlabeled. This is the labeled + unlabeled mix the proposal asks for.
Graph  : every drug pair is one node. Pair features come from the drug-drug interaction network:
           - drug embedding  = TruncatedSVD of the drug x drug adjacency matrix (edge presence only),
           - drug risk profile = share of high / moderate / low among the drug's TRAINING pairs
             (leave-one-out for training pairs, so a pair never sees its own label),
           - pair vector = symmetric combination of the two drugs (sum, product, min, max).
Model  : sklearn LabelSpreading on a k-nearest-neighbour graph of those pair vectors.
         Labels spread from labeled pairs to similar unlabeled ones.
Checks : stratified 70/15/15 split of labeled pairs; val picks k, alpha and a class-prior
         correction; test is used once. Baselines: majority class and LogisticRegression
         (labeled data only). A label-fraction experiment shows what the unlabeled data adds.
Output : models/interaction_risk_model.json  (metadata + predictions for every Unknown pair;
                                              the backend only reads this JSON)
         models/interaction_metrics.json, interaction_confusion.png, interaction_label_curve.png

Predictions are decision support only, never a clinical decision, and they only cover pairs that
DDInter lists. A pair missing from DDInter is NOT predicted and is never reported as safe.
"""
import argparse
import glob
import json
import os
import time
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import kneighbors_graph
from sklearn.preprocessing import StandardScaler
from sklearn.semi_supervised import LabelSpreading

from drug_names import normalize, pair_key

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data", "ddinter")
OUT_DIR = os.path.join(HERE, "models")
LEVEL_TO_CLASS = {"Minor": "low", "Moderate": "moderate", "Major": "high"}
CLASSES = ["low", "moderate", "high"]          # index = class id used by the model
SEED = 42
EMB_DIM = 32
GRID_K = [10, 20]
GRID_ALPHA = [0.1, 0.3, 0.6, 0.9]
GRID_BETA = [0.0, 0.5, 1.0]                     # class-prior correction strength
GRID_BOOST = [1.0, 1.25, 1.5, 2.0, 3.0]         # extra weight on the "high" class score
F1_TOLERANCE = 0.01   # among settings within 0.01 val macro-F1 of the best, pick the highest HIGH recall
GRID_T = np.round(np.logspace(-0.5, 1.5, 41), 4)  # temperature for confidence calibration
FRACTIONS = [0.05, 0.10, 0.25, 0.50, 1.00]


# ---------------------------------------------------------------- data
def load_pairs(sample=None):
    files = sorted(glob.glob(os.path.join(DATA_DIR, "ddinter_downloads_code_*.csv")))
    if not files:
        raise SystemExit("No DDInter files found. Run: python download_ddi.py")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    a, b = df["DDInterID_A"].to_numpy(), df["DDInterID_B"].to_numpy()
    df["id_a"], df["id_b"] = np.where(a < b, a, b), np.where(a < b, b, a)
    name = dict(zip(df["DDInterID_A"], df["Drug_A"])) | dict(zip(df["DDInterID_B"], df["Drug_B"]))
    # same pair can appear in several ATC files; keep the most severe level if they ever disagree
    rank = {"Unknown": 0, "Minor": 1, "Moderate": 2, "Major": 3}
    df["r"] = df["Level"].map(rank)
    pairs = df.sort_values("r").drop_duplicates(["id_a", "id_b"], keep="last")
    pairs = pairs[["id_a", "id_b", "Level"]].reset_index(drop=True)
    if sample and sample < len(pairs):
        pairs = pairs.sample(sample, random_state=SEED).reset_index(drop=True)
    pairs["y"] = pairs["Level"].map(lambda lv: CLASSES.index(LEVEL_TO_CLASS[lv]) if lv in LEVEL_TO_CLASS else -1)
    return pairs, name, files


# ---------------------------------------------------------------- features
def drug_index(pairs):
    ids = np.unique(np.concatenate([pairs["id_a"], pairs["id_b"]]))
    pos = {d: i for i, d in enumerate(ids)}
    return ids, pairs["id_a"].map(pos).to_numpy(), pairs["id_b"].map(pos).to_numpy()


def embeddings(n_drugs, ia, ib):
    """Drug vectors from WHO interacts with whom (no severity labels used)."""
    ones = np.ones(len(ia))
    adj = sparse.coo_matrix((ones, (ia, ib)), shape=(n_drugs, n_drugs)).tocsr()
    adj = adj + adj.T
    k = min(EMB_DIM, n_drugs - 1)
    emb = TruncatedSVD(n_components=k, random_state=SEED).fit_transform(adj)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
    degree = np.asarray(adj.sum(axis=1)).ravel()
    return emb, np.log1p(degree)


def risk_profiles(n_drugs, ia, ib, y_known):
    """Per drug: counts of low/moderate/high among pairs whose label the model may see."""
    counts = np.zeros((n_drugs, len(CLASSES)))
    m = y_known >= 0
    np.add.at(counts, (ia[m], y_known[m]), 1)
    np.add.at(counts, (ib[m], y_known[m]), 1)
    return counts


def pair_features(ia, ib, emb, logdeg, counts, y_known, prior):
    """Symmetric pair vector. Leave-one-out: a labeled pair's own label is removed from both drugs' profiles."""
    ca, cb = counts[ia].copy(), counts[ib].copy()
    own = y_known >= 0
    ca[own, y_known[own]] -= 1
    cb[own, y_known[own]] -= 1
    smooth = 2.0   # Laplace-style smoothing toward the overall class prior
    pa = (ca + smooth * prior) / (ca.sum(1, keepdims=True) + smooth)
    pb = (cb + smooth * prior) / (cb.sum(1, keepdims=True) + smooth)
    na, nb = np.log1p(ca.sum(1)), np.log1p(cb.sum(1))
    ea, eb = emb[ia], emb[ib]
    da, db = logdeg[ia], logdeg[ib]
    return np.hstack([
        ea + eb, ea * eb,
        pa + pb, np.minimum(pa, pb), np.maximum(pa, pb),
        np.c_[da + db, np.minimum(da, db), np.maximum(da, db), np.minimum(na, nb), np.maximum(na, nb)],
    ]).astype(np.float32)


def build_features(ia, ib, n_drugs, emb, logdeg, y_known):
    prior = np.bincount(y_known[y_known >= 0], minlength=len(CLASSES)) / max((y_known >= 0).sum(), 1)
    counts = risk_profiles(n_drugs, ia, ib, y_known)
    X = pair_features(ia, ib, emb, logdeg, counts, y_known, prior)
    return StandardScaler().fit_transform(X), prior


# ---------------------------------------------------------------- model
def knn_graph(X, k):
    g = kneighbors_graph(X, k, mode="connectivity", include_self=False, n_jobs=-1)
    return g.maximum(g.T).tocsr()


def spread(X, graph, y_masked, alpha):
    """Label Spreading on a precomputed kNN graph (the callable kernel just returns it)."""
    model = LabelSpreading(kernel=lambda a, b: graph, alpha=alpha, max_iter=300, tol=1e-4)
    model.fit(X, y_masked)
    dist = np.nan_to_num(model.label_distributions_)
    return dist, model.n_iter_


def correct(dist, prior, beta, boost=1.0):
    """Divide by class prior^beta so the majority class (moderate) does not swallow the rest,
    then multiply the HIGH score by `boost` (missing a dangerous interaction is worse than a false alarm)."""
    s = dist / np.power(prior, beta)
    s[:, CLASSES.index("high")] *= boost
    total = s.sum(1, keepdims=True)
    s = np.where(total > 0, s / np.where(total > 0, total, 1), 1.0 / len(CLASSES))
    return s


def temper(prob, T):
    """Temperature scaling: p^(1/T), renormalised. T > 1 softens over-confident scores."""
    s = np.power(np.clip(prob, 1e-12, 1), 1.0 / T)
    return s / s.sum(1, keepdims=True)


def fit_temperature(prob, y_true):
    """Pick T that minimises log-loss on the validation pairs."""
    nll = [-np.mean(np.log(temper(prob, T)[np.arange(len(y_true)), y_true])) for T in GRID_T]
    return float(GRID_T[int(np.argmin(nll))])


def ece(prob, y_true, bins=10):
    """Expected calibration error: gap between confidence and accuracy, averaged over 10 bins."""
    conf, pred = prob.max(1), prob.argmax(1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs((pred[m] == y_true[m]).mean() - conf[m].mean())
    return round(float(total), 4)


def macro_f1(y_true, y_pred):
    return f1_score(y_true, y_pred, average="macro", labels=list(range(len(CLASSES))), zero_division=0)


def logreg(X, y_masked, idx_eval):
    lab = np.where(y_masked >= 0)[0]
    clf = LogisticRegression(class_weight="balanced", max_iter=2000)
    clf.fit(X[lab], y_masked[lab])
    return clf.predict(X[idx_eval])


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Train the semi-supervised DDI risk model")
    ap.add_argument("--sample", type=int, default=None, help="use a random subset of N pairs (quick run)")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    os.makedirs(args.out, exist_ok=True)

    pairs, names, files = load_pairs(args.sample)
    y = pairs["y"].to_numpy()
    labeled = np.where(y >= 0)[0]
    unlabeled = np.where(y < 0)[0]
    print(f"Pairs: {len(pairs):,}  labeled: {len(labeled):,}  unlabeled (Unknown): {len(unlabeled):,}")
    print("Labeled classes:", {c: int((y == i).sum()) for i, c in enumerate(CLASSES)})

    tr, rest = train_test_split(labeled, test_size=0.30, stratify=y[labeled], random_state=SEED)
    va, te = train_test_split(rest, test_size=0.50, stratify=y[rest], random_state=SEED)
    print(f"Split  train {len(tr):,} / val {len(va):,} / test {len(te):,}")

    ids, ia, ib = drug_index(pairs)
    emb, logdeg = embeddings(len(ids), ia, ib)

    # ---- features that only know TRAIN labels (val/test/Unknown look unlabeled)
    y_train_only = np.full(len(y), -1)
    y_train_only[tr] = y[tr]
    X, prior = build_features(ia, ib, len(ids), emb, logdeg, y_train_only)

    # ---- tune k, alpha, beta, high-boost on val
    # Rule: keep settings within F1_TOLERANCE of the best val macro-F1, then take the highest
    # HIGH-class recall (the backend plan names high recall as the main safety metric).
    graphs, cands = {}, []
    high = CLASSES.index("high")
    for k in GRID_K:
        s = time.time()
        graphs[k] = knn_graph(X, k)
        print(f"kNN graph k={k}: {graphs[k].nnz:,} edges ({time.time() - s:.0f}s)")
        for alpha in GRID_ALPHA:
            dist, it = spread(X, graphs[k], y_train_only, alpha)
            for beta in GRID_BETA:
                for boost in GRID_BOOST:
                    pv = correct(dist, prior, beta, boost)[va].argmax(1)
                    cands.append(dict(k=k, alpha=alpha, beta=beta, high_boost=boost,
                                      val_macro_f1=macro_f1(y[va], pv),
                                      val_high_recall=float(((pv == high) & (y[va] == high)).sum() / max((y[va] == high).sum(), 1))))
            top = max(c["val_macro_f1"] for c in cands)
            print(f"  alpha={alpha}: iters={it}  best val macro-F1 so far {top:.3f}")
    top = max(c["val_macro_f1"] for c in cands)
    best = max((c for c in cands if c["val_macro_f1"] >= top - F1_TOLERANCE),
               key=lambda c: (c["val_high_recall"], c["val_macro_f1"]))
    print("Chosen:", best)

    # ---- test once with the chosen settings (+ temperature fitted on val only)
    graph = graphs[best["k"]]
    dist, _ = spread(X, graph, y_train_only, best["alpha"])
    raw = correct(dist, prior, best["beta"], best["high_boost"])
    T = fit_temperature(raw[va], y[va])
    prob = temper(raw, T)
    best["temperature"] = T
    calibration = {"temperature": T, "val_ece_before": ece(raw[va], y[va]), "val_ece_after": ece(prob[va], y[va]),
                   "test_ece_before": ece(raw[te], y[te]), "test_ece_after": ece(prob[te], y[te])}
    print("Calibration:", calibration)
    pred_te = prob[te].argmax(1)
    majority = int(np.bincount(y[tr]).argmax())
    lr_te = logreg(X, y_train_only, te)

    def summary(y_pred):
        rep = classification_report(y[te], y_pred, labels=list(range(3)), target_names=CLASSES,
                                    output_dict=True, zero_division=0)
        return {"accuracy": round(accuracy_score(y[te], y_pred), 4),
                "macro_f1": round(macro_f1(y[te], y_pred), 4),
                "per_class": {c: {m: round(rep[c][m], 4) for m in ("precision", "recall", "f1-score", "support")}
                              for c in CLASSES}}

    results = {"label_spreading": summary(pred_te),
               "logistic_regression_labeled_only": summary(lr_te),
               "majority_class": summary(np.full(len(te), majority))}
    for name_, r in results.items():
        print(f"TEST {name_:34s} acc={r['accuracy']:.3f}  macro-F1={r['macro_f1']:.3f}  "
              f"high recall={r['per_class']['high']['recall']:.3f}")
    cm = confusion_matrix(y[te], pred_te, labels=list(range(3)))

    # ---- label-fraction experiment: how much do unlabeled pairs help when labels are scarce?
    curve = []
    for frac in FRACTIONS:
        keep = tr if frac >= 1 else rng.choice(tr, int(len(tr) * frac), replace=False)
        y_frac = np.full(len(y), -1)
        y_frac[keep] = y[keep]
        Xf, prior_f = build_features(ia, ib, len(ids), emb, logdeg, y_frac)
        gf = knn_graph(Xf, best["k"])
        d, _ = spread(Xf, gf, y_frac, best["alpha"])
        ls = macro_f1(y[te], correct(d, prior_f, best["beta"], best["high_boost"])[te].argmax(1))
        lr = macro_f1(y[te], logreg(Xf, y_frac, te))
        curve.append({"fraction": frac, "labeled_pairs": int(len(keep)),
                      "label_spreading_macro_f1": round(ls, 4), "logistic_regression_macro_f1": round(lr, 4)})
        print(f"labels {frac:>5.0%}: LabelSpreading {ls:.3f}  LogisticRegression {lr:.3f}")

    # ---- final model: all labels known -> predict every Unknown pair
    Xa, prior_a = build_features(ia, ib, len(ids), emb, logdeg, y)
    da, _ = spread(Xa, knn_graph(Xa, best["k"]), y, best["alpha"])
    prob_all = temper(correct(da, prior_a, best["beta"], best["high_boost"]), T)
    name_of = lambda d: normalize(names[d])
    predictions = {}
    for i in unlabeled:
        p = prob_all[i]
        c = int(p.argmax())
        predictions[pair_key(name_of(pairs.at[i, "id_a"]), name_of(pairs.at[i, "id_b"]))] = {
            "category": CLASSES[c], "confidence": round(float(p[c]), 3)}
    conf = np.array([v["confidence"] for v in predictions.values()]) if predictions else np.array([0.0])

    # ---- write outputs
    source = {}
    src_path = os.path.join(DATA_DIR, "SOURCE.json")
    if os.path.exists(src_path):
        with open(src_path, encoding="utf-8") as f:
            source = json.load(f)
    metrics = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample": args.sample,
        "data": {"pairs": int(len(pairs)), "labeled": int(len(labeled)), "unlabeled": int(len(unlabeled)),
                 "drugs": int(len(ids)), "class_counts": {c: int((y == i).sum()) for i, c in enumerate(CLASSES)},
                 "split": {"train": int(len(tr)), "val": int(len(va)), "test": int(len(te))}},
        "chosen_params": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in best.items()},
        "test": results,
        "calibration": calibration,
        "selection_rule": f"val macro-F1 within {F1_TOLERANCE} of best, then highest val high-class recall",
        "confusion_matrix": {"labels": CLASSES, "rows_true_cols_pred": cm.tolist()},
        "label_fraction_curve": curve,
        "unknown_predictions": {"count": len(predictions),
                                "by_category": {c: sum(v["category"] == c for v in predictions.values()) for c in CLASSES},
                                "share_confidence_ge_0_6": round(float((conf >= 0.6).mean()), 4)},
        "runtime_seconds": round(time.time() - t0, 1),
    }
    model = {
        "model_type": "semi-supervised drug-interaction risk classifier (sklearn LabelSpreading, kNN graph)",
        "created_at_utc": metrics["created_at_utc"],
        "dataset": {"name": "DDInter 2.0", "license": source.get("license", "CC BY-NC-SA 4.0"),
                    "citation": source.get("citation"), "downloaded_at_utc": source.get("downloaded_at_utc"),
                    "files": [{"file": f["file"], "sha256": f["sha256"]} for f in source.get("files", [])]},
        "label_map": LEVEL_TO_CLASS,
        "classes": CLASSES,
        "params": metrics["chosen_params"],
        "metrics": {"test": results, "label_fraction_curve": curve, "calibration": calibration},
        "clinical_note": ("Predicted risk levels are model estimates for DDInter pairs whose severity is "
                          "'Unknown'. They are decision support only and must be verified by a doctor or "
                          "pharmacist. Pairs not listed in DDInter are not predicted and are never 'safe'."),
        "drugs": sorted({name_of(d) for d in ids}),
        "predictions": predictions,
    }
    with open(os.path.join(args.out, "interaction_risk_model.json"), "w", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(args.out, "interaction_metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    fig, ax = plt.subplots(figsize=(4.6, 4))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(3), CLASSES)
    ax.set_yticks(range(3), CLASSES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True (DDInter)")
    for r in range(3):
        for c in range(3):
            ax.text(c, r, f"{cm[r, c]:,}", ha="center", va="center",
                    color="white" if cm[r, c] > cm.max() / 2 else "black")
    ax.set_title("Label Spreading — test set")
    fig.tight_layout()
    fig.savefig(os.path.join(args.out, "interaction_confusion.png"), dpi=150)

    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    xs = [c["fraction"] * 100 for c in curve]
    ax.plot(xs, [c["label_spreading_macro_f1"] for c in curve], marker="o", label="Label Spreading (semi-supervised)")
    ax.plot(xs, [c["logistic_regression_macro_f1"] for c in curve], marker="s", label="Logistic Regression (labeled only)")
    ax.set_xscale("log")
    ax.set_xticks(xs, [f"{x:g}%" for x in xs])
    ax.set_xlabel("Share of training labels used")
    ax.set_ylabel("Test macro-F1")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(args.out, "interaction_label_curve.png"), dpi=150)

    print(f"Unknown pairs predicted: {len(predictions):,} {metrics['unknown_predictions']['by_category']}")
    print(f"Saved model + metrics in {args.out}  ({metrics['runtime_seconds']}s)")


if __name__ == "__main__":
    main()
