# Research methodology

**Project:** Stress Detection in Students Using Wearable Data
**Status:** Prototype for a final-year undergraduate project. It is not a medical device.

This document describes what the software actually does. Section 10 reports results only from runs that were actually executed. Section 11 separates findings from hypotheses and future work.

---

## 1. Research objective

The objective is to investigate whether heart-rate measurements from a consumer wearable can help estimate stress-related outcomes. It also asks whether features expressed relative to each person's own physiological baseline change how well a model performs.

## 2. Research question and hypothesis

**Research question:** Can personalised heart-rate features based on individual physiological baselines improve stress estimation compared with a general machine-learning model?

**Hypothesis (H1):** For participants not seen during training, a model that uses deviations from a personal resting baseline (Experiment B) performs better than a model that uses absolute heart-rate statistics only (Experiment A).

**Null hypothesis (H0):** Per-participant performance does not differ between A and B.

H1 is treated as a hypothesis to test, not as an established fact.

## 3. Dataset

**Source:** QoL_Stress, *a multimodal dataset of physiological and self-reported stress responses*, version 1.0.0. Authors: A. Calvo, A. Cejudo and C. Martin (Fundación Vicomtech). Published on PhysioNet under CC BY 4.0: <https://physionet.org/content/qol-stress/1.0.0/>.

According to the dataset README, 66 healthy adults took part in a controlled session with a relaxation period and an induced-stress period. The PhysioNet project page describes the protocol:
- **Relax phase:** the PSS-14 questionnaire, then a guided relaxation video, then a 30-s ECG and an EDA recording of up to 2 min, then the STAI-S questionnaire.
- **Stress phase:** a Stroop colour test and the Geometry Dash game, then the same ECG and EDA recordings and a second STAI-S.

All signals come from a Fitbit Charge 6. The participants are researchers and staff, not students.

### Verified file structure

These facts were checked by inspecting the downloaded files.

| File | Rows | Participants | Structure (verified) |
|---|---|---|---|
| participants.csv | 66 | 66 | One row per pseudonymised `username` (a SHA-256 hash) |
| fitbit_heart_rate_per_second.csv | 54 462 | 66 | `username, time, value`. **Clock time with no date.** Irregular sampling (median gap 2 s). Between 35 and 1 360 samples per person. No duplicate or out-of-range values |
| fitbit_heart_rate_per_minute.csv | 2 131 | 66 | Per-minute aggregate. 2 duplicate keys |
| fitbit_heart_rate_summary.csv | 264 | 66 | 4 heart-rate zones per person, with minutes counted **over the whole day** |
| stai.csv | 132 | 66 | **2 rows per person** (`phase` = relax, stress), each with a clock time, a total score and 20 item answers |
| pss_14.csv | 66 | 66 | 1 row per person, answered at the start of the session (before heart rate starts). The items ask about "the last month" |
| eda.csv | 20 094 | 64 | `phase` label. `time_sec` is relative to each phase recording, with no clock time. 98 % of rows are `valid_data`. A few rows have negative `time_sec` |
| ecg.csv | 132 | 66 | One short recording per person and phase. Gives the device heart rate, a rhythm class (122 NSR, 10 unclassifiable) and the waveform samples. The dataset page documents 250 Hz (Fitbit Charge 6), which matches the 7,488–7,501 samples per 30-s recording |

### Relationship between questionnaires and physiology (verified)

For every participant, the clock order of events is:

PSS-14 → Fitbit heart rate begins → (relax) → STAI "relax" → (stress) → STAI "stress" ≈ Fitbit heart rate ends.

Across participants, the median time from heart-rate start to STAI-relax is 19.8 min. The median time from STAI-relax to STAI-stress is 11.9 min.

For 65 of the 66 participants, the stress questionnaire is later than the relax questionnaire. The heart-rate recording ends within about 1 minute of the STAI-stress time for most participants.

ECG reading times fall inside the reconstructed phase for most participants. For 13 eligible participants they are offset, usually by about 54 minutes. This looks like a device clock offset. ECG times are therefore **not** used for alignment.

**Scoring checks.** The PSS-14 total can be reproduced exactly (66/66) from the item codes. This uses 0–4 codes, with items 1, 5, 6, 8, 9, 10 and 11 reverse-scored. Those items were identified from their wording.

The STAI total can be reproduced for 128 of 132 rows (97 %). This uses 1–4 scoring, with the 10 positively worded items reverse-scored. The totals provided in the dataset are used unchanged. The 4 mismatches are reported, not corrected.

## 4. Prediction targets and their justification

The questionnaires do **not** give moment-by-moment stress labels. Copying a questionnaire score onto every heart-rate sample would be invalid. The targets below are defined at the level where a label actually exists.

