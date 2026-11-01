"""Experiments, model training/evaluation, comparison and prediction endpoints."""
from __future__ import annotations

import csv
import io
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .. import jobs
from ..dataset import loader, qol
from ..ml import evaluation, registry
from ..ml.definitions import EXPERIMENTS, TARGETS, experiment_catalog
from .dataset_routes import clean

router = APIRouter(prefix="/api")


@router.get("/experiments/catalog")
def catalog():
    return {"targets": TARGETS, "experiments": EXPERIMENTS, "catalog": experiment_catalog(),
            "models": evaluation.MODEL_NAMES}


class RunRequest(BaseModel):
    targets: list[str] = Field(default_factory=lambda: list(TARGETS))
    models: list[str] | None = None


def _require_dataset():
    if not loader.is_available():
        raise HTTPException(409, "The QoL_Stress dataset was not found. Training is disabled until it is installed (see Settings).")


@router.post("/experiments/run")
def run_experiments(req: RunRequest):
    _require_dataset()
    unknown = [t for t in req.targets if t not in TARGETS]
    if unknown or not req.targets:
        raise HTTPException(422, f"Unknown or empty targets: {unknown}")
    qol.build()  # fail fast with a clear error if preprocessing cannot run
    try:
        job = jobs.submit("experiments", lambda progress: evaluation.run_experiments(req.targets, req.models, progress))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return job


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found (jobs are kept in memory until the server restarts).")
    return clean({k: v for k, v in job.items() if k != "traceback"})


@router.get("/experiments/results")
def results(target: str | None = None):
    runs = evaluation.load_runs()
    if target:
        runs = [r for r in runs if r["target"] == target]
    return clean({"runs": runs, "comparisons": evaluation.comparison_table(runs)})


@router.get("/experiments/results.csv")
def results_csv():
    runs = evaluation.load_runs()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["run_id", "created_at", "target", "task", "experiment", "model", "n_participants", "n_samples",
                "validation", "features", "balanced_accuracy", "macro_f1", "precision_macro", "recall_macro", "roc_auc",
                "mae", "rmse", "r2", "dataset_fingerprint", "dataset_matches_current"])
    for r in runs:
        m = r["metrics"]
        w.writerow([r["id"], r["created_at"], r["target"], r["task"], r["experiment"], r["model"], r["n_participants"],
                    r["n_samples"], r["config"].get("validation"), " ".join(r["config"].get("features", [])),
                    *[m.get(k) for k in ("balanced_accuracy", "macro_f1", "precision_macro", "recall_macro", "roc_auc", "mae", "rmse", "r2")],
                    r["dataset_fingerprint"], r["dataset_matches_current"]])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=experiment_results.csv"})


class TrainRequest(BaseModel):
    target: str
    experiment: Literal["A", "B", "C", "D"]
    model: str


@router.post("/models/train")
def train(req: TrainRequest):
    _require_dataset()
    if req.target not in TARGETS:
        raise HTTPException(422, f"Unknown target '{req.target}'.")
    if req.model not in evaluation.MODEL_NAMES[TARGETS[req.target]["task"]]:
        raise HTTPException(422, f"Model '{req.model}' is not valid for this target.")
    evaluation.prepare_xy(req.target, req.experiment)  # validates experiment availability synchronously
    try:
        job = jobs.submit("train", lambda progress: registry.train_final(req.target, req.experiment, req.model))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return job


@router.get("/models")
def models():
    return clean({"models": registry.list_models(), "interactive_targets": sorted(registry.INTERACTIVE_TARGETS)})


@router.get("/models/{model_id}")
def model_detail(model_id: int):
    b = registry.load_bundle(model_id)
    return clean(registry._public(b))


class PredictRequest(BaseModel):
    model_id: int
    hr_values: list[float]
    hr_seconds: list[float] | None = None
    duration_seconds: float | None = Field(default=None, gt=0, le=3600)
    calibration_values: list[float] | None = None
    extra_features: dict[str, float] | None = None
    input_source: Literal["manual entry", "pasted from CSV", "screenshot-derived"] = "manual entry"


@router.post("/predict")
def predict(req: PredictRequest) -> dict[str, Any]:
    body = req.model_dump()
    body["input_source"] = f"{req.input_source} (user-provided values, not verified device measurements)"
    return clean(registry.predict(req.model_id, body))
