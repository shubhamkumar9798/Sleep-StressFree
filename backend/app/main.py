"""FastAPI application entry point.

Run (from the backend folder):
    .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
Interactive API docs: http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, db
from .dataset.loader import DatasetError
from .imports.ocr import OcrUnavailable
from .imports.records import RecordError
from .ml.evaluation import ExperimentError
from .routers import data_routes, dataset_routes, ml_routes

@asynccontextmanager
async def lifespan(_: FastAPI):
    config.ensure_dirs()
    db.init_db()
    yield


app = FastAPI(
    title="Stress Detection in Students Using Wearable Data - Research API",
    version="1.0.0",
    description="Research prototype. Not a medical device. No authentication is implemented: run it locally only.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.settings.frontend_origin],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


def _error(status: int, message: str, details=None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message, "details": details})


@app.exception_handler(DatasetError)
async def _dataset_error(_: Request, exc: DatasetError):
    return _error(exc.status_code, exc.message, exc.details)


@app.exception_handler(ExperimentError)
async def _experiment_error(_: Request, exc: ExperimentError):
    return _error(exc.status_code, exc.message)


@app.exception_handler(RecordError)
async def _record_error(_: Request, exc: RecordError):
    return _error(exc.status_code, exc.message, exc.details)


@app.exception_handler(OcrUnavailable)
async def _ocr_error(_: Request, exc: OcrUnavailable):
    return _error(503, str(exc))


@app.get("/api/health")
def health():
    return {"status": "ok"}


app.include_router(dataset_routes.router)
app.include_router(ml_routes.router)
app.include_router(data_routes.router)