| Target | Unit of analysis | Label | Task | Justification |
|---|---|---|---|---|
| **phase_window** (primary) | 60-s heart-rate window | Protocol phase: relax = 0, stress = 1 | Binary classification | The phase is a property of every moment within it, so labelling each window inside the phase is legitimate. This measures recognition of an **induced-stress condition**, not of perceived stress |
| phase_segment | Last 5 min of each phase (2 per person) | Protocol phase | Binary classification | Lets the EDA and ECG phase summaries be added (Experiment C) |
| stai_state | Last 5 min of each phase | STAI state score (20–80) answered at the end of that phase | Regression | STAI-state measures anxiety "at this moment". The minutes just before the questionnaire are the closest physiological counterpart. A continuous score is modelled with regression rather than forced into arbitrary classes |
| pss14 | Participant (1 row each) | PSS-14 total (0–56) | Regression (exploratory) | PSS-14 refers to the previous month, which is a trait-like quantity. There is only one label per person and n is small, so results are exploratory |

No categorical stress thresholds were invented. The PSS-14 and STAI are kept as continuous scores.

## 5. Inclusion and exclusion criteria

A participant is **eligible** only if all of the following hold:

1. Both STAI timestamps are present, and the stress questionnaire is later than the relax questionnaire.
2. Valid heart-rate samples exist (30–220 bpm).
3. The calibration period (the first 3 minutes of heart rate) contains at least 45 samples, and ends before the relax evaluation period ends.
4. The relax and stress evaluation periods are each at least 3 minutes long, and each has at least 2 valid 60-s windows.
5. Each 5-minute segment has enough samples (at least 15 per minute).
6. The heart-rate recording does not end more than 1 minute before the stress evaluation period ends.

**Result:** 57 of 66 participants are eligible.

The 9 exclusions break down as follows:
- 6 had a calibration period with too few samples.
- 1 had heart rate starting only about 1 minute before the relax questionnaire.
- 1 had a recording that ended early.
- 1 had too few samples in the relax segment.

The Preprocessing page lists every exclusion reason. Excluded participants are left out of **all** experiments, so that comparisons use the same people.

## 6. Preprocessing and feature engineering

### Cleaning

- Clock times are parsed. One ECG value has the form `Tue Dec 17 13:01:42`, and some values have a single-digit hour. The HH:MM:SS part is extracted in both cases.
- Invalid times, heart-rate values outside 30–220 bpm, and duplicate (participant, time) samples are dropped.
- Data are sorted by participant and then by time.
- **No interpolation or forward-filling is done**, so nothing crosses participant boundaries. Missing data are never set to zero.

### Segmentation (all parameters configurable)

| Period | Definition |
|---|---|
| Calibration | `[HR start, HR start + 3 min)` |
| Relax evaluation | `[calibration end, STAI-relax − 2 min)` |
| Stress evaluation | `[STAI-relax + 1 min, STAI-stress − 2 min)` |
| Windows | Non-overlapping 60-s windows in each evaluation period, each with at least 15 samples |
| Segments | The last 5 minutes of each evaluation period |

The 2-minute guard bands remove the time most likely spent filling in the questionnaire. The 1-minute guard after STAI-relax removes the phase transition.

**Assumption:** the STAI timestamp marks the end of its phase. The dataset files do not state this. It is supported by the event order above and by the Fitbit recording ending at the STAI-stress time.

### Features

| Group | Features | Notes |
|---|---|---|
| Heart-rate statistics (A) | mean, median, SD, min, max, IQR, slope (bpm/min) | Computed per window or segment |
| Personal baseline (B) | hr_mean − baseline median, hr_median − baseline median, hr_mean / baseline median, (hr_mean − baseline mean) / max(baseline SD, 1), hr_SD / max(baseline SD, 1) | The baseline comes from the calibration period only |
| Additional physiology (C) | EDA scl mean, EDA scl SD, EDA activation fraction, ECG device heart rate (only when the recording is NSR) | Phase level only |
| Participant level (pss14) | Relax-segment heart-rate statistics; relax and stress deviations from baseline; reactivity (stress − relax mean heart rate); EDA/ECG features of each phase | |

### Features deliberately not computed

- **HRV.** The Fitbit data contain no beat-to-beat intervals. Standard deviation of heart rate is not HRV.
- **ECG waveform features in the app.** The app uses only the device-reported ECG heart rate. Ultra-short HRV (SDNN, RMSSD) from the 250 Hz waveforms is computed only in the research analysis (`research/ecg_hrv.py`). Correction: an earlier version of this document said the sampling rate was undocumented; the dataset page gives 250 Hz.
- **Time of day.** Sessions were scheduled at different times, which would add a confound.
- **Activity.** There are no activity data.
- **Demographics.** Excluded for data minimisation.

### Personal baseline protocol and leakage control

