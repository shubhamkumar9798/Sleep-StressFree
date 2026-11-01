"""Discovery, loading and validation of the QoL_Stress CSV files.

Files are opened read-only; nothing in the dataset folder is ever written.
"""
from __future__ import annotations

import hashlib
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .. import config
from .schema import EXPECTED_FILES

_lock = threading.Lock()
_state: dict[str, Any] = {"dir": None}
_frame_cache: dict[tuple, pd.DataFrame] = {}
_hash_cache: dict[tuple, str] = {}

# Columns with very long text (ECG waveforms) are not loaded unless asked for.
_HEAVY_COLUMNS = {"ecg.csv": ["waveform_samples"]}
_CLOCK_RE = r"(\d{1,2}:\d{2}:\d{2})"


class DatasetError(Exception):
    """Raised when the dataset (or one of its files) is missing or malformed."""

    def __init__(self, message: str, status_code: int = 409, details: Any = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


def dataset_dir() -> Path:
    return Path(_state["dir"] or config.settings.dataset_dir)


def set_dataset_dir(path: str | Path | None) -> None:
    """Point the app at another dataset folder (used by tests and the Settings page)."""
    with _lock:
        _state["dir"] = Path(path) if path else None
        _frame_cache.clear()
    from . import qol  # local import to avoid a cycle

    qol.clear_cache()


def _file_key(path: Path) -> tuple:
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


def sha256_of(path: Path) -> str:
    key = _file_key(path)
    if key not in _hash_cache:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _hash_cache[key] = h.hexdigest()
    return _hash_cache[key]


def parse_clock(values: pd.Series) -> pd.Series:
    """Parse time-of-day strings into seconds since midnight (float, NaN if invalid).

    The dataset stores clock times without dates (e.g. '12:07:52', ' 9:37:30').
    One ECG row uses 'Tue Dec 17 13:01:42'; the HH:MM:SS part is extracted.
    """
    extracted = values.astype(str).str.extract(_CLOCK_RE)[0]
    parts = extracted.str.split(":", expand=True)
    if parts.shape[1] < 3:
        return pd.Series(np.nan, index=values.index, dtype=float)
    h = pd.to_numeric(parts[0], errors="coerce")
    m = pd.to_numeric(parts[1], errors="coerce")
    s = pd.to_numeric(parts[2], errors="coerce")
    valid = (h >= 0) & (h < 24) & (m >= 0) & (m < 60) & (s >= 0) & (s < 60)
    secs = h * 3600 + m * 60 + s
    return secs.where(valid).astype(float)


def file_status() -> list[dict]:
    d = dataset_dir()
    out = []
    for name, spec in EXPECTED_FILES.items():
        p = d / name
        item = {
            "file": name,
            "present": p.exists(),
            "description": spec["description"],
            "role": spec["role"],
            "used_by_pipeline": spec["used_by_pipeline"],
            "size_bytes": p.stat().st_size if p.exists() else None,
        }
        out.append(item)
    return out


def is_available() -> bool:
    d = dataset_dir()
    return d.exists() and any((d / f).exists() for f in EXPECTED_FILES)


def load(name: str, include_heavy: bool = False) -> pd.DataFrame:
    if name not in EXPECTED_FILES:
        raise DatasetError(f"Unknown dataset file '{name}'.", 404)
    path = dataset_dir() / name
    if not path.exists():
        raise DatasetError(
            f"Required file '{name}' was not found in {dataset_dir()}. "
            "Download the QoL_Stress dataset from PhysioNet and place the CSV files there (see README).",
            409,
        )
    key = (*_file_key(path), include_heavy)
    with _lock:
        if key in _frame_cache:
            return _frame_cache[key]
    usecols = None
    if not include_heavy and name in _HEAVY_COLUMNS:
        header = pd.read_csv(path, nrows=0).columns
        usecols = [c for c in header if c not in _HEAVY_COLUMNS[name]]
    try:
        df = pd.read_csv(path, usecols=usecols)
    except Exception as exc:  # malformed CSV
        raise DatasetError(f"Could not parse '{name}': {exc}", 422) from exc
    missing = [c for c in EXPECTED_FILES[name]["required_columns"] if c not in df.columns]
    if missing:
        raise DatasetError(
            f"'{name}' does not match the expected schema: missing columns {missing}.",
            422,
            {"missing_columns": missing, "found_columns": list(df.columns)},
        )
    with _lock:
        _frame_cache[key] = df
    return df


def fingerprint() -> str:
    """Hash of the pipeline's input files; stored with every experiment and model."""
    d = dataset_dir()
    h = hashlib.sha256()
    for name, spec in sorted(EXPECTED_FILES.items()):
        p = d / name
        if spec["used_by_pipeline"] and p.exists():
            h.update(name.encode())
            h.update(sha256_of(p).encode())
    return h.hexdigest()[:16]


def _jsonable(v: Any) -> Any:
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, str) and len(v) > 80:
        return v[:77] + "..."
    return v


