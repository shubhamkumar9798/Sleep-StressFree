"""SQLite storage for application records.

The public QoL_Stress CSV files are NOT copied into this database; they are read
directly from the dataset folder. The database only holds:
  * user-entered / imported measurements (manual, CSV, screenshot) with provenance,
  * import batches,
  * experiment runs and trained-model metadata,
  * a log of exploratory predictions.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS import_batches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL CHECK (source IN ('manual','csv','screenshot')),
    filename        TEXT,
    file_sha256     TEXT,
    device_label    TEXT,
    stored_file     TEXT,
    status          TEXT NOT NULL DEFAULT 'committed',
    n_records       INTEGER NOT NULL DEFAULT 0,
    details_json    TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_records (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id          INTEGER REFERENCES import_batches(id) ON DELETE CASCADE,
    source            TEXT NOT NULL CHECK (source IN ('manual','csv','screenshot')),
    device_label      TEXT,
    participant_code  TEXT,
    recorded_at       TEXT NOT NULL,
    metric            TEXT NOT NULL,
    value             REAL NOT NULL,
    unit              TEXT NOT NULL,
    raw_value_text    TEXT,
    value_was_edited  INTEGER NOT NULL DEFAULT 0,
    verified_device_measurement INTEGER NOT NULL DEFAULT 0,
    extraction_flags  TEXT,
    notes             TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_user_records_lookup ON user_records(participant_code, metric, recorded_at);

CREATE TABLE IF NOT EXISTS experiment_runs (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id             TEXT NOT NULL,
    target               TEXT NOT NULL,
    experiment           TEXT NOT NULL,
    model                TEXT NOT NULL,
    task                 TEXT NOT NULL,
    n_participants       INTEGER NOT NULL,
    n_samples            INTEGER NOT NULL,
    config_json          TEXT NOT NULL,
    metrics_json         TEXT NOT NULL,
    details_json         TEXT NOT NULL,
    dataset_fingerprint  TEXT NOT NULL,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trained_models (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    target               TEXT NOT NULL,
    experiment           TEXT NOT NULL,
    model                TEXT NOT NULL,
    artifact_path        TEXT NOT NULL,
    feature_names_json   TEXT NOT NULL,
    cv_run_id            INTEGER REFERENCES experiment_runs(id),
    dataset_fingerprint  TEXT NOT NULL,
    is_active            INTEGER NOT NULL DEFAULT 1,
    created_at           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prediction_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id          INTEGER NOT NULL REFERENCES trained_models(id),
    input_source      TEXT NOT NULL,
    inputs_json       TEXT NOT NULL,
    output_json       TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _db_path() -> Path:
    return config.settings.db_path


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def dumps(obj: Any) -> str:
    return json.dumps(obj, default=str)
