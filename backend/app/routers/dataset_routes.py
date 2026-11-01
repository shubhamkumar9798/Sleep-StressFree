"""Dataset status, schema inspection, preprocessing and baseline endpoints."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import jobs
from ..dataset import loader, qol, schema
from ..imports import records
from ..ml import evaluation, registry
from ..ml.definitions import FEATURE_DOCS, TARGETS, experiment_catalog

router = APIRouter(prefix="/api")


def clean(obj):
    """Make pandas/numpy values JSON-safe (NaN -> None)."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def short(u: str) -> str:
    return u[:8]


def dataset_info() -> dict:
    return {
        "name": schema.DATASET_NAME, "version": schema.DATASET_VERSION, "url": schema.DATASET_URL,
        "license": schema.DATASET_LICENSE, "authors": schema.DATASET_AUTHORS, "device_note": schema.DEVICE_NOTE,
        "directory": str(loader.dataset_dir()),
    }


@router.get("/dataset/status")
def dataset_status():
    files = loader.file_status()
    present = [f for f in files if f["present"]]
    status = {"dataset": dataset_info(), "files": files, "available": bool(present),
              "complete": len(present) == len(files)}
    if present:
        status["fingerprint"] = loader.fingerprint()
    if not present:
        status["setup_message"] = (
            f"No QoL_Stress files were found in {loader.dataset_dir()}. Download the dataset from {schema.DATASET_URL} "
            "and either place the CSV files in data/qol_stress/ or set QOL_STRESS_DIR in backend/.env."
        )
    return status


@router.get("/dataset/files/{name}/validate")
def validate(name: str):
    return clean(loader.validate_file(name))


@router.get("/dataset/files/{name}/preview")
def preview(name: str, n: int = 10):
    return clean(loader.preview(name, max(1, min(n, 100))))


@router.get("/dataset/hr-distribution")
def hr_distribution():
    """Histogram of clean per-second heart rate by reconstructed phase (eligible participants)."""
    p = qol.build()
    if not len(p.windows):
        return {"bins": []}
    bins = np.arange(40, 141, 5)
    out = []
    for phase in ("relax", "stress"):
        vals = p.windows.loc[p.windows["phase"] == phase, "hr_mean"].to_numpy()
        counts, _ = np.histogram(vals, bins=bins)
        out.append((phase, counts))
    return {"bins": [{"bin": f"{int(b)}-{int(b + 5)}", "relax": int(out[0][1][i]), "stress": int(out[1][1][i])}
                     for i, b in enumerate(bins[:-1])], "unit": "window mean HR (bpm)"}


class DatasetDir(BaseModel):
    path: str | None = None


@router.post("/dataset/directory")
def set_directory(body: DatasetDir):
    if jobs.is_running():
        raise HTTPException(409, "A training job is running; try again when it finishes.")
    loader.set_dataset_dir(body.path)
    return dataset_status()


@router.get("/preprocessing/summary")
def preprocessing_summary():
    p = qol.build()
    s = dict(p.summary)
    s["exclusions"] = [{"participant": short(e["username"]), "reasons": e["reasons"]} for e in s.get("exclusions", [])]
    s["fingerprint"] = p.fingerprint
    s["feature_docs"] = FEATURE_DOCS
    if len(p.segments):
        s["segment_means"] = p.segments.groupby("phase")[qol.HR_STAT_FEATURES + ["hr_mean_delta", "stai_score"] + qol.MULTIMODAL_FEATURES].mean().round(2).to_dict(orient="index")
    return clean(s)


@router.post("/preprocessing/run")
def preprocessing_run():
    if jobs.is_running():
        raise HTTPException(409, "A training job is running; try again when it finishes.")
    qol.clear_cache()
    return preprocessing_summary()


