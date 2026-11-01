"""User-data endpoints: manual entry, CSV import, screenshot OCR, records explorer."""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import config
from ..imports import csv_import, ocr, records

router = APIRouter(prefix="/api")


@router.get("/records/metrics")
def metrics():
    return {"metrics": records.METRICS, "sources": records.SOURCES}


class ManualEntry(BaseModel):
    participant_code: str | None = None
    recorded_at: str
    device_label: str | None = None
    measurements: dict[str, Any]
    notes: str | None = None
    allow_duplicates: bool = False


@router.post("/records/manual", status_code=201)
def manual(entry: ManualEntry):
    return records.create_manual(entry.model_dump())


@router.get("/records")
def list_records(source: str | None = None, metric: str | None = None, participant_code: str | None = None,
                 start: str | None = None, end: str | None = None, limit: int = 50, offset: int = 0):
    return records.list_records(locals())


@router.get("/records/summary")
def summary():
    return records.summary()


@router.get("/records/export.csv")
def export(source: str | None = None, metric: str | None = None, participant_code: str | None = None):
    rows = records.list_records({"source": source, "metric": metric, "participant_code": participant_code, "limit": 5000})["rows"]
    buf = io.StringIO()
    cols = ["id", "source", "device_label", "participant_code", "recorded_at", "metric", "value", "unit", "raw_value_text",
            "value_was_edited", "verified_device_measurement", "extraction_flags", "notes", "batch_id", "created_at"]
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=user_records.csv"})


@router.delete("/records/{record_id}")
def delete_record(record_id: int):
    records.delete_record(record_id)
    return {"deleted": record_id}


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: int):
    return {"deleted_batch": batch_id, "deleted_records": records.delete_batch(batch_id)}


# ---- CSV ----------------------------------------------------------------
@router.post("/imports/csv/preview")
async def csv_preview(file: UploadFile = File(...)):
    return csv_import.preview(await file.read(), file.filename or "upload.csv")


class CsvMapping(BaseModel):
    token: str
    mapping: dict[str, Any]


@router.post("/imports/csv/validate")
def csv_validate(body: CsvMapping):
    return csv_import.analyse(body.token, body.mapping, commit=False)


@router.post("/imports/csv/commit")
def csv_commit(body: CsvMapping):
    return csv_import.analyse(body.token, body.mapping, commit=True)


@router.delete("/imports/csv/{token}")
def csv_discard(token: str):
    csv_import.discard(token)
    return {"discarded": True}


# ---- Screenshot ---------------------------------------------------------
@router.get("/imports/screenshot/status")
def ocr_status():
    return {**ocr.status(), "store_screenshots": config.settings.store_screenshots}


@router.post("/imports/screenshot/extract")
async def screenshot_extract(file: UploadFile = File(...)):
    return ocr.extract(await file.read(), file.filename or "screenshot")


class ScreenshotCommit(BaseModel):
    token: str
    recorded_at: str
    participant_code: str | None = None
    device_label: str | None = None
    notes: str | None = None
    confirmed: bool = False
    records: list[dict[str, Any]]


@router.post("/imports/screenshot/commit", status_code=201)
def screenshot_commit(body: ScreenshotCommit):
    return ocr.commit(body.token, body.model_dump())


@router.delete("/imports/screenshot/{token}")
def screenshot_discard(token: str):
    ocr.discard(token)
    return {"discarded": True}
