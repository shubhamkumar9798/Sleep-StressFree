import pandas as pd
import pytest

from app.dataset import loader, qol


def test_parse_clock_formats():
    s = pd.Series(["12:07:52", " 9:37:30", "Tue Dec 17 13:01:42", "25:00:00", "garbage"])
    out = loader.parse_clock(s)
    assert out[0] == 12 * 3600 + 7 * 60 + 52
    assert out[1] == 9 * 3600 + 37 * 60 + 30
    assert out[2] == 13 * 3600 + 60 + 42
    assert pd.isna(out[3]) and pd.isna(out[4])


def test_missing_dataset_status(client, empty_dataset_dir):
    r = client.get("/api/dataset/status").json()
    assert r["available"] is False
    assert "setup_message" in r
    assert client.get("/api/preprocessing/summary").status_code == 409
    assert client.post("/api/experiments/run", json={}).status_code == 409
    d = client.get("/api/dashboard").json()
    assert d["dataset"]["available"] is False and "preprocessing" not in d


def test_schema_mismatch_is_reported(tmp_path, synthetic_dataset):
    stai = pd.read_csv(synthetic_dataset / "stai.csv").drop(columns=["phase"])
    stai.to_csv(synthetic_dataset / "stai.csv", index=False)
    rep = loader.validate_file("stai.csv")
    assert any("missing columns" in i for i in rep["issues"])
    with pytest.raises(loader.DatasetError) as exc:
        qol.build(force=True)
    assert exc.value.status_code == 422


def test_validate_reports_quality(synthetic_dataset):
    rep = loader.validate_file("fitbit_heart_rate_per_second.csv")
    assert rep["n_participants"] == 10
    assert rep["timestamps"]["time"]["n_invalid"] == 0
    assert "n_duplicate_keys" in rep


def test_preprocessing_segments_and_calibration(synthetic_dataset):
    p = qol.build(force=True)
    assert p.summary["participants_eligible"] == 10
    assert set(p.windows["phase"]) == {"relax", "stress"}
    # Calibration minutes are never part of an evaluation window
    merged = p.windows.merge(p.sessions[["username", "calib_end", "stai_relax_t", "stai_stress_t"]], on="username")
    assert (merged["window_start"] >= merged["calib_end"]).all()
    relax = merged[merged.phase == "relax"]
    stress = merged[merged.phase == "stress"]
    assert (relax["window_start"] + 60 <= relax["stai_relax_t"]).all()
    assert (stress["window_start"] > stress["stai_relax_t"]).all()
    assert len(p.segments) == 20
    assert p.segments["stai_score"].notna().all()


def test_no_forward_fill_across_participants(synthetic_dataset):
    # Remove all heart rate of one participant: it must be excluded, not filled from a neighbour.
    hr = pd.read_csv(synthetic_dataset / "fitbit_heart_rate_per_second.csv")
    hr = hr[hr.username != "synthetic_test_participant_03"]
    hr.to_csv(synthetic_dataset / "fitbit_heart_rate_per_second.csv", index=False)
    p = qol.build(force=True)
    assert "synthetic_test_participant_03" not in set(p.windows["username"])
    excl = {e["username"]: e["reasons"] for e in p.summary["exclusions"]}
    assert "no valid heart-rate samples" in excl["synthetic_test_participant_03"]


def test_hr_features():
    f = qol.hr_features([60, 62, 64, 66], [0, 20, 40, 60])
    assert f["hr_mean"] == 63 and f["hr_min"] == 60 and f["hr_max"] == 66
    assert abs(f["hr_slope"] - 6.0) < 1e-9  # 2 bpm per 20 s = 6 bpm/min
    base = qol.baseline_stats([60, 60, 60])
    pf = qol.personal_features(f, base)
    assert pf["hr_mean_delta"] == 3
    assert pf["hr_mean_z"] == 3  # SD floored at 1 bpm
