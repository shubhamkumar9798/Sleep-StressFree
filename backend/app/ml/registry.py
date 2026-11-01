"""Training of final models, persistence with joblib, and exploratory prediction.

A saved bundle contains the fitted Pipeline (imputer + scaler + model) together
with its feature schema, target definition, training ranges and the dataset
fingerprint, so a stale or incompatible model is detected before predicting.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import sklearn

from .. import config, db
from ..dataset import loader, qol
from .definitions import FEATURE_SCHEMA_VERSION, TARGETS, features_for
from .evaluation import ExperimentError, cross_validate, make_estimator, prepare_xy, store_run

# Targets that can be predicted from a heart-rate sequence typed in by the user.
INTERACTIVE_TARGETS = {"phase_window", "phase_segment", "stai_state"}


def train_final(target: str, experiment: str, model: str) -> dict:
    """Cross-validate (for honest metrics) and then fit on all eligible data for the prediction interface."""
    if target not in TARGETS:
        raise ExperimentError(f"Unknown target '{target}'.", 404)
    cv = cross_validate(target, experiment, model)
    run_id = store_run(cv, group_id=f"train-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    X, y, groups, feats = prepare_xy(target, experiment)
    est = make_estimator(TARGETS[target]["task"], model)
    est.fit(X, y)

    ranges = {
        f: {
            "min": float(np.nanmin(X[f])), "max": float(np.nanmax(X[f])),
            "p01": float(np.nanpercentile(X[f], 1)), "p99": float(np.nanpercentile(X[f], 99)),
        }
        for f in feats
    }
    importances = None
    inner = est.named_steps["model"]
    inner = getattr(inner, "regressor_", inner)
    if hasattr(inner, "feature_importances_"):
        importances = dict(sorted(zip(feats, map(float, inner.feature_importances_)), key=lambda kv: -kv[1]))
    elif hasattr(inner, "coef_"):
        coefs = np.ravel(inner.coef_)
        importances = dict(sorted(zip(feats, map(float, coefs)), key=lambda kv: -abs(kv[1])))

    bundle = {
        "pipeline": est,
        "target": target,
        "target_definition": TARGETS[target],
        "experiment": experiment,
        "model": model,
        "feature_names": feats,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "training_ranges": ranges,
        "dataset_fingerprint": loader.fingerprint(),
        "preprocessing": config.settings.preprocessing.__dict__,
        "sklearn_version": sklearn.__version__,
        "n_participants": int(groups.nunique()),
        "n_samples": int(len(y)),
        "cv_run_id": run_id,
        "cv_metrics": cv["metrics"],
        "importances": importances,
        "created_at": db.now_iso(),
    }
    out_dir = config.settings.artifact_dir / "models"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{target}_{experiment}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.joblib"
    joblib.dump(bundle, path)
    with db.connect() as conn:
        conn.execute("UPDATE trained_models SET is_active=0 WHERE target=?", (target,))
        cur = conn.execute(
            """INSERT INTO trained_models (target, experiment, model, artifact_path, feature_names_json, cv_run_id,
               dataset_fingerprint, is_active, created_at) VALUES (?,?,?,?,?,?,?,1,?)""",
            (target, experiment, model, str(path), json.dumps(feats), run_id, bundle["dataset_fingerprint"], bundle["created_at"]),
        )
        model_id = int(cur.lastrowid)
    return {"model_id": model_id, **_public(bundle)}


def _public(bundle: dict) -> dict:
    return {k: v for k, v in bundle.items() if k != "pipeline"}


def list_models() -> list[dict]:
    with db.connect() as conn:
        rows = db.rows_to_dicts(conn.execute("SELECT * FROM trained_models ORDER BY id DESC").fetchall())
    current_fp = loader.fingerprint() if loader.is_available() else None
    for r in rows:
        r["feature_names"] = json.loads(r.pop("feature_names_json"))
        r["artifact_exists"] = Path(r["artifact_path"]).exists()
        r["dataset_matches_current"] = r["dataset_fingerprint"] == current_fp
        r["compatible"], r["incompatibility"] = _check_compat(r["target"], r["experiment"], r["feature_names"])
        r["artifact_file"] = Path(r["artifact_path"]).name
        r.pop("artifact_path")
    return rows


def _check_compat(target: str, experiment: str, feature_names: list[str]) -> tuple[bool, str | None]:
    try:
        current = features_for(target, experiment)
    except (ValueError, KeyError) as exc:
        return False, str(exc)
    if current != feature_names:
        return False, "The feature schema changed since this model was trained. Retrain it."
    return True, None


def load_bundle(model_id: int) -> dict:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM trained_models WHERE id=?", (model_id,)).fetchone()
    if not row:
        raise ExperimentError(f"Model {model_id} not found.", 404)
    path = Path(row["artifact_path"])
    if not path.exists():
        raise ExperimentError("The model artifact file is missing. Retrain the model.", 409)
    bundle = joblib.load(path)
    if bundle.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise ExperimentError("Model was saved with an older feature schema version. Retrain it.", 409)
    ok, why = _check_compat(bundle["target"], bundle["experiment"], bundle["feature_names"])
    if not ok:
        raise ExperimentError(why or "Incompatible model.", 409)
    if bundle.get("sklearn_version") != sklearn.__version__:
        bundle.setdefault("warnings", []).append(
            f"Model saved with scikit-learn {bundle.get('sklearn_version')}, running {sklearn.__version__}."
        )
    bundle["model_id"] = model_id
    return bundle


def build_features(bundle: dict, inputs: dict) -> tuple[dict[str, float], list[str]]:
    """Compute the model's features from user-entered sequences using the training code path."""
    target = bundle["target"]
    if target not in INTERACTIVE_TARGETS:
        raise ExperimentError(
            "This participant-level model needs a complete relax + stress session per person and cannot be used "
            "from manually entered values.", 422,
        )
    pp = config.settings.preprocessing
    hr = np.asarray(inputs.get("hr_values") or [], dtype=float)
    secs = inputs.get("hr_seconds")
    errors: list[str] = []
    if len(hr) == 0:
        raise ExperimentError("Heart-rate values are required.", 422)
    if np.any(np.isnan(hr)) or np.any(hr < pp.hr_valid_min) or np.any(hr > pp.hr_valid_max):
        raise ExperimentError(f"Every heart-rate value must be between {pp.hr_valid_min:.0f} and {pp.hr_valid_max:.0f} bpm.", 422)
    duration = float(inputs.get("duration_seconds") or (pp.window_seconds if target == "phase_window" else pp.segment_minutes * 60))
    if secs is not None:
        secs = np.asarray(secs, dtype=float)
        if len(secs) != len(hr):
            raise ExperimentError("hr_seconds must have the same length as hr_values.", 422)
        if np.any(np.diff(secs) <= 0):
            raise ExperimentError("hr_seconds must be strictly increasing.", 422)
    else:
        secs = np.linspace(0, duration, len(hr), endpoint=False)
    min_n = pp.min_samples_per_window if target == "phase_window" else int(pp.min_samples_per_window * pp.segment_minutes)
    if len(hr) < min_n:
        raise ExperimentError(
            f"At least {min_n} heart-rate readings are required for this model (the training windows had at least that many). "
            "A single reading is not enough.", 422,
        )
    feats = qol.hr_features(hr, secs)
    needed = bundle["feature_names"]
    if any(f in needed for f in qol.PERSONAL_FEATURES):
        cal = np.asarray(inputs.get("calibration_values") or [], dtype=float)
        if len(cal) < pp.min_calibration_samples:
            raise ExperimentError(
                f"This personalised model needs at least {pp.min_calibration_samples} resting calibration readings "
                f"(about {pp.calibration_minutes:.0f} minutes at rest).", 422,
            )
        if np.any(cal < pp.hr_valid_min) or np.any(cal > pp.hr_valid_max):
            raise ExperimentError("Calibration values must be physiological heart rates.", 422)
        feats.update(qol.personal_features(feats, qol.baseline_stats(cal)))
    for f in qol.MULTIMODAL_FEATURES:
        if f in needed:
            v = (inputs.get("extra_features") or {}).get(f)
            if v is None:
                errors.append(f"'{f}' is required by this model.")
            else:
                feats[f] = float(v)
    if errors:
        raise ExperimentError(" ".join(errors), 422)
    missing = [f for f in needed if f not in feats or feats[f] is None or np.isnan(feats[f])]
    if missing:
        raise ExperimentError(f"Could not compute features {missing} from the input (e.g. too few readings).", 422)
    return {f: float(feats[f]) for f in needed}, []