The baseline uses only the **first 3 minutes of each participant's own heart-rate recording**. It uses no labels and no questionnaire information. At deployment time, this is equivalent to asking the user for a short resting calibration before measurement.

Calibration minutes are **excluded from evaluation in every experiment**, including Experiment A. So A and B are scored on exactly the same windows.

Because the calibration always falls at the start of the relax phase, it is closer in time to the relax windows than to the stress windows. This ordering is part of the protocol and is discussed as a confound in Section 9.

## 7. Experimental design

| Experiment | Feature set | Available for |
|---|---|---|
| A. General | Heart-rate statistics | All targets |
| B. Personalised baseline | A + baseline deviations | All targets |
| C. Additional physiology | B + EDA + ECG heart rate | phase_segment, stai_state, pss14 |
| D. Activity-adjusted | — | **Unavailable** |

**Why C is unavailable at window level:** EDA timing is relative to an unknown phase start, and the ECG is one short recording per phase. Neither can be synchronised with individual Fitbit windows.

**Why D is unavailable:** the dataset has no step, accelerometer or activity data for the session. The daily heart-rate-zone summary covers the whole day and cannot be attributed to a phase. An activity-adjusted model would therefore have to be invented, so it was not implemented.

### Models

All models use fixed, pre-declared hyper-parameters. There is **no tuning**, so the test folds are never used for model selection.

**Classification:**
- Majority-class baseline (`DummyClassifier`).
- Logistic Regression (`class_weight=balanced`).
- Random Forest (300 trees, `min_samples_leaf=5`, balanced).
- RBF Support Vector Machine (`C=1`, balanced).

**Regression:**
- Mean baseline (`DummyRegressor`).
- Ridge (`α=1`).
- Random Forest Regressor (300 trees, `min_samples_leaf=5`).
- RBF Support Vector Regression.

Regression targets are standardised inside the model with `TransformedTargetRegressor`. Every model is a scikit-learn `Pipeline` of median imputation, then standard scaling, then the estimator. This means the imputation and scaling are fitted on the training participants only.

## 8. Train/test strategy and evaluation metrics

- **Cross-validation.** Participant-wise 5-fold cross-validation. Participants are shuffled with seed 42 and assigned to folds in turn. All rows from one participant are in exactly one test fold. The code checks that train and test participants never overlap (overlap is 0 in every fold) and stores this with each run.
- **Shared folds.** The same fold assignment is used for every experiment and model of a target. This makes the comparison paired and fair.
- **Metrics.** All metrics are computed from **out-of-fold** predictions, so each prediction comes from a model that never saw that participant. Per-fold means and SDs are also stored. Training-set performance is never reported.
- **Classification metrics:**
  - balanced accuracy
  - macro-F1
  - macro precision and macro recall
  - ROC-AUC, from pooled out-of-fold scores (predicted probability or decision function)
  - confusion matrix
  - per-class report
- **Regression metrics:** MAE, RMSE, R² and Pearson r.
- **Trivial baselines.** Every model is shown next to the majority-class or mean baseline.
- **A vs B and A vs C comparison.** A two-sided Wilcoxon signed-rank test on per-participant metrics, using the same participants and folds. The per-participant metric is balanced accuracy for windows, accuracy for segments, and MAE for regression. These tests are **exploratory and not corrected for multiple comparisons.**
- **Final model.** "Train" on the Model Training page first runs the same cross-validation and stores it. It then fits the pipeline on all eligible participants for use on the Stress Estimation page.

The saved model stores:
- its feature names and schema version
- the target definition
- the training range of each feature
- the dataset fingerprint
- the preprocessing parameters
- the scikit-learn version

Predictions are refused if the schema no longer matches.

## 9. Potential confounding factors

1. **Order effect.** Stress always followed relax in 65 of the 66 sessions. Fatigue, posture changes, time on task and anticipation therefore all vary together with the condition.
2. **Questionnaire and transition activity.** Guard bands reduce this but cannot remove it, because the exact task start and end times are not available.
3. **Physical activity and posture.** These were not measured. Heart-rate changes may reflect movement rather than stress.
4. **Calibration proximity.** The baseline lies just before the relax windows in time.
5. **Device.** Fitbit optical heart rate is noisy and its sampling is irregular.
6. **Session time of day** and individual factors such as caffeine, fitness and medication are unknown.

## 10. Results of the executed runs

**Run details:**
- Run group: `483d862c9b52`.
- Dataset fingerprint: `6a342b432fcef3be`.
- Date: 2026-11-01.
- Software: scikit-learn 1.8.0.
- Sample: 57 participants for every target.
- Validation: 5-fold participant-wise cross-validation.

These numbers come from the stored runs and the exported CSV (Research Experiments → Download CSV). They describe this dataset and this protocol only.

### Primary target: phase_window

