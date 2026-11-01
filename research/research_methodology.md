# Research methodology for the paper

This document describes the methodology used in `paper/main.tex`. The application's own methodology document (`docs/METHODOLOGY.md`) covers the prototype app. This document adds the paper-specific experiments: ablations, controls, HRV, bootstrap, Holm correction and nested tuning.

## 1. Dataset (verified against the files and the PhysioNet page)

**Source and licence.** QoL_Stress v1.0.0, PhysioNet, DOI 10.13026/vqtz-pm70, released under the CC BY 4.0 licence.

**Participants.** 66 adults: 39 male and 27 female, mean age 29.7 years (SD 6.9).
- Job categories in `participants.csv`: researchers and staff (Junior Researcher 31, Researcher 16, Senior Researcher 6, Junior Staff 6, Senior Staff 5, Staff 2).
- **They are not students.**

**Device.** Fitbit Charge 6 for heart rate (HR), ECG and EDA.

**Protocol (session of about 30 min), as described on the dataset page:**
1. PSS-14 questionnaire.
2. Guided relaxation video.
3. 30-s ECG, then EDA recording (≤ 2 min).
4. STAI-S questionnaire.
5. Stroop colour test and the Geometry Dash game.
6. 30-s ECG, then EDA recording (≤ 2 min).
7. STAI-S questionnaire.

HR was recorded throughout. Calendar dates were removed from the data; clock times were kept.

**Inspected files.**
- `fitbit_heart_rate_per_second.csv`: 54,462 rows, 66 IDs.
- `stai.csv`: 132 rows (2 per participant).
- `pss_14.csv`: 66 rows.
- `eda.csv`: 20,094 rows, 64 IDs (8 EDA recordings are missing).
- `ecg.csv`: 132 recordings of 7,488–7,501 samples each (30 s at 250 Hz).

Exact counts are in `results/results.json` under `dataset`.

## 2. Prediction target and rationale

The **primary** task is to classify each 60-s window of Fitbit HR as coming from the relax phase or the induced-stress phase of the protocol. Notes on this target:

- It is the only label available at moment level.
- It is a protocol condition, not perceived stress, and is never described as perceived stress.
- PSS-14 refers to the past month. STAI-S gives two scores per person, each describing the state at the end of a phase. Neither is used as a label for individual windows.
- STAI-S and PSS-14 regression results are reported only as secondary analyses.

## 3. Preprocessing (shared with the app)

**Phase reconstruction.** The STAI-S timestamps mark the end of each phase. This is an assumption, supported by the order of events in the files. It was not used for ECG time alignment, because about 13 eligible participants have offsets of roughly 54 min, which look like a device clock problem.

**Periods** (t₀ is the first HR sample; STAI_r and STAI_s are the relax and stress STAI-S timestamps):

| Period | Interval |
|---|---|
| Calibration | [t₀, t₀ + 3 min) |
| Relax evaluation | [t₀ + 3 min, STAI_r − 2 min) |
| Stress evaluation | [STAI_r + 1 min, STAI_s − 2 min) |

**Windows.** Non-overlapping 60-s windows with at least 15 valid samples (HR between 30 and 220 bpm).

**Eligibility.** 57 of 66 participants are eligible. The reasons for each exclusion are logged.

**Data handling.** No interpolation or forward-fill is applied to HR.

## 4. Features

Let h be the valid HR samples in a window, and let the participant's calibration samples have mean μ_c, median m_c and standard deviation σ_c. Define σ̃ = max(σ_c, 1 bpm).

**A (absolute):**
- mean, median, SD, min, max and IQR of h
- OLS slope of h against time (bpm/min)

**R (relative, label-free):**
- mean(h) − m_c
- median(h) − m_c
- mean(h) / m_c
- (mean(h) − μ_c) / σ̃
- SD(h) / σ̃

**A+R:** both sets together.

**Zt (reference only):** each A feature z-scored using all of that participant's evaluation windows. This is similar to cStress-style per-participant normalization. It is not deployable because it uses future windows from both classes.

**T (control):** minutes since the first HR sample, used as the only feature.

**Segment-level features** are computed over the last 5 min of each phase's evaluation period:
- A and R as above
- EDA: mean and SD of SCL, and the fraction of activation, over rows with valid_data = True and time_sec ≥ 0
- ECG HRV: derived HR, SDNN and RMSSD from R-peaks. Peaks are found with a simplified Pan–Tompkins detector: 5–15 Hz band-pass, derivative, squaring, 150-ms integration, 300-ms refractory period. RR intervals are kept only if they lie in 300–2000 ms and within ±30 % of the median. A recording needs at least 15 RR intervals. The detector was validated against the device-reported HR (see results).

## 5. Models and evaluation

**Models.**
- Majority-class baseline.
- Logistic regression, class_weight = balanced.
- Random forest: 300 trees, min_samples_leaf = 5, balanced.
- RBF SVM: C = 1, gamma = scale, balanced.
- Every model is an `SimpleImputer(median) → StandardScaler → model` pipeline, so all preprocessing is fitted on training participants only.

**Cross-validation.**
- Participant-wise 5-fold CV. Folds are assigned by shuffling participants with seed 42.
- The same folds are used for every feature set and model.
- The code asserts that no participant appears in both training and test data.

**Metrics.**
- Computed on pooled out-of-fold predictions: balanced accuracy (BA), macro-F1, recall per class, ROC-AUC and the confusion matrix.
- Per-participant BA is also recorded.

**Uncertainty.**
- 95 % participant-cluster bootstrap with 2,000 resamples. Paired differences use the same resamples for both models.
- Repeated CV with 10 different fold seeds.

**Hypothesis tests.**
- Two-sided Wilcoxon signed-rank test on per-participant BA.
- Holm correction within each family. The window family has 6 tests (3 models × 2 comparisons); the segment family has 12 tests.

**Sensitivity analyses.**
- Calibration length of 1, 2 or 3 min, with the evaluation windows unchanged.
- Nested hyper-parameter tuning, with an inner GroupKFold(4) on training participants only.

## 6. Controls for confounds and leakage

**Record-wise CV.** Stratified 5-fold CV that ignores participant identity. Comparing it with participant-wise CV shows how much leakage inflates the scores.

**Time-only classifier.** A classifier given only the time since the first HR sample. It measures how separable the classes are from protocol order alone.

**Temporally matched subset.** For each participant, the last 3 relax windows and the first 3 stress windows. These are the closest in time to the phase boundary, so drift has the least room to differ between classes.

**Drift-only negative control.** A classifier that separates the first half of each participant's relax windows from the second half. Both halves have the same condition, so any skill above chance reflects drift alone.

**Within-phase HR slopes.** Descriptive estimates of how HR changes over time inside each phase.

## 7. Error analysis

- Accuracy by window position relative to the phase boundary.
- Distribution of per-participant BA.
- Spearman correlations of per-participant BA with ΔSTAI-S, segment ΔHR, baseline HR and baseline SD.
- Counts of false positives and false negatives.
- Grouped permutation importance on held-out folds (20 repeats per fold).

## 8. Limitations

- **Labels.** The labels are protocol conditions. The fixed order (relax, then stress) is confounded with time. The ECG and EDA recordings are made after each stressor.
- **Sample.** 57 eligible adults from a single research institute, with no students.
- **Signals.** HR comes only from Fitbit optical sensing. There are no activity data. The HRV is ultra-short (30 s).
- **Generalization.** There is no external or cross-dataset validation and no Amazfit validation.
- **Statistics.** Small-n cross-validation has wide error bars [varoquaux2018cv].