def predict(model_id: int, inputs: dict) -> dict:
    bundle = load_bundle(model_id)
    feats, _ = build_features(bundle, inputs)
    import pandas as pd

    X = pd.DataFrame([feats], columns=bundle["feature_names"])
    est = bundle["pipeline"]
    tdef = bundle["target_definition"]
    out_of_range = []
    for f, v in feats.items():
        r = bundle["training_ranges"][f]
        if v < r["min"] or v > r["max"]:
            out_of_range.append({"feature": f, "value": v, "training_min": r["min"], "training_max": r["max"]})
    result: dict[str, Any] = {
        "model_id": model_id,
        "target": bundle["target"],
        "target_name": tdef["name"],
        "experiment": bundle["experiment"],
        "model": bundle["model"],
        "features": feats,
        "within_training_range": not out_of_range,
        "out_of_range_features": out_of_range,
        "cv_metrics": bundle["cv_metrics"],
        "trained_on": f"QoL_Stress (Fitbit) - {bundle['n_participants']} participants, {bundle['n_samples']} samples",
        "input_source": inputs.get("input_source", "manual entry (user-provided values, not verified device data)"),
        "warnings": list(bundle.get("warnings", [])),
        "disclaimer": "Experimental research estimate, not a medical or psychological diagnosis. "
        "The model was trained on Fitbit data from a lab protocol and has not been validated on Amazfit or everyday data.",
    }
    if bundle["dataset_fingerprint"] != (loader.fingerprint() if loader.is_available() else None):
        result["warnings"].append("The dataset files differ from those used to train this model.")
    if tdef["task"] == "classification":
        pred = int(est.predict(X)[0])
        result["prediction"] = tdef["classes"][pred]
        if hasattr(est, "predict_proba") and hasattr(est.named_steps["model"], "predict_proba"):
            proba = est.predict_proba(X)[0]
            result["probabilities"] = {tdef["classes"][int(c)]: float(p) for c, p in zip(est.classes_, proba)}
        elif hasattr(est.named_steps["model"], "decision_function"):
            result["decision_value"] = float(est.decision_function(X)[0])
        result["interpretation"] = (
            f"Heart-rate pattern resembles the '{result['prediction']}' phase of the lab protocol more than the other phase. "
            "This is not a measurement of how stressed a person feels."
        )
    else:
        result["prediction"] = float(est.predict(X)[0])
        result["interpretation"] = (
            f"Estimated {tdef['name']} of {result['prediction']:.1f}. Cross-validated MAE on unseen participants was "
            f"{bundle['cv_metrics'].get('mae', float('nan')):.1f} points, so the true value may differ substantially."
        )
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO prediction_log (model_id, input_source, inputs_json, output_json, created_at) VALUES (?,?,?,?,?)",
            (model_id, result["input_source"], db.dumps({k: v for k, v in inputs.items()}), db.dumps(result), db.now_iso()),
        )
    return result
