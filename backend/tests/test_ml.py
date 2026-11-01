import time

import pytest

from app.ml import definitions, evaluation, registry
from conftest import REAL_DATASET


def test_no_target_in_features():
    for item in definitions.experiment_catalog():
        if item["available"]:
            y = definitions.TARGETS[item["target"]]["y"]
            assert y not in item["features"]
            assert "username" not in item["features"]


def test_unavailable_experiments_explain_why():
    with pytest.raises(ValueError, match="activity"):
        definitions.features_for("phase_window", "D")
    with pytest.raises(ValueError, match="synchronised"):
        definitions.features_for("phase_window", "C")


def test_cv_is_participant_wise(synthetic_dataset):
    res = evaluation.cross_validate("phase_window", "A", "logistic_regression")
    assert all(f["participant_overlap"] == 0 for f in res["details"]["folds"])
    assert sum(f["n_test_participants"] for f in res["details"]["folds"]) == res["n_participants"] == 10
    assert 0 <= res["metrics"]["balanced_accuracy"] <= 1
    cm = res["details"]["confusion_matrix"]
    assert sum(map(sum, cm)) == res["n_samples"]


def test_same_folds_across_experiments(synthetic_dataset):
    a = evaluation.cross_validate("phase_segment", "A", "random_forest")
    b = evaluation.cross_validate("phase_segment", "B", "random_forest")
    c = evaluation.cross_validate("phase_segment", "C", "random_forest")
    assert a["config"]["fold_assignment"] == b["config"]["fold_assignment"] == c["config"]["fold_assignment"]
    assert a["n_samples"] == b["n_samples"] == c["n_samples"]


def test_regression_targets(synthetic_dataset):
    res = evaluation.cross_validate("stai_state", "B", "ridge")
    assert {"mae", "rmse", "r2"} <= set(res["metrics"])
    assert len(res["details"]["points"]) == res["n_samples"]


def test_insufficient_participants(tmp_path):
    from conftest import write_synthetic_dataset
    from app.dataset import loader

    loader.set_dataset_dir(write_synthetic_dataset(tmp_path / "tiny", n_participants=3))
    try:
        with pytest.raises(evaluation.ExperimentError, match="at least"):
            evaluation.cross_validate("phase_window", "A", "svm")
    finally:
        loader.set_dataset_dir(None)


def test_train_predict_and_validation(synthetic_dataset):
    info = registry.train_final("phase_window", "B", "logistic_regression")
    mid = info["model_id"]
    ok = registry.predict(mid, {"hr_values": [80] * 30, "calibration_values": [65] * 60})
    assert ok["prediction"] in ("relax", "stress")
    assert "disclaimer" in ok and "probabilities" in ok
    with pytest.raises(evaluation.ExperimentError, match="single reading"):
        registry.predict(mid, {"hr_values": [80], "calibration_values": [65] * 60})
    with pytest.raises(evaluation.ExperimentError, match="calibration"):
        registry.predict(mid, {"hr_values": [80] * 30})
    with pytest.raises(evaluation.ExperimentError, match="between"):
        registry.predict(mid, {"hr_values": [500] * 30, "calibration_values": [65] * 60})
    far = registry.predict(mid, {"hr_values": [180] * 30, "calibration_values": [65] * 60})
    assert far["within_training_range"] is False
    # A model whose stored feature schema no longer matches is rejected
    ok_compat, why = registry._check_compat("phase_window", "B", ["hr_mean"])
    assert not ok_compat and "Retrain" in why


def test_participant_level_model_not_interactive(synthetic_dataset):
    info = registry.train_final("pss14", "A", "ridge")
    with pytest.raises(evaluation.ExperimentError, match="participant-level"):
        registry.predict(info["model_id"], {"hr_values": [70] * 100})


def test_experiment_job_api(client, synthetic_dataset):
    r = client.post("/api/experiments/run", json={"targets": ["phase_segment"], "models": ["dummy", "logistic_regression"]})
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("finished", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "finished", job
    res = client.get("/api/experiments/results?target=phase_segment").json()
    assert {r["experiment"] for r in res["runs"]} >= {"A", "B", "C"}
    assert any(c["same_participants_and_folds"] for c in res["comparisons"])
    csv_text = client.get("/api/experiments/results.csv").text
    assert csv_text.startswith("run_id,")


@pytest.mark.skipif(REAL_DATASET is None, reason="QoL_Stress dataset not installed")
def test_real_dataset_pipeline():
    from app.dataset import loader, qol

    loader.set_dataset_dir(REAL_DATASET)
    p = qol.build(force=True)
    assert p.summary["participants_total"] == 66
    assert p.summary["participants_eligible"] >= 40
    assert p.summary["pss_scoring_check"]["verified"]
    res = evaluation.cross_validate("phase_window", "B", "logistic_regression")
    assert res["n_participants"] == p.summary["participants_eligible"]
