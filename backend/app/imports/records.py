"""User-entered measurements (manual, CSV, screenshot) with provenance.

These records are kept completely separate from the QoL_Stress research data
and are never used to train or evaluate the research models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import db

METRICS: dict[str, dict[str, Any]] = {
    "heart_rate": {"label": "Heart rate", "unit": "bpm", "min": 30, "max": 220},
    "resting_heart_rate": {"label": "Resting heart rate", "unit": "bpm", "min": 30, "max": 150},
    "steps": {"label": "Steps", "unit": "steps", "min": 0, "max": 100000, "integer": True},
    "sleep_duration": {"label": "Sleep duration", "unit": "min", "min": 0, "max": 1440},
    "hrv": {"label": "Heart-rate variability", "unit": "ms", "min": 1, "max": 300},
    "spo2": {"label": "Blood oxygen (SpO2)", "unit": "%", "min": 70, "max": 100},
    "body_temperature": {"label": "Body/skin temperature", "unit": "degC", "min": 30, "max": 43},
    "device_stress_score": {
        "label": "Device stress score",
        "unit": "device scale",
        "min": 0,
        "max": 100,
        "note": "Manufacturer's proprietary score. Stored separately and never used as ground truth.",
    },
    "self_reported_stress": {
        "label": "Self-reported stress (1-5)",
        "unit": "1-5 scale",
        "min": 1,
        "max": 5,
        "integer": True,
        "note": "1 = not stressed, 5 = extremely stressed. Only ever entered by the participant.",
    },
}

SOURCES = ("manual", "csv", "screenshot")


class RecordError(Exception):
    def __init__(self, message: str, status_code: int = 422, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


def normalise_timestamp(value: str) -> str:
    """Accept ISO-8601 date-times; store as 'YYYY-MM-DDTHH:MM:SS' (local time as entered)."""
    if not value or not str(value).strip():
        raise RecordError("A date and time is required for every measurement.")
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        raise RecordError(f"'{value}' is not a valid date/time. Use e.g. 2026-11-01T14:30.")
    if dt.year < 2000 or dt.year > datetime.now().year + 1:
        raise RecordError(f"Timestamp {value} is outside the plausible range (2000 to next year).")
    return dt.replace(tzinfo=None).isoformat(timespec="seconds")


def validate_value(metric: str, value: Any) -> float:
    spec = METRICS.get(metric)
    if spec is None:
        raise RecordError(f"Unknown metric '{metric}'. Allowed: {sorted(METRICS)}.")
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise RecordError(f"{spec['label']}: '{value}' is not a number.")
    if v != v:
        raise RecordError(f"{spec['label']}: value is missing.")
    if v < spec["min"] or v > spec["max"]:
        raise RecordError(f"{spec['label']} must be between {spec['min']} and {spec['max']} {spec['unit']} (got {v}).")
    if spec.get("integer") and not float(v).is_integer():
        raise RecordError(f"{spec['label']} must be a whole number.")
    return v


def clean_code(code: str | None) -> str | None:
    if code is None:
        return None
    code = str(code).strip()
    if not code:
        return None
    if len(code) > 40 or "@" in code:
        raise RecordError("Participant code must be a short pseudonymous code (no names or e-mail addresses).")
    return code


def create_batch(conn, source: str, filename: str | None = None, sha: str | None = None, device_label: str | None = None,
                 stored_file: str | None = None, details: dict | None = None) -> int:
    cur = conn.execute(
        """INSERT INTO import_batches (source, filename, file_sha256, device_label, stored_file, status, details_json, created_at)
           VALUES (?,?,?,?,?, 'committed', ?, ?)""",
        (source, filename, sha, device_label, stored_file, db.dumps(details or {}), db.now_iso()),
    )
    return int(cur.lastrowid)


def is_duplicate(conn, participant: str | None, recorded_at: str, metric: str, value: float) -> bool:
    row = conn.execute(
        """SELECT 1 FROM user_records WHERE IFNULL(participant_code,'')=IFNULL(?, '') AND recorded_at=? AND metric=?
           AND ABS(value-?) < 1e-9 LIMIT 1""",
        (participant, recorded_at, metric, value),
    ).fetchone()
    return row is not None


def insert_record(conn, batch_id: int, source: str, rec: dict) -> int:
    cur = conn.execute(
        """INSERT INTO user_records (batch_id, source, device_label, participant_code, recorded_at, metric, value, unit,
           raw_value_text, value_was_edited, verified_device_measurement, extraction_flags, notes, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)""",
        (
            batch_id, source, rec.get("device_label"), rec.get("participant_code"), rec["recorded_at"], rec["metric"],
            rec["value"], METRICS[rec["metric"]]["unit"], rec.get("raw_value_text"), int(bool(rec.get("value_was_edited"))),
            db.dumps(rec.get("flags") or []), rec.get("notes"), db.now_iso(),
        ),
    )
    return int(cur.lastrowid)


def update_batch_count(conn, batch_id: int) -> None:
    conn.execute(
        "UPDATE import_batches SET n_records=(SELECT COUNT(*) FROM user_records WHERE batch_id=?) WHERE id=?", (batch_id, batch_id)
    )


def create_manual(payload: dict) -> dict:
    recorded_at = normalise_timestamp(payload.get("recorded_at"))
    participant = clean_code(payload.get("participant_code"))
    measurements = {k: v for k, v in (payload.get("measurements") or {}).items() if v not in (None, "")}
    if not measurements:
        raise RecordError("Enter at least one measurement. Empty fields are stored as missing, never as zero.")
    errors, clean = [], {}
    for metric, value in measurements.items():
        try:
            clean[metric] = validate_value(metric, value)
        except RecordError as exc:
            errors.append(exc.message)
    if errors:
        raise RecordError("Some values are invalid.", details=errors)
    device_label = (payload.get("device_label") or "").strip() or None
    with db.connect() as conn:
        dups = [m for m, v in clean.items() if is_duplicate(conn, participant, recorded_at, m, v)]
        if dups and not payload.get("allow_duplicates"):
            raise RecordError(f"Identical records already exist for {dups} at {recorded_at}.", 409, details={"duplicates": dups})
        batch = create_batch(conn, "manual", device_label=device_label)
        ids = []
        for metric, value in clean.items():
            ids.append(insert_record(conn, batch, "manual", {
                "metric": metric, "value": value, "recorded_at": recorded_at, "participant_code": participant,
                "device_label": device_label, "notes": payload.get("notes"), "raw_value_text": str(measurements[metric]),
            }))
        update_batch_count(conn, batch)
    return {"batch_id": batch, "record_ids": ids, "n_records": len(ids)}


def list_records(filters: dict) -> dict:
    where, params = [], []
    for col in ("source", "metric", "participant_code"):
        if filters.get(col):
            where.append(f"{col} = ?")
            params.append(filters[col])
    if filters.get("start"):
        where.append("recorded_at >= ?")
        params.append(filters["start"])
    if filters.get("end"):
        where.append("recorded_at <= ?")
        params.append(filters["end"])
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    limit = min(int(filters.get("limit") or 50), 5000)
    offset = int(filters.get("offset") or 0)
    with db.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM user_records {clause}", params).fetchone()[0]
        rows = db.rows_to_dicts(conn.execute(
            f"SELECT * FROM user_records {clause} ORDER BY recorded_at DESC, id DESC LIMIT ? OFFSET ?", [*params, limit, offset]
        ).fetchall())
    return {"total": total, "rows": rows}


def summary() -> dict:
    with db.connect() as conn:
        by_source = {r[0]: r[1] for r in conn.execute("SELECT source, COUNT(*) FROM user_records GROUP BY source")}
        by_metric = {r[0]: r[1] for r in conn.execute("SELECT metric, COUNT(*) FROM user_records GROUP BY metric")}
        participants = conn.execute("SELECT COUNT(DISTINCT participant_code) FROM user_records WHERE participant_code IS NOT NULL").fetchone()[0]
        batches = db.rows_to_dicts(conn.execute("SELECT id, source, filename, device_label, n_records, created_at FROM import_batches ORDER BY id DESC LIMIT 10").fetchall())
    return {"by_source": by_source, "by_metric": by_metric, "participants": participants, "recent_batches": batches,
            "total": sum(by_source.values())}


def delete_record(record_id: int) -> None:
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM user_records WHERE id=?", (record_id,))
        if cur.rowcount == 0:
            raise RecordError("Record not found.", 404)


def delete_batch(batch_id: int) -> int:
    with db.connect() as conn:
        n = conn.execute("DELETE FROM user_records WHERE batch_id=?", (batch_id,)).rowcount
        cur = conn.execute("DELETE FROM import_batches WHERE id=?", (batch_id,))
        if cur.rowcount == 0:
            raise RecordError("Import batch not found.", 404)
    return n


def user_baseline(participant_code: str, start: str, end: str, min_readings: int = 10) -> dict:
    """Baseline heart rate for user-entered data over an explicitly chosen period."""
    import numpy as np

    start_n, end_n = normalise_timestamp(start), normalise_timestamp(end)
    if end_n <= start_n:
        raise RecordError("The baseline period end must be after its start.")
    with db.connect() as conn:
        base_rows = db.rows_to_dicts(conn.execute(
            """SELECT recorded_at, value, source FROM user_records WHERE participant_code=? AND metric='heart_rate'
               AND recorded_at BETWEEN ? AND ? ORDER BY recorded_at""", (participant_code, start_n, end_n)).fetchall())
        later = db.rows_to_dicts(conn.execute(
            """SELECT recorded_at, value, source FROM user_records WHERE participant_code=? AND metric='heart_rate'
               AND recorded_at > ? ORDER BY recorded_at LIMIT 500""", (participant_code, end_n)).fetchall())
    vals = np.array([r["value"] for r in base_rows], dtype=float)
    reliable = len(vals) >= min_readings
    res: dict[str, Any] = {
        "participant_code": participant_code, "period_start": start_n, "period_end": end_n,
        "n_readings": int(len(vals)), "min_readings_required": min_readings, "meets_minimum": reliable,
        "sources": sorted({r["source"] for r in base_rows}),
    }
    if len(vals):
        res.update(baseline_median=float(np.median(vals)), baseline_mean=float(np.mean(vals)),
                   baseline_sd=float(np.std(vals, ddof=1)) if len(vals) > 1 else None)
        res["subsequent"] = [
            {"recorded_at": r["recorded_at"], "value": r["value"], "source": r["source"],
             "delta_from_baseline": r["value"] - res["baseline_median"]} for r in later
        ]
    else:
        res["subsequent"] = []
    res["note"] = ("A reading above baseline does not mean the person is stressed: activity, posture, caffeine, illness and "
                   "measurement error all change heart rate. No activity data is used here.")
    return res
