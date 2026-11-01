"""Test configuration.

The `synthetic_dataset` fixture writes a SYNTHETIC TEST FIXTURE that mimics the
QoL_Stress file layout. It exists only to exercise the software. It is not
research data, and no result computed from it may be reported as a finding.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_TMP = Path(tempfile.mkdtemp(prefix="qol_tests_"))
os.environ["APP_DB_PATH"] = str(_TMP / "test.db")
os.environ["ARTIFACT_DIR"] = str(_TMP / "artifacts")
os.environ["UPLOAD_DIR"] = str(_TMP / "uploads")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.dataset import loader  # noqa: E402
from app.main import app  # noqa: E402

db.init_db()

REAL_DATASET = loader.dataset_dir() if (loader.dataset_dir() / "stai.csv").exists() else None


def _clock(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def write_synthetic_dataset(folder: Path, n_participants: int = 10, seed: int = 0) -> Path:
    """SYNTHETIC TEST FIXTURE - fabricated values for software tests only."""
    rng = np.random.default_rng(seed)
    folder.mkdir(parents=True, exist_ok=True)
    hr, stai, pss, eda, ecg, parts = [], [], [], [], [], []
    for i in range(n_participants):
        u = f"synthetic_test_participant_{i:02d}"
        start = 9 * 3600 + i * 3600
        base = rng.uniform(60, 80)
        t_relax_q = start + 20 * 60
        t_stress_q = start + 32 * 60
        for t in np.arange(start, t_stress_q + 30, 2):
            level = base + (8 if t > t_relax_q else 0)
            hr.append((u, _clock(t), int(round(level + rng.normal(0, 3)))))
        stai += [(u, _clock(t_relax_q), "relax", int(rng.integers(25, 35))), (u, _clock(t_stress_q), "stress", int(rng.integers(30, 45)))]
        pss.append((u, _clock(start - 300), int(rng.integers(10, 35))))
        for ph, shift in (("relax", 0.0), ("stress", 2.0)):
            for s in range(0, 160):
                eda.append((u, ph, s, True, int(rng.random() < 0.1), 35 + shift + rng.normal(0, 1)))
            ecg.append((u, ph, _clock(t_relax_q - 300 if ph == "relax" else t_stress_q - 300), int(base + (5 if ph == "stress" else 0)), "NSR"))
        parts.append((u, "Female" if i % 2 else "Male", 20 + i, "Bachelor", "Student"))
    pd.DataFrame(hr, columns=["username", "time", "value"]).to_csv(folder / "fitbit_heart_rate_per_second.csv", index=False)
    pd.DataFrame(stai, columns=["username", "time", "phase", "score"]).to_csv(folder / "stai.csv", index=False)
    pd.DataFrame(pss, columns=["username", "time", "score"]).to_csv(folder / "pss_14.csv", index=False)
    pd.DataFrame(eda, columns=["username", "phase", "time_sec", "valid_data", "activation", "scl_avg"]).to_csv(folder / "eda.csv", index=False)
    pd.DataFrame(ecg, columns=["username", "phase", "reading_time", "heart_rate", "result_classification"]).to_csv(folder / "ecg.csv", index=False)
    pd.DataFrame(parts, columns=["username", "sex", "age", "education_level", "job_category"]).to_csv(folder / "participants.csv", index=False)
    (folder / "SYNTHETIC_TEST_FIXTURE.txt").write_text("Fabricated data for automated software tests only. Not research data.\n")
    return folder


@pytest.fixture()
def synthetic_dataset(tmp_path):
    folder = write_synthetic_dataset(tmp_path / "synthetic_qol")
    loader.set_dataset_dir(folder)
    yield folder
    loader.set_dataset_dir(None)


@pytest.fixture()
def empty_dataset_dir(tmp_path):
    folder = tmp_path / "empty"
    folder.mkdir()
    loader.set_dataset_dir(folder)
    yield folder
    loader.set_dataset_dir(None)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
