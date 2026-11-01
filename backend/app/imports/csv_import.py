"""CSV import with column mapping, validation report and explicit confirmation.

Flow: upload -> preview (token) -> analyse(mapping) -> commit(mapping).
Nothing is written to the records table until `commit` is called.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from .. import config, db
from . import records as rec

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 200_000

TIMESTAMP_SYNONYMS = ["timestamp", "datetime", "date_time", "recorded_at", "time", "date"]
PARTICIPANT_SYNONYMS = ["participant_id", "participant", "participant_code", "subject", "subject_id", "user", "username"]
METRIC_SYNONYMS = {
    "heart_rate": ["heart_rate", "heartrate", "heart rate", "hr", "bpm", "pulse"],
    "resting_heart_rate": ["resting_heart_rate", "resting_hr", "rhr"],
    "steps": ["steps", "step_count", "step"],
    "sleep_duration": ["sleep_duration", "sleep_minutes", "total_sleep", "sleep_min"],
    "hrv": ["hrv", "rmssd", "hrv_ms"],
    "spo2": ["spo2", "blood_oxygen", "oxygen_saturation"],
    "body_temperature": ["body_temperature", "temperature", "skin_temperature", "temp"],
    "device_stress_score": ["device_stress", "device_stress_score", "zepp_stress", "watch_stress"],
}
# Columns that clearly hold stress values but whose origin (device or self-report) is ambiguous.
AMBIGUOUS_STRESS = ["stress", "stress_level", "stress_score"]
UNIT_CONVERSIONS = {
    ("sleep_duration", "hours"): lambda v: v * 60.0,
    ("body_temperature", "fahrenheit"): lambda v: (v - 32.0) * 5.0 / 9.0,
}


def _pending_dir() -> Path:
    d = config.settings.upload_dir / "pending"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def _read(raw: bytes) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.BytesIO(raw), sep=None, engine="python", nrows=MAX_ROWS + 1, dtype=str, keep_default_na=False)
    except Exception as exc:
        raise rec.RecordError(f"The file could not be read as CSV: {exc}")
    if len(df) > MAX_ROWS:
        raise rec.RecordError(f"The file has more than {MAX_ROWS} rows; split it into smaller files.")
    if df.empty or len(df.columns) == 0:
        raise rec.RecordError("The CSV file contains no data rows.")
    df.columns = [str(c).strip() for c in df.columns]
    if len(set(df.columns)) != len(df.columns):
        raise rec.RecordError("The CSV has duplicate column names.")
    return df


def suggest_mapping(columns: list[str]) -> dict:
    normed = {c: _norm(c) for c in columns}
    mapping: dict[str, Any] = {"timestamp_column": None, "participant_column": None, "metrics": {}, "units": {}}
    warnings = []
    for syn in TIMESTAMP_SYNONYMS:
        hit = next((c for c, n in normed.items() if n == syn), None)
        if hit:
            mapping["timestamp_column"] = hit
            break
    for syn in PARTICIPANT_SYNONYMS:
        hit = next((c for c, n in normed.items() if n == syn), None)
        if hit:
            mapping["participant_column"] = hit
            break
    for c, n in normed.items():
        for metric, syns in METRIC_SYNONYMS.items():
            if n in [_norm(s) for s in syns]:
                mapping["metrics"][c] = metric
        if n in AMBIGUOUS_STRESS:
            warnings.append(
                f"Column '{c}' looks like a stress value but it is unclear whether it is a device score or a self-report. "
                "Map it explicitly to 'device_stress_score' or 'self_reported_stress', or leave it unmapped."
            )
        if n in ("sleep_hours", "sleep_duration_hours", "sleep_h"):
            mapping["metrics"][c] = "sleep_duration"
            mapping["units"][c] = "hours"
    return {"mapping": mapping, "warnings": warnings}


def preview(raw: bytes, filename: str) -> dict:
    if len(raw) > MAX_BYTES:
        raise rec.RecordError("File too large (max 20 MB).", 413)
    if not filename.lower().endswith((".csv", ".txt")):
        raise rec.RecordError("Only .csv files are supported.", 415)
    df = _read(raw)
    token = uuid.uuid4().hex
    (_pending_dir() / f"{token}.csv").write_bytes(raw)
    (_pending_dir() / f"{token}.json").write_text(json.dumps({"filename": filename, "sha256": hashlib.sha256(raw).hexdigest()}))
    sugg = suggest_mapping(list(df.columns))
    return {
        "token": token,
        "filename": filename,
        "n_rows": int(len(df)),
        "columns": list(df.columns),
        "rows": df.head(10).to_dict(orient="records"),
        "suggested_mapping": sugg["mapping"],
        "warnings": sugg["warnings"],
        "metrics": {k: {"label": v["label"], "unit": v["unit"]} for k, v in rec.METRICS.items()},
        "unit_options": {"sleep_duration": ["minutes", "hours"], "body_temperature": ["celsius", "fahrenheit"]},
    }


def _load_pending(token: str) -> tuple[pd.DataFrame, dict]:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise rec.RecordError("Invalid upload token.", 400)
    p = _pending_dir() / f"{token}.csv"
    if not p.exists():
        raise rec.RecordError("This upload has expired or was discarded. Upload the file again.", 404)
    meta = json.loads((_pending_dir() / f"{token}.json").read_text())
    return _read(p.read_bytes()), meta


def analyse(token: str, mapping: dict, commit: bool = False) -> dict:
    df, meta = _load_pending(token)
    ts_col = mapping.get("timestamp_column")
    if not ts_col or ts_col not in df.columns:
        raise rec.RecordError("Select the column that contains the date/time of each measurement.")
    metrics: dict[str, str] = {c: m for c, m in (mapping.get("metrics") or {}).items() if m}
    if not metrics:
        raise rec.RecordError("Map at least one column to a measurement type.")
    for c, m in metrics.items():
        if c not in df.columns:
            raise rec.RecordError(f"Column '{c}' does not exist in the file.")
        if m not in rec.METRICS:
            raise rec.RecordError(f"Unknown measurement type '{m}'.")
        if c == ts_col:
            raise rec.RecordError("The timestamp column cannot also be a measurement.")
    units = mapping.get("units") or {}
    part_col = mapping.get("participant_column") or None
    if part_col and part_col not in df.columns:
        raise rec.RecordError(f"Participant column '{part_col}' does not exist.")
    default_participant = rec.clean_code(mapping.get("default_participant_code"))
    device_label = (mapping.get("device_label") or "").strip() or None

    fmt = (mapping.get("timestamp_format") or "").strip() or None
    raw_ts = df[ts_col].astype(str).str.strip()
    parsed = pd.to_datetime(raw_ts, format=fmt, errors="coerce", dayfirst=bool(mapping.get("dayfirst")))
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
    invalid_ts = parsed.isna()

    report: dict[str, Any] = {
        "n_rows": int(len(df)),
        "invalid_timestamps": int(invalid_ts.sum()),
        "invalid_timestamp_rows": [int(i) + 2 for i in df.index[invalid_ts][:10]],  # +2 = header + 1-based
        "metrics": {},
        "duplicate_rows_in_file": int(df.duplicated().sum()),
    }
    candidates = []
    for col, metric in metrics.items():
        spec = rec.METRICS[metric]
        raw = df[col].astype(str).str.strip()
        missing = raw.isin(["", "nan", "NaN", "NA", "N/A", "null", "-", "--"])
        numeric = pd.to_numeric(raw.str.replace(",", "", regex=False), errors="coerce")
        non_numeric = numeric.isna() & ~missing
        conv = UNIT_CONVERSIONS.get((metric, units.get(col)))
        values = numeric.map(conv) if conv else numeric
        out_of_range = values.notna() & ((values < spec["min"]) | (values > spec["max"]))
        if spec.get("integer"):
            out_of_range |= values.notna() & (values % 1 != 0)
        ok = values.notna() & ~out_of_range & ~invalid_ts
        report["metrics"][col] = {
            "metric": metric, "unit": spec["unit"], "converted_from": units.get(col),
            "n_values": int(numeric.notna().sum()), "n_missing": int(missing.sum()),
            "n_non_numeric": int(non_numeric.sum()), "n_out_of_range": int(out_of_range.sum()),
            "n_valid": int(ok.sum()),
            "example_problems": [
                {"row": int(i) + 2, "value": raw[i]} for i in df.index[(non_numeric | out_of_range)][:5]
            ],
        }
        for i in df.index[ok]:
            pcode = rec.clean_code(df.at[i, part_col]) if part_col else default_participant
            candidates.append({
                "participant_code": pcode, "recorded_at": parsed[i].isoformat(timespec="seconds"), "metric": metric,
                "value": float(values[i]), "raw_value_text": raw[i], "device_label": device_label,
                "flags": [f"converted_from_{units[col]}"] if conv else [],
            })
    seen, in_file_dups, unique = set(), 0, []
    for c in candidates:
        key = (c["participant_code"], c["recorded_at"], c["metric"], c["value"])
        if key in seen:
            in_file_dups += 1
            continue
        seen.add(key)
        unique.append(c)
    with db.connect() as conn:
        is_dup = [rec.is_duplicate(conn, c["participant_code"], c["recorded_at"], c["metric"], c["value"]) for c in unique]
        db_dups = [c for c, d in zip(unique, is_dup) if d]
        new = [c for c, d in zip(unique, is_dup) if not d]
        report.update(
            duplicate_measurements_in_file=in_file_dups,
            duplicates_already_in_database=len(db_dups),
            n_records_to_import=len(new),
            note="Missing cells are skipped (never stored as zero). No stress label is created for any row.",
        )
        if commit:
            if not new:
                raise rec.RecordError("There are no new valid records to import.", 409, details=report)
            batch = rec.create_batch(conn, "csv", meta["filename"], meta["sha256"], device_label,
                                     details={"mapping": mapping, "report": {k: v for k, v in report.items() if k != "metrics"}})
            for c in new:
                rec.insert_record(conn, batch, "csv", c)
            rec.update_batch_count(conn, batch)
            report["batch_id"] = batch
            report["imported"] = len(new)
    if commit:
        discard(token)
    return report


def discard(token: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise rec.RecordError("Invalid upload token.", 400)
    for ext in (".csv", ".json"):
        p = _pending_dir() / f"{token}{ext}"
        if p.exists():
            p.unlink()
