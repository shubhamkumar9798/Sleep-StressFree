"""Prediction targets, experiments and feature sets.

Every experiment declares exactly which columns it may use. The target column
is checked to never appear in a feature list (see `features_for`).
"""
from __future__ import annotations

from ..dataset.qol import HR_STAT_FEATURES, MULTIMODAL_FEATURES, PERSONAL_FEATURES

FEATURE_SCHEMA_VERSION = 1

TARGETS: dict[str, dict] = {
    "phase_window": {
        "name": "Experimental phase (60-s windows)",
        "task": "classification",
        "unit": "60-second heart-rate window",
        "table": "windows",
        "y": "label",
        "classes": ["relax", "stress"],
        "primary": True,
        "label_source": "Protocol condition (relax vs. induced stress), reconstructed from STAI questionnaire timestamps. "
        "Not a self-reported stress level.",
        "description": "Can the experimental condition be recognised from one minute of Fitbit heart rate in participants not seen during training?",
    },
    "phase_segment": {
        "name": "Experimental phase (5-min segments)",
        "task": "classification",
        "unit": "last 5 minutes of each phase (2 per participant)",
        "table": "segments",
        "y": "label",
        "classes": ["relax", "stress"],
        "primary": False,
        "label_source": "Protocol condition (relax vs. induced stress).",
        "description": "Phase recognition at segment level, which allows EDA and ECG phase features to be added (Experiment C).",
    },
    "stai_state": {
        "name": "STAI state-anxiety score",
        "task": "regression",
        "unit": "last 5 minutes of each phase (2 per participant)",
        "table": "segments",
        "y": "stai_score",
        "primary": False,
        "label_source": "Self-reported STAI state score (20-80) answered at the end of each phase.",
        "description": "Regression of the self-reported state-anxiety score from heart-rate features of the minutes preceding the questionnaire.",
    },
    "pss14": {
        "name": "PSS-14 perceived stress (past month)",
        "task": "regression",
        "unit": "participant (1 row each)",
        "table": "participants",
        "y": "pss_score",
        "primary": False,
        "label_source": "Self-reported Perceived Stress Scale (0-56), refers to the last month, answered once before the session.",
        "description": "Exploratory: can lab-session heart-rate features estimate a person's past-month perceived stress? "
        "Very small sample (one row per participant).",
    },
}

UNAVAILABLE_D = (
    "The dataset contains no step, accelerometer or activity-label data for the session. "
    "fitbit_heart_rate_summary.csv only gives minutes per heart-rate zone for the whole day, which cannot be attributed "
    "to the relax or stress phase. An activity-adjusted analysis would therefore be invented, so Experiment D is disabled."
)
UNAVAILABLE_C_WINDOW = (
    "EDA time stamps are seconds relative to an unknown per-phase recording start and each ECG file is one short recording "
    "per phase, so neither can be synchronised with individual 60-s Fitbit windows. Experiment C is available for the "
    "segment-level and participant-level targets instead."
)

PART_HR = [f"rest_{f}" for f in HR_STAT_FEATURES]
PART_PERSONAL = ["rest_hr_mean_delta", "rest_hr_mean_ratio", "rest_hr_mean_z",
                 "stress_hr_mean_delta", "stress_hr_mean_ratio", "stress_hr_mean_z", "reactivity_hr_mean"]
PART_MULTI = [f"{p}_{f}" for f in MULTIMODAL_FEATURES for p in ("rest", "stress")]

EXPERIMENTS: dict[str, dict] = {
    "A": {"name": "A. General model", "description": "Heart-rate summary statistics only; no participant-specific information."},
    "B": {"name": "B. Personalised baseline", "description": "A + deviations from each participant's own 3-minute calibration baseline (computed without labels, excluded from evaluation)."},
    "C": {"name": "C. Additional physiology", "description": "B + phase-level EDA (skin conductance) and device-reported ECG heart rate."},
    "D": {"name": "D. Activity-adjusted", "description": "Would add activity covariates to control for physical-activity confounding."},
}


def _feature_map(target: str) -> dict[str, list[str] | str]:
    if target == "phase_window":
        return {"A": HR_STAT_FEATURES, "B": HR_STAT_FEATURES + PERSONAL_FEATURES, "C": UNAVAILABLE_C_WINDOW, "D": UNAVAILABLE_D}
    if target in ("phase_segment", "stai_state"):
        return {
            "A": HR_STAT_FEATURES,
            "B": HR_STAT_FEATURES + PERSONAL_FEATURES,
            "C": HR_STAT_FEATURES + PERSONAL_FEATURES + MULTIMODAL_FEATURES,
            "D": UNAVAILABLE_D,
        }
    if target == "pss14":
        return {"A": PART_HR, "B": PART_HR + PART_PERSONAL, "C": PART_HR + PART_PERSONAL + PART_MULTI, "D": UNAVAILABLE_D}
    raise KeyError(target)


def features_for(target: str, experiment: str) -> list[str]:
    """Feature list, or raises ValueError with the scientific reason it is unavailable."""
    if target not in TARGETS:
        raise KeyError(f"Unknown target '{target}'")
    fm = _feature_map(target)
    if experiment not in fm:
        raise KeyError(f"Unknown experiment '{experiment}'")
    feats = fm[experiment]
    if isinstance(feats, str):
        raise ValueError(feats)
    y = TARGETS[target]["y"]
    leak = {y, "label", "stai_score", "pss_score", "phase", "username"} & set(feats)
    if leak:
        raise AssertionError(f"Target/identifier columns {leak} must never be features")
    return list(feats)


def experiment_catalog() -> list[dict]:
    out = []
    for t, tdef in TARGETS.items():
        for e, edef in EXPERIMENTS.items():
            try:
                feats = features_for(t, e)
                out.append({"target": t, "experiment": e, "available": True, "features": feats, **edef})
            except ValueError as reason:
                out.append({"target": t, "experiment": e, "available": False, "reason": str(reason), "features": [], **edef})
    return out


FEATURE_DOCS = {
    "hr_mean": "Mean of valid Fitbit HR samples in the window/segment (bpm).",
    "hr_median": "Median HR (bpm).",
    "hr_std": "Sample standard deviation of HR (bpm). Not HRV: Fitbit gives no beat-to-beat intervals.",
    "hr_min": "Minimum HR (bpm).",
    "hr_max": "Maximum HR (bpm).",
    "hr_iqr": "Interquartile range of HR (bpm).",
    "hr_slope": "Least-squares slope of HR over time within the window (bpm per minute).",
    "hr_mean_delta": "hr_mean minus the participant's calibration median HR (bpm).",
    "hr_median_delta": "hr_median minus calibration median HR (bpm).",
    "hr_mean_ratio": "hr_mean divided by calibration median HR.",
    "hr_mean_z": "(hr_mean - calibration mean) / max(calibration SD, 1 bpm).",
    "hr_std_ratio": "hr_std / max(calibration SD, 1 bpm).",
    "eda_scl_mean": "Mean skin-conductance level (scl_avg) over valid EDA rows of the phase.",
    "eda_scl_std": "SD of scl_avg over valid EDA rows of the phase.",
    "eda_activation_frac": "Fraction of valid EDA rows flagged activation=1 in the phase.",
    "ecg_device_hr": "Heart rate reported by the ECG device for the phase recording (missing if not classified NSR).",
    "reactivity_hr_mean": "Stress-segment hr_mean minus relax-segment hr_mean (bpm).",
}