def validate_file(name: str) -> dict:
    """Schema, missing values, duplicates, timestamps and value-range report for one file."""
    spec = EXPECTED_FILES.get(name)
    if spec is None:
        raise DatasetError(f"Unknown dataset file '{name}'.", 404)
    path = dataset_dir() / name
    report: dict[str, Any] = {"file": name, "present": path.exists(), "issues": [], "warnings": []}
    if not path.exists():
        report["issues"].append("File is missing.")
        return report
    try:
        df = load(name)
    except DatasetError as exc:
        report["issues"].append(exc.message)
        return report

    report["sha256"] = sha256_of(path)
    report["n_rows"] = int(len(df))
    report["columns"] = [
        {
            "name": c,
            "dtype": str(df[c].dtype),
            "n_missing": int(df[c].isna().sum()),
            "n_unique": int(df[c].nunique(dropna=True)),
            "required": c in spec["required_columns"],
        }
        for c in df.columns
    ]
    if name in _HEAVY_COLUMNS:
        report["warnings"].append(f"Columns {_HEAVY_COLUMNS[name]} hold long waveform strings and are not loaded.")
    extra = [c for c in df.columns if c not in spec["required_columns"]]
    report["extra_columns"] = len(extra)
    if "username" in df.columns:
        report["n_participants"] = int(df["username"].nunique())
    report["n_duplicate_rows"] = int(df.duplicated().sum())
    if report["n_duplicate_rows"]:
        report["warnings"].append(f"{report['n_duplicate_rows']} fully duplicated rows.")

    key_cols = {
        "fitbit_heart_rate_per_second.csv": ["username", "time"],
        "fitbit_heart_rate_per_minute.csv": ["username", "time"],
        "stai.csv": ["username", "phase"],
        "pss_14.csv": ["username"],
        "ecg.csv": ["username", "phase"],
        "participants.csv": ["username"],
        "fitbit_heart_rate_summary.csv": ["username", "zone_name"],
    }.get(name)
    if key_cols:
        dup_keys = int(df.duplicated(key_cols).sum())
        report["n_duplicate_keys"] = dup_keys
        report["duplicate_key_columns"] = key_cols
        if dup_keys:
            report["warnings"].append(f"{dup_keys} rows share the same {key_cols}; duplicates are dropped (first kept) during preprocessing.")

    for tc in spec["time_columns"]:
        secs = parse_clock(df[tc])
        n_invalid = int(secs.isna().sum())
        non_standard = int((~df[tc].astype(str).str.fullmatch(r"\d{2}:\d{2}:\d{2}")).sum())
        report.setdefault("timestamps", {})[tc] = {
            "n_invalid": n_invalid,
            "n_non_standard_format": non_standard,
            "has_date": False,
        }
        if n_invalid:
            report["issues"].append(f"{n_invalid} unparseable values in '{tc}'.")
        if non_standard:
            report["warnings"].append(
                f"{non_standard} values in '{tc}' are not in zero-padded HH:MM:SS form (e.g. single-digit hour '9:05:00', "
                "a leading space or a weekday/date prefix); the clock time is extracted."
            )
    if any(spec["time_columns"]):
        report["warnings"].append("Timestamps are clock times without dates; sessions are assumed not to cross midnight.")

    if name.startswith("fitbit_heart_rate_per"):
        v = pd.to_numeric(df["value"], errors="coerce")
        pp = config.settings.preprocessing
        out_of_range = int(((v < pp.hr_valid_min) | (v > pp.hr_valid_max)).sum())
        report["value_summary"] = {k: _jsonable(x) for k, x in v.describe().items()}
        report["n_out_of_physiological_range"] = out_of_range
        if out_of_range:
            report["warnings"].append(f"{out_of_range} heart-rate values outside {pp.hr_valid_min}-{pp.hr_valid_max} bpm are excluded.")
    if name == "eda.csv":
        invalid = int((~df["valid_data"].astype(bool)).sum())
        neg_time = int((pd.to_numeric(df["time_sec"], errors="coerce") < 0).sum())
        report["n_invalid_flagged"] = invalid
        report["n_negative_time_sec"] = neg_time
        report["warnings"].append(f"{invalid} rows flagged valid_data=False and {neg_time} rows with negative time_sec are excluded.")
    if name == "ecg.csv":
        uncl = int((df["result_classification"] != "NSR").sum())
        report["warnings"].append(
            f"{uncl} recordings are not classified 'NSR' by the device; their heart rate is treated as missing."
        )
    return report


def preview(name: str, n: int = 10) -> dict:
    df = load(name)
    head = df.head(n)
    rows = [{c: _jsonable(v) for c, v in r.items()} for r in head.to_dict(orient="records")]
    return {"file": name, "columns": list(df.columns), "rows": rows, "n_rows": int(len(df))}
