"""Experiments for the paper.

Run from the project root:
    backend\\.venv\\Scripts\\python research\\run_research.py

Reads the QoL_Stress CSV files (read-only), reuses the application's validated
preprocessing (backend/app/dataset/qol.py) and model definitions
(backend/app/ml/evaluation.py), and writes every number used in the paper to
research/results/results.json plus CSV tables. Nothing is written to the
application database.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("APP_DB_PATH", str(Path(tempfile.gettempdir()) / "qol_research_unused.db"))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import scipy  # noqa: E402
import sklearn  # noqa: E402
from scipy import stats  # noqa: E402
from sklearn.base import clone  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    balanced_accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, GroupKFold, StratifiedKFold  # noqa: E402

from app import config  # noqa: E402
from app.dataset import loader, qol  # noqa: E402
from app.ml import evaluation  # noqa: E402
from ecg_hrv import hrv_table  # noqa: E402

OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
SEED = 42
K = 5
N_BOOT = 2000
N_REPEATS = 10
MODELS = ["dummy", "logistic_regression", "random_forest", "svm"]
REAL = ["logistic_regression", "random_forest", "svm"]
HR = qol.HR_STAT_FEATURES
REL = qol.PERSONAL_FEATURES
HRV = ["ecg_hr_derived", "ecg_sdnn", "ecg_rmssd"]
EDA = ["eda_scl_mean", "eda_scl_std", "eda_activation_frac"]
RESULTS: dict = {}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------
def scores_of(est, X):
    m = est.named_steps["model"] if hasattr(est, "named_steps") else est.best_estimator_.named_steps["model"]
    if m.__class__.__name__.startswith("Dummy"):
        return None
    if hasattr(m, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    return est.decision_function(X)


def grouped_cv(X, y, groups, model, seed=SEED, k=K, estimator=None):
    """Participant-wise CV; returns out-of-fold predictions/scores and fold info."""
    folds = evaluation.fold_assignment(sorted(groups.unique()), k, seed)
    f = groups.map(folds).to_numpy()
    pred = np.zeros(len(y), dtype=int)
    score = np.full(len(y), np.nan)
    info = []
    for i in range(k):
        te, tr = f == i, f != i
        assert not set(groups[tr]) & set(groups[te]), "participant overlap"
        est = clone(estimator) if estimator is not None else evaluation.make_estimator("classification", model)
        est.fit(X[tr], y[tr]) if estimator is None else est.fit(X[tr], y[tr], groups=groups[tr])
        pred[te] = est.predict(X[te])
        s = scores_of(est, X[te])
        if s is not None:
            score[te] = s
        info.append({"fold": i, "n_train": int(tr.sum()), "n_test": int(te.sum()),
                     "n_train_participants": int(groups[tr].nunique()), "n_test_participants": int(groups[te].nunique()),
                     "test_ba": float(balanced_accuracy_score(y[te], pred[te]))})
    return pred, score, info


def per_participant_ba(y, pred, groups) -> pd.Series:
    out = {}
    for g in groups.unique():
        m = (groups == g).to_numpy()
        yt, yp = y[m], pred[m]
        out[g] = balanced_accuracy_score(yt, yp) if len(set(yt)) == 2 else float(np.mean(yt == yp))
    return pd.Series(out)


def metrics(y, pred, score) -> dict:
    d = {
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "precision_macro": float(precision_score(y, pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y, pred, average="macro", zero_division=0)),
        "recall_relax": float(recall_score(y, pred, pos_label=0, zero_division=0)),
        "recall_stress": float(recall_score(y, pred, pos_label=1, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, score)) if not np.isnan(score).any() else None,
        "confusion_matrix": confusion_matrix(y, pred, labels=[0, 1]).tolist(),
    }
    return d


def boot_ci(y, preds: dict, groups, n=N_BOOT, seed=SEED) -> dict:
    """Participant-cluster bootstrap of pooled balanced accuracy (and pairwise differences)."""
    rng = np.random.default_rng(seed)
    parts = np.array(sorted(groups.unique()))
    idx_of = {p: np.flatnonzero((groups == p).to_numpy()) for p in parts}
    samples = {k: [] for k in preds}
    for _ in range(n):
        pick = rng.choice(parts, size=len(parts), replace=True)
        idx = np.concatenate([idx_of[p] for p in pick])
        for k, pr in preds.items():
            samples[k].append(balanced_accuracy_score(y[idx], pr[idx]))
    return {k: np.array(v) for k, v in samples.items()}


def ci(a) -> list:
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def holm(pvals: dict) -> dict:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    return out


def wilcoxon(a: pd.Series, b: pd.Series) -> dict:
    common = a.index.intersection(b.index)
    d = (b[common] - a[common]).to_numpy()
    if np.allclose(d, 0):
        return {"n": int(len(d)), "mean_diff": 0.0, "median_diff": 0.0, "p": 1.0, "n_better": 0, "n_worse": 0}
    w = stats.wilcoxon(b[common], a[common], zero_method="wilcox")
    return {"n": int(len(d)), "mean_diff": float(d.mean()), "median_diff": float(np.median(d)), "statistic": float(w.statistic),
            "p": float(w.pvalue), "n_better": int((d > 0).sum()), "n_worse": int((d < 0).sum()), "n_tied": int((d == 0).sum())}


# ---------------------------------------------------------------------------
def main() -> None:
    t0 = time.time()
    log(f"dataset: {loader.dataset_dir()}")
    p = qol.build(force=True)
    W = p.windows.reset_index(drop=True).copy()
    S = p.segments.reset_index(drop=True).copy()
    sess = p.sessions.set_index("username")
    eligible = sorted(W["username"].unique())

    RESULTS["environment"] = {
        "python": platform.python_version(), "platform": platform.platform(), "processor": platform.processor(),
        "numpy": np.__version__, "pandas": pd.__version__, "scikit_learn": sklearn.__version__, "scipy": scipy.__version__,
        "dataset_fingerprint": p.fingerprint, "seed": SEED, "k_folds": K, "n_bootstrap": N_BOOT, "n_repeats": N_REPEATS,
        "preprocessing": config.settings.preprocessing.__dict__,
    }

    # ---------------- Dataset characterisation ----------------
    files = {}
    for name in ["participants.csv", "fitbit_heart_rate_per_second.csv", "fitbit_heart_rate_per_minute.csv",
                 "fitbit_heart_rate_summary.csv", "stai.csv", "pss_14.csv", "eda.csv", "ecg.csv"]:
        df = loader.load(name)
        files[name] = {"rows": int(len(df)), "participants": int(df["username"].nunique()), "columns": int(len(df.columns))}
    part = loader.load("participants.csv")
    RESULTS["dataset"] = {
        "files": files,
        "sex": part["sex"].value_counts().to_dict(),
        "age_mean": float(part["age"].mean()), "age_sd": float(part["age"].std()),
        "age_min": int(part["age"].min()), "age_max": int(part["age"].max()),
        "job_category": part["job_category"].value_counts().to_dict(),
        "education": part["education_level"].value_counts().to_dict(),
        "preprocessing_summary": {k: v for k, v in p.summary.items() if k not in ("config",)},
        "n_eligible": len(eligible),
        "windows_per_phase": W["phase"].value_counts().to_dict(),
        "windows_per_participant": W.groupby("username").size().describe().to_dict(),
        "relax_eval_minutes": ((sess.loc[eligible, "relax_eval_end"] - sess.loc[eligible, "relax_eval_start"]) / 60).describe().to_dict(),
        "stress_eval_minutes": ((sess.loc[eligible, "stress_eval_end"] - sess.loc[eligible, "stress_eval_start"]) / 60).describe().to_dict(),
        "samples_per_window": W["n_samples"].describe().to_dict(),
    }
    paired = S.pivot(index="username", columns="phase", values="stai_score").dropna()
    w = stats.wilcoxon(paired["stress"], paired["relax"])
    RESULTS["manipulation_check"] = {
        "n": int(len(paired)), "relax_mean": float(paired["relax"].mean()), "relax_sd": float(paired["relax"].std()),
        "stress_mean": float(paired["stress"].mean()), "stress_sd": float(paired["stress"].std()),
        "wilcoxon_p": float(w.pvalue), "n_higher": int((paired["stress"] > paired["relax"]).sum()),
        "n_equal": int((paired["stress"] == paired["relax"]).sum()), "n_lower": int((paired["stress"] < paired["relax"]).sum()),
        "hr_segment_relax_mean": float(S.loc[S.phase == "relax", "hr_mean"].mean()),
        "hr_segment_stress_mean": float(S.loc[S.phase == "stress", "hr_mean"].mean()),
        "hr_window_relax_mean": float(W.loc[W.phase == "relax", "hr_mean"].mean()),
        "hr_window_stress_mean": float(W.loc[W.phase == "stress", "hr_mean"].mean()),
    }
    hrp = W.groupby(["username", "phase"])["hr_mean"].mean().unstack()
    RESULTS["manipulation_check"]["participants_hr_higher_in_stress"] = int((hrp["stress"] > hrp["relax"]).sum())
    log("dataset characterised")

    # ---------------- Calibration-length variants of baseline features ----------------
    hr = p.hr
    base_by_len = {}
    for L in (1, 2, 3):
        rows = {}
        for u in eligible:
            g = hr[hr["username"] == u]
            s0 = sess.loc[u, "hr_start"]
            v = g.loc[(g["t"] >= s0) & (g["t"] < s0 + L * 60), "value"].to_numpy(float)
            rows[u] = qol.baseline_stats(v)
        base_by_len[L] = pd.DataFrame(rows).T

    def rel_features(df: pd.DataFrame, L: int) -> pd.DataFrame:
        b = base_by_len[L].loc[df["username"]].reset_index(drop=True)
        out = pd.DataFrame(index=df.index)
        sd = np.maximum(b["base_sd"].astype(float).to_numpy(), qol.MIN_BASELINE_SD)
        out["hr_mean_delta"] = df["hr_mean"].to_numpy() - b["base_median"].to_numpy(float)
        out["hr_median_delta"] = df["hr_median"].to_numpy() - b["base_median"].to_numpy(float)
        out["hr_mean_ratio"] = df["hr_mean"].to_numpy() / b["base_median"].to_numpy(float)
        out["hr_mean_z"] = (df["hr_mean"].to_numpy() - b["base_mean"].to_numpy(float)) / sd
        out["hr_std_ratio"] = df["hr_std"].to_numpy() / sd
        return out

    # sanity: 3-min recomputation equals the application's features
    chk = rel_features(W, 3)
    assert np.allclose(chk["hr_mean_delta"], W["hr_mean_delta"], equal_nan=True)
    RESULTS["calibration_samples"] = {L: base_by_len[L]["base_n"].astype(float).describe().to_dict() for L in base_by_len}

    # Transductive per-participant z-score (label-free but uses all of a test participant's windows): reference only
    Z = W.groupby("username")[HR].transform(lambda c: (c - c.mean()) / (c.std(ddof=1) if c.std(ddof=1) > 0 else 1.0))
    Z.columns = [f"z_{c}" for c in HR]
    W = pd.concat([W, Z], axis=1)

    y = W["label"].to_numpy()
    g = W["username"]
    featsets = {
        "A_absolute": HR,
        "R_relative_only": REL,
        "AR_absolute_plus_relative": HR + REL,
        "Zt_transductive_zscore": list(Z.columns),
        "T_time_only": ["minutes_from_hr_start"],
    }

    # ---------------- Experiment 1 & 3: window level ----------------
    log("window-level participant-wise CV")
    win = {}
    preds, pp_ba = {}, {}
    for fs_name, cols in featsets.items():
        X = W[cols].astype(float)
        for m in MODELS:
            if fs_name in ("T_time_only", "Zt_transductive_zscore") and m not in ("logistic_regression", "random_forest"):
                continue
            pred, score, info = grouped_cv(X, y, g, m)
            key = f"{fs_name}|{m}"
            win[key] = {**metrics(y, pred, score), "folds": info, "n_participants": int(g.nunique()), "n_samples": int(len(y)), "features": cols}
            preds[key] = pred
            pp_ba[key] = per_participant_ba(y, pred, g)
    boots = boot_ci(y, preds, g)
    for key in win:
        win[key]["ba_ci95"] = ci(boots[key])
        win[key]["per_participant_ba_mean"] = float(pp_ba[key].mean())
        win[key]["per_participant_ba_sd"] = float(pp_ba[key].std())
    # paired comparisons vs absolute baseline
    comps, pvals = {}, {}
    for m in REAL:
        for other in ("R_relative_only", "AR_absolute_plus_relative"):
            k_a, k_b = f"A_absolute|{m}", f"{other}|{m}"
            c = wilcoxon(pp_ba[k_a], pp_ba[k_b])
            diff = boots[k_b] - boots[k_a]
            c.update(pooled_ba_diff=float(win[k_b]["balanced_accuracy"] - win[k_a]["balanced_accuracy"]),
                     pooled_ba_diff_ci95=ci(diff), boot_prob_positive=float((diff > 0).mean()))
            comps[f"{other} vs A_absolute|{m}"] = c
            pvals[f"{other} vs A_absolute|{m}"] = c["p"]
    for k, adj in holm(pvals).items():
        comps[k]["p_holm"] = adj
    RESULTS["window"] = win
    RESULTS["window_comparisons"] = comps
    pd.DataFrame({k: v for k, v in pp_ba.items()}).to_csv(OUT / "per_participant_ba_window.csv")
    log("window-level done")

    # ---------------- Repeated CV (fold-assignment variability) ----------------
    log("repeated CV")
    rep = {}
    for m in REAL:
        for fs_name in ("A_absolute", "R_relative_only", "AR_absolute_plus_relative"):
            vals = []
            for r in range(N_REPEATS):
                pred, _, _ = grouped_cv(W[featsets[fs_name]].astype(float), y, g, m, seed=1000 + r)
                vals.append(balanced_accuracy_score(y, pred))
            rep[f"{fs_name}|{m}"] = vals
    RESULTS["repeated_cv"] = {
        k: {"values": v, "mean": float(np.mean(v)), "sd": float(np.std(v, ddof=1))} for k, v in rep.items()
    }
    RESULTS["repeated_cv_wins"] = {
        m: {o: int(sum(b > a for a, b in zip(rep[f"A_absolute|{m}"], rep[f"{o}|{m}"]))) for o in ("R_relative_only", "AR_absolute_plus_relative")}
        for m in REAL
    }

    # ---------------- Calibration length sensitivity ----------------
    log("calibration length sensitivity")
    cal = {}
    for L in (1, 2, 3):
        R = rel_features(W, L)
        for fs_name, cols in (("R_relative_only", None), ("AR_absolute_plus_relative", HR)):
            X = R if cols is None else pd.concat([W[HR], R], axis=1)
            for m in ("logistic_regression", "svm"):
                pred, score, _ = grouped_cv(X.astype(float), y, g, m)
                cal[f"{L}min|{fs_name}|{m}"] = {"balanced_accuracy": float(balanced_accuracy_score(y, pred)),
                                                "roc_auc": float(roc_auc_score(y, score))}
    RESULTS["calibration_length"] = cal

    # ---------------- Record-wise (leaky) vs participant-wise ----------------
    log("record-wise CV")
    rec = {}
    skf = StratifiedKFold(n_splits=K, shuffle=True, random_state=SEED)
    for fs_name in ("A_absolute", "AR_absolute_plus_relative", "T_time_only"):
        X = W[featsets[fs_name]].astype(float)
        for m in ("logistic_regression", "random_forest", "svm"):
            if fs_name == "T_time_only" and m == "svm":
                continue
            pred = np.zeros(len(y), dtype=int)
            for tr, te in skf.split(X, y):
                est = evaluation.make_estimator("classification", m).fit(X.iloc[tr], y[tr])
                pred[te] = est.predict(X.iloc[te])
            rec[f"{fs_name}|{m}"] = {"balanced_accuracy": float(balanced_accuracy_score(y, pred)),
                                     "participant_wise_ba": win.get(f"{fs_name}|{m}", {}).get("balanced_accuracy")}
    RESULTS["record_wise"] = rec

    # ---------------- Temporal confound controls ----------------
    log("temporal controls")
    tc = {}
    # (i) Temporally matched windows: last 3 relax windows and first 3 stress windows of each participant
    k_m = 3
    W_sorted = W.sort_values(["username", "window_start"])
    last_relax = W_sorted[W_sorted.phase == "relax"].groupby("username").tail(k_m)
    first_stress = W_sorted[W_sorted.phase == "stress"].groupby("username").head(k_m)
    M = pd.concat([last_relax, first_stress])
    ok = M.groupby("username")["phase"].value_counts().unstack().fillna(0)
    keep = ok[(ok.get("relax", 0) == k_m) & (ok.get("stress", 0) == k_m)].index
    M = M[M.username.isin(keep)].reset_index(drop=True)
    ym, gm = M["label"].to_numpy(), M["username"]
    gap = (M[M.phase == "stress"].groupby("username").window_start.min() - M[M.phase == "relax"].groupby("username").window_start.max()) / 60
    tc["matched"] = {"k_per_phase": k_m, "n_participants": int(gm.nunique()), "n_samples": int(len(ym)),
                     "median_gap_minutes_between_last_relax_and_first_stress_window": float(gap.median())}
    m_preds = {}
    for fs_name in ("A_absolute", "R_relative_only", "AR_absolute_plus_relative"):
        for m in REAL:
            pred, score, _ = grouped_cv(M[featsets[fs_name]].astype(float), ym, gm, m)
            key = f"{fs_name}|{m}"
            tc["matched"][key] = metrics(ym, pred, score)
            m_preds[key] = pred
    mb = boot_ci(ym, m_preds, gm)
    for key in m_preds:
        tc["matched"][key]["ba_ci95"] = ci(mb[key])
    # (ii) Drift-only negative control: early vs late half of each participant's relax windows (both are "relax")
    R_ = W_sorted[W_sorted.phase == "relax"].copy()
    R_["rank"] = R_.groupby("username").cumcount()
    R_["n"] = R_.groupby("username")["rank"].transform("max") + 1
    R_ = R_[R_["n"] >= 4]
    R_["late"] = (R_["rank"] >= R_["n"] / 2).astype(int)
    R_ = R_.reset_index(drop=True)
    tc["drift_control"] = {"description": "classify first vs second half of each participant's relax windows",
                           "n_participants": int(R_.username.nunique()), "n_samples": int(len(R_))}
    for fs_name in ("A_absolute", "AR_absolute_plus_relative"):
        for m in ("logistic_regression", "random_forest"):
            pred, score, _ = grouped_cv(R_[featsets[fs_name]].astype(float), R_["late"].to_numpy(), R_["username"], m)
            tc["drift_control"][f"{fs_name}|{m}"] = metrics(R_["late"].to_numpy(), pred, score)
    # (iii) Within-phase HR trend (descriptive): slope of window mean HR vs time, per participant and phase
    slopes = {}
    for ph in ("relax", "stress"):
        sl = []
        for u, d in W_sorted[W_sorted.phase == ph].groupby("username"):
            if len(d) >= 3:
                sl.append(np.polyfit(d["minutes_from_hr_start"], d["hr_mean"], 1)[0])
        sl = np.array(sl)
        slopes[ph] = {"n": int(len(sl)), "median_bpm_per_min": float(np.median(sl)), "mean": float(sl.mean()),
                      "wilcoxon_p_vs_0": float(stats.wilcoxon(sl).pvalue), "n_negative": int((sl < 0).sum())}
    tc["within_phase_slope"] = slopes
    RESULTS["temporal_controls"] = tc

    # ---------------- Nested hyper-parameter tuning (sensitivity) ----------------
    log("nested tuning")
    grids = {
        "logistic_regression": {"model__C": [0.01, 0.1, 1, 10]},
        "svm": {"model__C": [0.1, 1, 10], "model__gamma": ["scale", 0.01, 0.1]},
        "random_forest": {"model__min_samples_leaf": [1, 5, 20], "model__max_depth": [None, 5]},
    }
    nest = {}
    for fs_name in ("A_absolute", "AR_absolute_plus_relative"):
        X = W[featsets[fs_name]].astype(float)
        for m, grid in grids.items():
            gs = GridSearchCV(evaluation.make_estimator("classification", m), grid, scoring="balanced_accuracy",
                              cv=GroupKFold(n_splits=4), n_jobs=-1)
            pred, score, info = grouped_cv(X, y, g, m, estimator=gs)
            nest[f"{fs_name}|{m}"] = {"balanced_accuracy": float(balanced_accuracy_score(y, pred)),
                                      "fixed_hyperparameters_ba": win[f"{fs_name}|{m}"]["balanced_accuracy"]}
    RESULTS["nested_tuning"] = {"grids": {k: {kk: [str(x) for x in vv] for kk, vv in v.items()} for k, v in grids.items()},
                                "inner_cv": "GroupKFold(4) on training participants only", "results": nest}

    # ---------------- Permutation importance (held-out folds) ----------------
    log("permutation importance")
    imp = {}
    for m in ("logistic_regression", "random_forest"):
        X = W[HR + REL].astype(float)
        folds = evaluation.fold_assignment(eligible, K, SEED)
        f = g.map(folds).to_numpy()
        acc = []
        for i in range(K):
            te, tr = f == i, f != i
            est = evaluation.make_estimator("classification", m).fit(X[tr], y[tr])
            r = permutation_importance(est, X[te], y[te], scoring="balanced_accuracy", n_repeats=20, random_state=SEED, n_jobs=-1)
            acc.append(r.importances_mean)
        acc = np.array(acc)
        imp[m] = {c: {"mean": float(acc[:, j].mean()), "sd_over_folds": float(acc[:, j].std(ddof=1))} for j, c in enumerate(HR + REL)}
    RESULTS["permutation_importance"] = imp

    # ---------------- Error analysis (AR, logistic regression) ----------------
    log("error analysis")
    key = "AR_absolute_plus_relative|logistic_regression"
    pred = preds[key]
    E = W[["username", "phase", "label", "window_start", "minutes_from_hr_start"]].copy()
    E["pred"] = pred
    E["correct"] = (E["pred"] == E["label"]).astype(int)
    # position relative to the phase boundary (relax: minutes before end; stress: minutes after start)
    re_end = sess.loc[E.username, "relax_eval_end"].to_numpy()
    st_start = sess.loc[E.username, "stress_eval_start"].to_numpy()
    E["pos_min"] = np.where(E.phase == "relax", (re_end - (E.window_start + 60)) / 60, (E.window_start - st_start) / 60)
    E["pos_bin"] = np.floor(E["pos_min"]).clip(upper=10).astype(int)
    pos = E.groupby(["phase", "pos_bin"])["correct"].agg(["mean", "size"]).reset_index()
    ppA = pp_ba["A_absolute|logistic_regression"]
    ppB = pp_ba[key]
    seg_w = S.pivot(index="username", columns="phase", values=["hr_mean", "stai_score"])
    d_stai = (seg_w[("stai_score", "stress")] - seg_w[("stai_score", "relax")])
    d_hr = (seg_w[("hr_mean", "stress")] - seg_w[("hr_mean", "relax")])
    base_hr = sess.loc[ppB.index, "base_median"].astype(float)
    corr = {}
    for name, v in (("delta_stai", d_stai), ("delta_segment_hr", d_hr), ("baseline_hr", base_hr),
                    ("baseline_sd", sess.loc[ppB.index, "base_sd"].astype(float))):
        rho, pv = stats.spearmanr(ppB.loc[v.index], v, nan_policy="omit")
        corr[name] = {"spearman_rho": float(rho), "p": float(pv), "n": int(v.notna().sum())}
    RESULTS["error_analysis"] = {
        "model": key,
        "per_participant_ba": {"mean": float(ppB.mean()), "median": float(ppB.median()), "sd": float(ppB.std()),
                               "n_below_0_5": int((ppB < 0.5).sum()), "n_at_or_above_0_75": int((ppB >= 0.75).sum()),
                               "n": int(len(ppB))},
        "per_participant_ba_A": {"mean": float(ppA.mean()), "median": float(ppA.median()), "n_below_0_5": int((ppA < 0.5).sum())},
        "confusion_matrix": win[key]["confusion_matrix"],
        "false_positives": int(((E.pred == 1) & (E.label == 0)).sum()),
        "false_negatives": int(((E.pred == 0) & (E.label == 1)).sum()),
        "accuracy_by_position": pos.to_dict(orient="records"),
        "correlates_of_per_participant_ba": corr,
        "class_balance": {"relax": int((y == 0).sum()), "stress": int((y == 1).sum())},
    }
    E.to_csv(OUT / "window_predictions_AR_logreg.csv", index=False)

    # ---------------- Experiment 2: segment level with additional physiology ----------------
    log("segment level")
    ecg = loader.load("ecg.csv", include_heavy=True)
    H = hrv_table(ecg)
    nsr = H[H.device_class == "NSR"]
    dev = (nsr["ecg_hr_derived"] - nsr["device_hr"]).dropna()
    RESULTS["ecg_detector"] = {
        "n_recordings": int(len(H)), "n_usable": int(H.ecg_usable.sum()),
        "n_with_invalid_tokens": int((H.ecg_n_invalid_samples > 0).sum()),
        "vs_device_hr_n": int(len(dev)), "mae_bpm": float(dev.abs().mean()), "bias_bpm": float(dev.mean()),
        "loa_low": float(dev.mean() - 1.96 * dev.std(ddof=1)), "loa_high": float(dev.mean() + 1.96 * dev.std(ddof=1)),
        "max_abs_bpm": float(dev.abs().max()),
        "median_by_phase": H.groupby("phase")[["ecg_hr_derived", "ecg_sdnn", "ecg_rmssd"]].median().to_dict(),
    }
    H[["username", "phase", "device_hr", "ecg_hr_derived", "device_class", "ecg_usable"]].to_csv(OUT / "ecg_detector_check.csv", index=False)
    S2 = S.merge(H[["username", "phase"] + HRV], on=["username", "phase"], how="left")
    ys, gs_ = S2["label"].to_numpy(), S2["username"]
    segsets = {
        "A_absolute": HR,
        "AR_absolute_plus_relative": HR + REL,
        "AR+EDA": HR + REL + EDA,
        "AR+ECG_HRV": HR + REL + HRV,
        "AR+EDA+ECG_HRV": HR + REL + EDA + HRV,
        "EDA+ECG_HRV_only": EDA + HRV,
    }
    seg, s_preds, s_pp = {}, {}, {}
    for fs_name, cols in segsets.items():
        X = S2[cols].astype(float)
        for m in MODELS:
            pred, score, info = grouped_cv(X, ys, gs_, m)
            key = f"{fs_name}|{m}"
            seg[key] = {**metrics(ys, pred, score), "n_participants": int(gs_.nunique()), "n_samples": int(len(ys)),
                        "n_missing_values_imputed": int(X.isna().sum().sum()), "features": cols}
            s_preds[key] = pred
            s_pp[key] = per_participant_ba(ys, pred, gs_)
    sb = boot_ci(ys, s_preds, gs_)
    for key in seg:
        seg[key]["ba_ci95"] = ci(sb[key])
    scomp, sp = {}, {}
    for m in REAL:
        for other in ("AR_absolute_plus_relative", "AR+EDA", "AR+ECG_HRV", "AR+EDA+ECG_HRV"):
            c = wilcoxon(s_pp[f"A_absolute|{m}"], s_pp[f"{other}|{m}"])
            diff = sb[f"{other}|{m}"] - sb[f"A_absolute|{m}"]
            c.update(pooled_ba_diff_ci95=ci(diff))
            scomp[f"{other} vs A_absolute|{m}"] = c
            sp[f"{other} vs A_absolute|{m}"] = c["p"]
    for k, adj in holm(sp).items():
        scomp[k]["p_holm"] = adj
    RESULTS["segment"] = seg
    RESULTS["segment_comparisons"] = scomp
    RESULTS["segment_phase_means"] = S2.groupby("phase")[HR + ["hr_mean_delta"] + EDA + HRV].mean().to_dict()
    pr = S2.pivot(index="username", columns="phase", values=HRV + EDA)
    RESULTS["segment_paired_tests"] = {}
    for c in HRV + EDA:
        d = pr[(c, "stress")] - pr[(c, "relax")]
        d = d.dropna()
        RESULTS["segment_paired_tests"][c] = {"n": int(len(d)), "median_diff": float(d.median()), "p": float(stats.wilcoxon(d).pvalue)}

    # ---------------- Secondary regression targets (app pipeline, same folds) ----------------
    log("regression targets")
    reg = {}
    for tgt, models in (("stai_state", ["dummy", "ridge", "random_forest", "svr"]), ("pss14", ["dummy", "ridge", "random_forest", "svr"])):
        for e in ("A", "B", "C"):
            for m in models:
                r = evaluation.cross_validate(tgt, e, m)
                reg[f"{tgt}|{e}|{m}"] = {k: r["metrics"][k] for k in ("mae", "rmse", "r2", "pearson_r")} | {
                    "n_participants": r["n_participants"], "n_samples": r["n_samples"]}
    RESULTS["regression"] = reg

    RESULTS["runtime_seconds"] = round(time.time() - t0, 1)
    (OUT / "results.json").write_text(json.dumps(RESULTS, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    log(f"done in {RESULTS['runtime_seconds']} s -> {OUT / 'results.json'}")


if __name__ == "__main__":
    main()