1 217 windows: 746 relax and 471 stress.

| Experiment | Model | Balanced acc. | Macro-F1 | ROC-AUC |
|---|---|---|---|---|
| A | Majority baseline | 0.500 | 0.380 | — |
| A | Logistic regression | 0.578 | 0.578 | 0.604 |
| A | Random forest | 0.535 | 0.536 | 0.558 |
| A | SVM | 0.573 | 0.573 | 0.588 |
| B | Logistic regression | 0.602 | 0.602 | 0.608 |
| B | Random forest | 0.566 | 0.566 | 0.579 |
| B | SVM | 0.610 | 0.612 | 0.599 |

Paired comparison of B vs A (per-participant balanced accuracy, n = 57):

| Model | Mean difference | Wilcoxon p |
|---|---|---|
| Logistic regression | +0.022 | 0.11 |
| Random forest | +0.022 | 0.21 |
| SVM | +0.037 | 0.026 |

### phase_segment

114 segments.

| Experiment | Model | Balanced acc. | ROC-AUC |
|---|---|---|---|
| A | Logistic regression | 0.667 | 0.697 |
| B | Logistic regression | 0.675 | 0.689 |
| C | Logistic regression | 0.667 | 0.737 |
| C | Random forest | 0.675 | 0.742 |

None of the B vs A or C vs A differences at this level were statistically reliable (all p ≥ 0.31).

### stai_state

114 segments. The target mean is 35.2 and its SD is 8.2.

- The mean baseline gives MAE 6.67 and R² −0.04.
- Every heart-rate model was **worse than the mean baseline**: MAE 6.99–7.41, with negative R².

### pss14

57 participants.

- The mean baseline gives MAE 6.51.
- No model clearly beat it. The best was Experiment C random forest: MAE 6.58, R² 0.00.
- Some A vs B/C differences reach p < 0.05. However, neither model in those pairs beats the trivial baseline, so the differences are not informative.

## 11. Findings, hypotheses and future work

### Findings (this dataset and protocol only)

- Heart rate from one minute of Fitbit data separates the relax and stress phases only modestly better than chance in participants not seen during training. The best balanced accuracy was about 0.58–0.61.
- Adding personal-baseline features raised balanced accuracy by about 0.02–0.04 for all three classifiers at window level. The paired test reached p < 0.05 only for the SVM (p = 0.026). That result does not survive a correction for the nine A/B/C classifier comparisons. **The evidence is therefore weak and inconclusive: it neither supports nor rules out H1.**
- At segment level, adding EDA and ECG heart rate (Experiment C) gave the highest ROC-AUC values (0.74). However, the paired differences were not significant.
- In this sample, heart-rate features did **not** estimate self-reported STAI-state or PSS-14 scores better than predicting the mean.
- The manipulation check is descriptive only. STAI-state was on average 3.2 points higher after the stress phase (SD 6.2). It was higher for 37 of 57 participants, equal for 11, and lower for 9.

### Hypotheses for further study

- Personal baselines may help more with longer calibration periods, with repeated measurements per person, or with beat-to-beat (HRV) data.

### Future work

- Collect data with the Amazfit device under an approved protocol. This should include repeated self-reports (the in-app 1–5 scale), activity and steps, and a counter-balanced order of the stress and relax conditions.
- Validate on that data before making any claim about Amazfit devices.

### Novelty

No claim of novelty is made. Personalisation by baseline normalisation is an established idea in the affective-computing literature. Any novelty claim would require a systematic literature review, which this document does not contain.

## 12. Limitations

- **What the label measures.** The labels are protocol conditions. A model can only learn what differs between the two lab phases, not "stress" in daily life.
- **Reconstructed boundaries.** Phase boundaries are inferred from questionnaire timestamps.
- **Sample.** The sample is small (57 eligible adults) and is not specifically students. Generalisation is uncertain.
- **Device.** The data are Fitbit only. Results cannot be transferred to Amazfit devices without new validation.
- **Statistics.** The tests are exploratory and uncorrected. With a small n, a non-significant result is not evidence of equivalence.
- **User data.** Records entered through the app (manual, CSV or screenshot) are kept separate from the research data. They are never used in these experiments.

## 13. Reproducibility

1. Install the backend and frontend as described in the README.
2. Place the dataset as described there.
3. Open Research Experiments, select all targets, and click **Run**. Alternatively, call `POST /api/experiments/run` with the body `{"targets": ["phase_window","phase_segment","stai_state","pss14"]}`.

Every run stores:
- its fold assignment
- the seed
- the estimator `repr`
- the preprocessing parameters
- the scikit-learn version
- the dataset fingerprint

You can export these with `GET /api/experiments/results.csv`. With the same dataset files, configuration and library versions, the metrics are deterministic. All estimators are seeded or deterministic, and folds are assigned by seed.
