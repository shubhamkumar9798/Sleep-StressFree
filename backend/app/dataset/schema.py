"""Expected structure of the QoL_Stress (PhysioNet, v1.0.0) CSV files.

Column lists were taken from the dataset's README.md and then checked against
the actual downloaded files. Questionnaire item columns are not listed as
required because only `score` is used by the pipeline.
"""
from __future__ import annotations

DATASET_NAME = "QoL_Stress: a multimodal dataset of physiological and self-reported stress responses"
DATASET_VERSION = "1.0.0"
DATASET_URL = "https://physionet.org/content/qol-stress/1.0.0/"
DATASET_LICENSE = "Creative Commons Attribution 4.0 International (CC BY 4.0)"
DATASET_AUTHORS = "Amaia Calvo, Ander Cejudo, Cristina Martin (Fundacion Vicomtech)"
DEVICE_NOTE = "Heart rate in this dataset was recorded with Fitbit devices. It is NOT Amazfit data."

# role: how the pipeline uses the file
EXPECTED_FILES: dict[str, dict] = {
    "participants.csv": {
        "required_columns": ["username", "sex", "age", "education_level", "job_category"],
        "time_columns": [],
        "description": "Participant demographics (one row per pseudonymised participant).",
        "role": "Participant counts only. Demographics are not used as model features (data minimisation).",
        "used_by_pipeline": True,
    },
    "fitbit_heart_rate_per_second.csv": {
        "required_columns": ["username", "time", "value"],
        "time_columns": ["time"],
        "description": "Fitbit heart rate (bpm), irregular ~1-5 s sampling, time of day only (no date).",
        "role": "Primary physiological signal for all experiments.",
        "used_by_pipeline": True,
    },
    "fitbit_heart_rate_per_minute.csv": {
        "required_columns": ["username", "time", "value"],
        "time_columns": ["time"],
        "description": "Fitbit heart rate aggregated per minute.",
        "role": "Explored only; the per-second file is used for features because it has finer resolution.",
        "used_by_pipeline": False,
    },
    "fitbit_heart_rate_summary.csv": {
        "required_columns": ["username", "zone_name", "min", "max", "minutes", "caloriesOut"],
        "time_columns": [],
        "description": "Daily Fitbit heart-rate-zone summary (minutes per zone over the whole day).",
        "role": "Not used: daily totals cannot be attributed to the relax/stress phases (see Experiment D).",
        "used_by_pipeline": False,
    },
    "stai.csv": {
        "required_columns": ["username", "time", "phase", "score"],
        "time_columns": ["time"],
        "description": "STAI state-anxiety questionnaire, answered once after the relax phase and once after the stress phase.",
        "role": "Phase timing (questionnaire timestamps) and the STAI-state regression target.",
        "used_by_pipeline": True,
    },
    "pss_14.csv": {
        "required_columns": ["username", "time", "score"],
        "time_columns": ["time"],
        "description": "Perceived Stress Scale (14 items, 'in the last month'), answered once per participant.",
        "role": "Participant-level regression target (exploratory).",
        "used_by_pipeline": True,
    },
    "eda.csv": {
        "required_columns": ["username", "phase", "time_sec", "valid_data", "activation", "scl_avg"],
        "time_columns": [],
        "description": "Electrodermal activity per phase; time_sec is relative to the start of the phase recording.",
        "role": "Phase-level EDA features (Experiment C). Not clock-aligned with Fitbit data.",
        "used_by_pipeline": True,
    },
    "ecg.csv": {
        "required_columns": ["username", "phase", "reading_time", "heart_rate", "result_classification"],
        "time_columns": ["reading_time"],
        "description": "One short single-lead ECG recording per phase with device-reported heart rate and waveform samples.",
        "role": "Device-reported ECG heart rate per phase (Experiment C). Waveforms (30 s at 250 Hz) are not processed by the app; research/ecg_hrv.py derives HRV from them.",
        "used_by_pipeline": True,
    },
}

PHASES = ("relax", "stress")