@router.get("/baseline/participants")
def baseline_participants():
    p = qol.build()
    pp = qol.config.settings.preprocessing
    rows = []
    for r in p.sessions.itertuples():
        seg = p.segments[p.segments["username"] == r.username].set_index("phase") if len(p.segments) else pd.DataFrame()
        rows.append({
            "participant": short(r.username),
            "username": r.username,
            "eligible": bool(r.eligible),
            "exclusion_reasons": r.exclusion_reasons,
            "calibration_samples": getattr(r, "base_n", None),
            "min_calibration_samples": pp.min_calibration_samples,
            "meets_minimum": bool((getattr(r, "base_n", 0) or 0) >= pp.min_calibration_samples),
            "baseline_median": getattr(r, "base_median", None),
            "baseline_mean": getattr(r, "base_mean", None),
            "baseline_sd": getattr(r, "base_sd", None),
            "calibration_period": [getattr(r, "calib_start", None), getattr(r, "calib_end", None)],
            "relax_windows": getattr(r, "relax_windows", None),
            "stress_windows": getattr(r, "stress_windows", None),
            "relax_segment_delta": seg.loc["relax", "hr_mean_delta"] if "relax" in seg.index else None,
            "stress_segment_delta": seg.loc["stress", "hr_mean_delta"] if "stress" in seg.index else None,
        })
    return clean({"participants": rows, "calibration_minutes": pp.calibration_minutes,
                  "note": "Calibration = first minutes of each participant's heart-rate recording (start of the relax phase). "
                          "Computed from heart rate only, without labels; these minutes are excluded from every evaluation."})


def _clock(sec):
    if sec is None or (isinstance(sec, float) and math.isnan(sec)):
        return None
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


@router.get("/baseline/participants/{username}")
def baseline_detail(username: str):
    p = qol.build()
    sess = p.sessions[p.sessions["username"] == username]
    if sess.empty:
        raise HTTPException(404, "Participant not found.")
    r = sess.iloc[0].to_dict()
    hr = p.hr[p.hr["username"] == username]
    step = max(1, len(hr) // 600)
    raw = [{"minute": (t - r.get("hr_start", t)) / 60.0, "hr": v} for t, v in zip(hr["t"].to_numpy()[::step], hr["value"].to_numpy()[::step])]
    w = p.windows[p.windows["username"] == username] if len(p.windows) else pd.DataFrame()
    marks = {k: (r[k] - r["hr_start"]) / 60.0 for k in ("calib_end", "relax_eval_end", "stai_relax_t", "stress_eval_start", "stress_eval_end", "stai_stress_t") if r.get(k) == r.get(k) and r.get(k) is not None and "hr_start" in r}
    return clean({
        "participant": short(username),
        "session": {k: (_clock(v) if k.endswith("_t") or k in ("hr_start", "hr_end") or k.startswith(("calib_", "relax_eval", "stress_eval")) else v)
                    for k, v in r.items() if k != "username"},
        "markers_minutes": marks,
        "raw_hr": raw,
        "windows": w[["minutes_from_hr_start", "phase", "hr_mean", "hr_mean_delta", "hr_std", "n_samples"]].to_dict(orient="records") if len(w) else [],
    })


@router.get("/baseline/user")
def user_baseline(participant_code: str, start: str, end: str):
    return clean(records.user_baseline(participant_code, start, end))


@router.get("/dashboard")
def dashboard():
    status = dataset_status()
    out = {"dataset": status, "user_records": records.summary(), "targets": TARGETS}
    if status["available"]:
        try:
            p = qol.build()
            pr = loader.load("participants.csv") if (loader.dataset_dir() / "participants.csv").exists() else None
            out["preprocessing"] = clean({
                "participants_total": p.summary.get("participants_total"),
                "participants_in_files": int(pr["username"].nunique()) if pr is not None else None,
                "participants_eligible": p.summary.get("participants_eligible"),
                "hr_samples": p.summary.get("hr_samples", {}).get("clean"),
                "windows_per_phase": p.summary.get("windows_per_phase"),
                "segments": p.summary.get("segments"),
                "manipulation_check": p.summary.get("manipulation_check"),
                "variables": ["Fitbit heart rate (per second / per minute)", "EDA skin conductance (per phase)",
                              "ECG device heart rate (per phase)", "STAI state anxiety (per phase)", "PSS-14 (per participant)"],
            })
        except loader.DatasetError as exc:
            out["preprocessing_error"] = exc.message
    out["models"] = registry.list_models()
    runs = evaluation.load_runs()
    out["latest_runs"] = [{k: r[k] for k in ("id", "target", "experiment", "model", "metrics", "n_participants", "n_samples", "created_at", "dataset_matches_current")} for r in runs[:50]]
    out["experiments"] = experiment_catalog()
    return clean(out)
