"""Participant-wise cross-validation of the experiments.

Protocol
--------
* Participants (never individual rows) are assigned to K folds with a fixed seed.
  The same fold assignment is used for every experiment and model of a target,
  so comparisons are paired and fair.
* Imputation and scaling are inside a scikit-learn Pipeline, so they are fitted
  on the training participants of each fold only.
* Models use fixed, pre-declared hyper-parameters. No tuning is done on the
  test folds.
* Metrics are computed from out-of-fold predictions (each row is predicted by
  a model that never saw that participant), plus per-fold values.
"""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd
import sklearn
from scipy import stats
from sklearn.compose import TransformedTargetRegressor
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR

from .. import config, db
from ..dataset import loader, qol
from .definitions import EXPERIMENTS, TARGETS, features_for

MIN_PARTICIPANTS = 5


class ExperimentError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


MODEL_NAMES = {
    "classification": {
        "dummy": "Majority-class baseline",
        "logistic_regression": "Logistic Regression",
        "random_forest": "Random Forest",
        "svm": "Support Vector Machine (RBF)",
    },
    "regression": {
        "dummy": "Mean baseline",
        "ridge": "Ridge Regression",
        "random_forest": "Random Forest Regressor",
        "svr": "Support Vector Regression (RBF)",
    },
}


def make_estimator(task: str, model: str):
    seed = config.settings.random_seed
    if task == "classification":
        est = {
            "dummy": lambda: DummyClassifier(strategy="most_frequent"),
            "logistic_regression": lambda: LogisticRegression(class_weight="balanced", max_iter=2000),
            "random_forest": lambda: RandomForestClassifier(
                n_estimators=300, min_samples_leaf=5, class_weight="balanced", random_state=seed, n_jobs=-1
            ),
            "svm": lambda: SVC(kernel="rbf", C=1.0, gamma="scale", class_weight="balanced", probability=False),
        }
    else:
        est = {
            "dummy": lambda: DummyRegressor(strategy="mean"),
            "ridge": lambda: Ridge(alpha=1.0),
            "random_forest": lambda: RandomForestRegressor(n_estimators=300, min_samples_leaf=5, random_state=seed, n_jobs=-1),
            "svr": lambda: SVR(kernel="rbf", C=1.0, epsilon=0.1),
        }
    if model not in est:
        raise ExperimentError(f"Model '{model}' is not available for {task}. Choose from {sorted(est)}.")
    inner = est[model]()
    if task == "regression":
        inner = TransformedTargetRegressor(regressor=inner, transformer=StandardScaler())
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", inner)])


def get_table(target: str) -> pd.DataFrame:
    prepared = qol.build()
    table = getattr(prepared, TARGETS[target]["table"])
    if table is None or len(table) == 0:
        raise ExperimentError("No eligible rows were produced by preprocessing; check the dataset status page.", 409)
    return table


def fold_assignment(participants: list[str], k: int, seed: int) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    order = rng.permutation(sorted(participants))
    return {p: i % k for i, p in enumerate(order)}


def prepare_xy(target: str, experiment: str) -> tuple[pd.DataFrame, pd.Series, pd.Series, list[str]]:
    tdef = TARGETS[target]
    try:
        feats = features_for(target, experiment)
    except ValueError as reason:
        raise ExperimentError(f"Experiment {experiment} is not supported for target '{target}': {reason}", 422)
    table = get_table(target)
    y = table[tdef["y"]]
    keep = y.notna()
    table = table[keep]
    missing_cols = [f for f in feats if f not in table.columns]
    if missing_cols:
        raise ExperimentError(f"Features {missing_cols} are not available in the prepared data (missing source file?).", 409)
    X = table[feats].astype(float)
    if tdef["y"] in X.columns:
        raise ExperimentError("Target leakage: target column found in the feature matrix.", 500)
    if X.isna().all(axis=0).any():
        empty = list(X.columns[X.isna().all(axis=0)])
        raise ExperimentError(f"Features {empty} are entirely missing; the experiment cannot run.", 409)
    return X, table[tdef["y"]], table["username"], feats


