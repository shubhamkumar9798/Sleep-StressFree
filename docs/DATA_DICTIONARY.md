# Data dictionary

This dictionary covers three groups of data:

1. **Public research data.** These are the QoL_Stress CSV files. The app only reads them and never changes them.
2. **Derived analysis tables.** The backend computes these in memory from the research data.
3. **User records.** These are the measurements you enter yourself. They are stored in SQLite, at `backend/data/app.db`.

Notation used below: "HR" means heart rate in beats per minute (bpm). "Clock time" means a time of day in `HH:MM:SS` form, with no date.

---

## 1. QoL_Stress source files (PhysioNet v1.0.0, CC BY 4.0)

| File | Field | Type / unit | Meaning | Used? |
|---|---|---|---|---|
| participants.csv | username | text (SHA-256 pseudonym) | Participant identifier shared by all files | Counts only |
| | sex, age, education_level, job_category | text / years | Demographics | **Not used** (data minimisation) |
| fitbit_heart_rate_per_second.csv | username | text | Participant | Yes |
| | time | clock time | Sample time. Samples are irregular, with a median gap of about 2 s | Yes |
| | value | bpm | Fitbit optical HR | Yes (primary signal) |
| fitbit_heart_rate_per_minute.csv | username, time, value | as above | Per-minute HR | Explored only |
| fitbit_heart_rate_summary.csv | zone_name, min, max, minutes, caloriesOut | bpm, min, kcal | Daily HR-zone totals | Not used (cannot be attributed to a phase) |
| stai.csv | username, time | clock time | When the STAI state questionnaire was submitted | Phase boundaries |
| | phase | `relax` / `stress` | The phase the questionnaire refers to | Yes |
| | score | 20–80 | STAI state-anxiety total, as provided | Regression target |
| | 20 item columns | `0. Not at all` … `3. Very much` | Item answers | Used only to check the scoring |
| pss_14.csv | username, time | clock time | PSS-14 answered once before the session | – |
| | score | 0–56 | Perceived Stress Scale total, as provided ("in the last month") | Participant-level target |
| | 14 item columns | `0`–`4` codes; some labels are in Spanish | Item answers | Used only to check the scoring |
| eda.csv | phase | relax / stress | Phase of the EDA recording | Yes |
| | time_sec | s | Seconds from the start of the phase recording (not clock time) | Filter (rows with time_sec < 0 are dropped) |
| | valid_data | bool | Device validity flag | Filter (rows with False are dropped) |
| | activation | 0/1 | Device activation flag | Feature (fraction of rows equal to 1) |
| | scl_avg | device units (skin-conductance level) | Mean skin conductance level | Feature (mean and SD) |
| ecg.csv | reading_time | clock time | Time of the ECG recording. About 13 eligible participants show a clock offset of roughly 54 min | Quality flag only |
| | phase | relax / stress | Phase of the recording | Yes |
| | heart_rate | bpm | HR reported by the device | Feature (only when result_classification = NSR) |
| | result_classification | `NSR` / `UNCLASSIFIABLE` | Device rhythm classification | Filter |
| | waveform_samples | text | Raw 30-s waveform, 250 Hz (about 7,500 samples; per the dataset page) | Not used by the app; the paper derives HRV from it (`research/ecg_hrv.py`) |

## 2. Derived analysis tables (backend `app/dataset/qol.py`)

### Session table: one row per participant

| Field | Unit | Definition |
|---|---|---|
| hr_start / hr_end | clock seconds | First and last valid HR sample |
| stai_relax_t / stai_stress_t | clock seconds | STAI timestamps. They are taken as the end of each phase |
| calib_start / calib_end | clock seconds | `[hr_start, hr_start + 3 min)` |
| relax_eval_start / end | clock seconds | `[calib_end, stai_relax_t − 2 min)` |
| stress_eval_start / end | clock seconds | `[stai_relax_t + 1 min, stai_stress_t − 2 min)` |
| base_mean, base_median, base_sd, base_n | bpm, count | Statistics of the HR samples in the calibration period |
| eligible, exclusion_reasons | bool, list | Result of the eligibility checks (see the methodology document) |
| ecg_clock_consistent | bool | Whether each ECG reading time falls inside its reconstructed phase |

### Window table: one row per 60-second window (target `phase_window`)

| Field | Unit | Definition |
|---|---|---|
| phase / label | text / 0-1 | relax = 0, stress = 1 (the protocol condition) |
| window_start, minutes_from_hr_start | s, min | Window position |
| n_samples | count | Valid HR samples in the window (at least 15) |
| hr_mean, hr_median, hr_std, hr_min, hr_max, hr_iqr | bpm | Statistics of the samples in the window. hr_std uses ddof = 1 |
| hr_slope | bpm/min | Least-squares slope of HR against time within the window |
| hr_mean_delta, hr_median_delta | bpm | Statistic minus base_median |
| hr_mean_ratio | ratio | hr_mean ÷ base_median |
| hr_mean_z | z | (hr_mean − base_mean) ÷ max(base_sd, 1 bpm) |
| hr_std_ratio | ratio | hr_std ÷ max(base_sd, 1 bpm) |

### Segment table: two rows per participant (targets `phase_segment`, `stai_state`)

This table has the same HR and personal features as the window table. They are computed over the **last 5 minutes** of each phase's evaluation period. It also has these columns:

| Field | Unit | Definition |
|---|---|---|
| stai_score | 20–80 | STAI state score answered at the end of this phase |
| eda_scl_mean, eda_scl_std | device units | Statistics of scl_avg over valid EDA rows of this phase |
| eda_activation_frac | 0–1 | Mean of activation over valid EDA rows |
| ecg_device_hr | bpm | ECG device HR for this phase. Missing if the recording is not NSR |

### Participant table: one row per participant (target `pss14`)

| Field | Definition |
|---|---|
| rest_hr_* | Relax-segment HR statistics |
| rest_/stress_hr_mean_delta, _ratio, _z | Relax and stress segment deviations from the calibration baseline |
| reactivity_hr_mean | Stress-segment hr_mean minus relax-segment hr_mean |
| rest_/stress_eda_*, rest_/stress_ecg_device_hr | EDA and ECG features of each phase |
| pss_score | PSS-14 total (the target) |

## 3. User records (`user_records` table)

| Field | Type | Meaning |
|---|---|---|
| id | int | Primary key |
| batch_id | int | Import batch, so a whole upload can be deleted together |
| source | `manual` / `csv` / `screenshot` | How the value entered the system (provenance) |
| device_label | text | Free text supplied by the user, e.g. "Amazfit (model not confirmed)". It is not verified |
| participant_code | text ≤ 40 chars | Pseudonymous code. Names and e-mail addresses are rejected |
| recorded_at | ISO-8601 local date-time | When the measurement was taken |
| metric | enum (below) | Measurement type |
| value | real | Value in the canonical unit |
| unit | text | Canonical unit |
| raw_value_text | text | Exactly what was typed, read by OCR, or found in the CSV cell |
| value_was_edited | 0/1 | 1 if the user changed the value or type that OCR extracted |
| verified_device_measurement | 0/1 | Always 0. Nothing entered through the UI is treated as a verified device reading |
| extraction_flags | JSON list | OCR or CSV warnings, e.g. low confidence or a unit conversion |
| notes | text | Free-text context |
| created_at | ISO-8601 UTC | When the record was stored |

| metric | Unit | Valid range | Notes |
|---|---|---|---|
| heart_rate | bpm | 30–220 | |
| resting_heart_rate | bpm | 30–150 | |
| steps | steps | 0–100 000 (integer) | |
| sleep_duration | min | 0–1440 | CSV values in hours are converted (× 60) |
| hrv | ms | 1–300 | As reported by the device. The algorithm is unknown |
| spo2 | % | 70–100 | |
| body_temperature | °C | 30–43 | CSV values in °F are converted |
| device_stress_score | device scale | 0–100 | The manufacturer's proprietary score. It is **never** used as ground truth |
| self_reported_stress | 1–5 (integer) | 1–5 | 1 means not stressed and 5 means extremely stressed. It is only ever entered by the participant |

Missing values are never stored. An empty field means no row is created. Missing values are never stored as zero.

## 4. Other tables

* `import_batches`: source, filename, the file's SHA-256, device label, the stored screenshot name (only if `STORE_SCREENSHOTS=true`), and validation details.
* `experiment_runs`: target, experiment, model, the sizes of the participant set and the sample set, the full configuration (features, fold assignment, seed, estimator, preprocessing parameters, scikit-learn version), the metrics, the details (confusion matrix, folds, per-participant scores) and the dataset fingerprint.
* `trained_models`: the path to the joblib artifact, the feature list, the cross-validation run it came from, the dataset fingerprint, and whether it is active.
* `prediction_log`: the inputs, outputs and input source of each exploratory prediction.