def _scores(est, X) -> np.ndarray | None:
    model = est.named_steps["model"]
    if isinstance(model, DummyClassifier):
        return None
    if hasattr(est, "predict_proba") and hasattr(model, "predict_proba"):
        return est.predict_proba(X)[:, 1]
    if hasattr(model, "decision_function"):
        return est.decision_function(X)
    return None


def cross_validate(target: str, experiment: str, model: str) -> dict[str, Any]:
    tdef = TARGETS[target]
    task = tdef["task"]
    X, y, groups, feats = prepare_xy(target, experiment)
    participants = sorted(groups.unique())
    if len(participants) < MIN_PARTICIPANTS:
        raise ExperimentError(f"Only {len(participants)} eligible participants; at least {MIN_PARTICIPANTS} are required.", 409)
    k = min(config.settings.cv_folds, len(participants))
    folds = fold_assignment(participants, k, config.settings.random_seed)
    fold_of_row = groups.map(folds).to_numpy()

    oof_pred = np.full(len(y), np.nan, dtype=float)
    oof_score = np.full(len(y), np.nan, dtype=float)
    fold_info = []
    for f in range(k):
        test = fold_of_row == f
        train = ~test
        train_p, test_p = set(groups[train]), set(groups[test])
        overlap = train_p & test_p
        if overlap:
            raise ExperimentError(f"Participant overlap detected between train and test in fold {f}.", 500)
        info = {
            "fold": f,
            "n_train": int(train.sum()),
            "n_test": int(test.sum()),
            "n_train_participants": len(train_p),
            "n_test_participants": len(test_p),
            "participant_overlap": 0,
        }
        if task == "classification":
            counts = y[train].value_counts().to_dict()
            info["train_class_counts"] = {tdef["classes"][int(c)]: int(n) for c, n in counts.items()}
            if len(counts) < 2 or min(counts.values()) < 2:
                raise ExperimentError(f"Fold {f} has insufficient class counts in training data: {counts}.", 409)
        est = make_estimator(task, model)
        est.fit(X[train], y[train])
        oof_pred[test] = est.predict(X[test])
        if task == "classification":
            s = _scores(est, X[test])
            if s is not None:
                oof_score[test] = s
            info["balanced_accuracy"] = float(balanced_accuracy_score(y[test], oof_pred[test]))
            info["macro_f1"] = float(f1_score(y[test], oof_pred[test], average="macro", zero_division=0))
        else:
            info["mae"] = float(mean_absolute_error(y[test], oof_pred[test]))
        fold_info.append(info)

    yt = y.to_numpy()
    metrics: dict[str, Any] = {}
    details: dict[str, Any] = {"folds": fold_info}
    per_participant: dict[str, float] = {}
    if task == "classification":
        yp = oof_pred.astype(int)
        labels = [0, 1]
        metrics.update(
            balanced_accuracy=float(balanced_accuracy_score(yt, yp)),
            macro_f1=float(f1_score(yt, yp, average="macro", zero_division=0)),
            precision_macro=float(precision_score(yt, yp, average="macro", zero_division=0)),
            recall_macro=float(recall_score(yt, yp, average="macro", zero_division=0)),
            roc_auc=float(roc_auc_score(yt, oof_score)) if not np.isnan(oof_score).any() else None,
            fold_balanced_accuracy_mean=float(np.mean([f["balanced_accuracy"] for f in fold_info])),
            fold_balanced_accuracy_sd=float(np.std([f["balanced_accuracy"] for f in fold_info], ddof=1)) if k > 1 else None,
        )
        details["confusion_matrix"] = confusion_matrix(yt, yp, labels=labels).tolist()
        details["class_labels"] = tdef["classes"]
        details["classification_report"] = classification_report(
            yt, yp, labels=labels, target_names=tdef["classes"], output_dict=True, zero_division=0
        )
        details["class_counts"] = {tdef["classes"][int(c)]: int(n) for c, n in y.value_counts().items()}
        for p, idx in groups.groupby(groups).groups.items():
            pos = groups.index.get_indexer(idx)
            per_participant[p] = float(np.mean(yp[pos] == yt[pos]) if len(set(yt[pos])) < 2 else balanced_accuracy_score(yt[pos], yp[pos]))
        details["per_participant_metric"] = "balanced accuracy (accuracy if the participant has one class)"
    else:
        metrics.update(
            mae=float(mean_absolute_error(yt, oof_pred)),
            rmse=float(np.sqrt(mean_squared_error(yt, oof_pred))),
            r2=float(r2_score(yt, oof_pred)),
            pearson_r=float(stats.pearsonr(yt, oof_pred)[0]) if np.std(oof_pred) > 0 else None,
            fold_mae_mean=float(np.mean([f["mae"] for f in fold_info])),
            fold_mae_sd=float(np.std([f["mae"] for f in fold_info], ddof=1)) if k > 1 else None,
            target_mean=float(np.mean(yt)),
            target_sd=float(np.std(yt, ddof=1)),
        )
        details["points"] = [{"actual": float(a), "predicted": float(b)} for a, b in zip(yt, oof_pred)]
        for p, idx in groups.groupby(groups).groups.items():
            pos = groups.index.get_indexer(idx)
            per_participant[p] = float(np.mean(np.abs(yt[pos] - oof_pred[pos])))
        details["per_participant_metric"] = "mean absolute error"
    details["per_participant"] = per_participant
    n_imputed = int(X.isna().sum().sum())
    details["n_missing_feature_values_imputed"] = n_imputed
    details["missing_by_feature"] = {c: int(n) for c, n in X.isna().sum().items() if n}

    return {
        "target": target,
        "experiment": experiment,
        "model": model,
        "task": task,
        "n_participants": len(participants),
        "n_samples": int(len(y)),
        "features": feats,
        "metrics": metrics,
        "details": details,
        "config": {
            "validation": f"{k}-fold participant-wise cross-validation (GroupKFold-style, seed {config.settings.random_seed}); "
            "metrics from out-of-fold predictions",
            "k_folds": k,
            "seed": config.settings.random_seed,
            "estimator": repr(make_estimator(task, model)),
            "sklearn_version": sklearn.__version__,
            "preprocessing": config.settings.preprocessing.__dict__,
            "fold_assignment": folds,
            "hyperparameter_tuning": "none (fixed, pre-declared hyper-parameters)",
        },
    }


def store_run(result: dict, group_id: str) -> int:
    with db.connect() as conn:
        cur = conn.execute(
            """INSERT INTO experiment_runs (group_id, target, experiment, model, task, n_participants, n_samples,
               config_json, metrics_json, details_json, dataset_fingerprint, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                group_id, result["target"], result["experiment"], result["model"], result["task"],
                result["n_participants"], result["n_samples"],
                db.dumps({**result["config"], "features": result["features"]}),
                db.dumps(result["metrics"]), db.dumps(result["details"]),
                loader.fingerprint(), db.now_iso(),
            ),
        )
        return int(cur.lastrowid)


def paired_comparison(base: dict, other: dict, task: str) -> dict | None:
    """Wilcoxon signed-rank test on per-participant metrics (same participants, same folds)."""
    a, b = base["details"]["per_participant"], other["details"]["per_participant"]
    common = sorted(set(a) & set(b))
    if len(common) < 6:
        return None
    da = np.array([a[p] for p in common])
    dbv = np.array([b[p] for p in common])
    diff = dbv - da  # positive = other higher
    better_if_higher = task == "classification"
    res: dict[str, Any] = {
        "n_participants": len(common),
        "mean_difference": float(diff.mean()),
        "metric": base["details"]["per_participant_metric"],
        "higher_is_better": better_if_higher,
    }
    if np.allclose(diff, 0):
        res.update(statistic=None, p_value=1.0)
    else:
        w = stats.wilcoxon(dbv, da, zero_method="wilcox")
        res.update(statistic=float(w.statistic), p_value=float(w.pvalue))
    return res


def run_experiments(targets: list[str], models: list[str] | None = None, progress=None) -> dict:
    """Run every available experiment for the given targets and store the results."""
    group_id = uuid.uuid4().hex[:12]
    summary: dict[str, Any] = {"group_id": group_id, "runs": [], "skipped": []}
    jobs = []
    for t in targets:
        task = TARGETS[t]["task"]
        ms = models or list(MODEL_NAMES[task])
        for e in EXPERIMENTS:
            try:
                features_for(t, e)
            except ValueError as reason:
                summary["skipped"].append({"target": t, "experiment": e, "reason": str(reason)})
                continue
            for m in ms:
                if m in MODEL_NAMES[task]:
                    jobs.append((t, e, m))
    for i, (t, e, m) in enumerate(jobs):
        if progress:
            progress(i, len(jobs), f"{t} / {e} / {m}")
        try:
            res = cross_validate(t, e, m)
            run_id = store_run(res, group_id)
            summary["runs"].append({"id": run_id, "target": t, "experiment": e, "model": m, "metrics": res["metrics"]})
        except ExperimentError as exc:
            summary["skipped"].append({"target": t, "experiment": e, "model": m, "reason": exc.message})
    if progress:
        progress(len(jobs), len(jobs), "done")
    return summary


def load_runs(group_id: str | None = None, latest_only: bool = True) -> list[dict]:
    with db.connect() as conn:
        if group_id:
            rows = conn.execute("SELECT * FROM experiment_runs WHERE group_id=? ORDER BY id", (group_id,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM experiment_runs ORDER BY id DESC").fetchall()
    import json

    runs = []
    seen = set()
    for r in rows:
        d = dict(r)
        key = (d["target"], d["experiment"], d["model"])
        if latest_only and not group_id:
            if key in seen:
                continue
            seen.add(key)
        d["config"] = json.loads(d.pop("config_json"))
        d["metrics"] = json.loads(d.pop("metrics_json"))
        d["details"] = json.loads(d.pop("details_json"))
        d["dataset_matches_current"] = d["dataset_fingerprint"] == (loader.fingerprint() if loader.is_available() else None)
        runs.append(d)
    return runs


def comparison_table(runs: list[dict]) -> list[dict]:
    """For each target/model, compare B and C against A on the same participants."""
    by_key = {(r["target"], r["experiment"], r["model"]): r for r in runs}
    out = []
    for (t, e, m), r in by_key.items():
        if e == "A":
            continue
        base = by_key.get((t, "A", m))
        if not base:
            continue
        same_folds = base["config"].get("fold_assignment") == r["config"].get("fold_assignment")
        cmp = paired_comparison(base, r, r["task"]) if same_folds else None
        text = _interpret(cmp, r["task"]) if cmp else "Not comparable (different participants or folds)."
        chance = by_key.get((t, e, "dummy"))
        beats = _beats_chance(r, chance) if chance else None
        if beats is False:
            text += (" Neither result is informative: this model does not outperform the trivial "
                     f"{'majority-class' if r['task'] == 'classification' else 'mean'} baseline.")
        out.append({
            "target": t, "model": m, "experiment": e, "baseline_experiment": "A",
            "same_participants_and_folds": same_folds,
            "test": cmp,
            "beats_trivial_baseline": beats,
            "interpretation": text,
        })
    return out


def _beats_chance(run: dict, dummy: dict) -> bool:
    if run["task"] == "classification":
        return run["metrics"]["balanced_accuracy"] > dummy["metrics"]["balanced_accuracy"]
    return run["metrics"]["mae"] < dummy["metrics"]["mae"]


def _interpret(cmp: dict, task: str) -> str:
    p = cmp.get("p_value")
    d = cmp["mean_difference"]
    improved = d > 0 if cmp["higher_is_better"] else d < 0
    if p is None or p >= 0.05:
        return ("No statistically reliable difference from the general model at alpha = 0.05 "
                "(exploratory, uncorrected for multiple comparisons).")
    return (f"Per-participant {cmp['metric']} is {'better' if improved else 'worse'} than the general model "
            f"(Wilcoxon p = {p:.3g}; exploratory, uncorrected for multiple comparisons).")
