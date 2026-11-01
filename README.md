# Stress Detection in Students Using Wearable Data

This is a research prototype for a final-year engineering project. It asks the following question:

> *Can personalised heart-rate features based on individual physiological baselines improve stress estimation compared with a general machine-learning model?*

The question is investigated on the public **QoL_Stress** dataset (PhysioNet). The app can also take in your own smartwatch data (for example from an Amazfit or Zepp app) by manual entry, CSV upload or screenshot OCR. Your own data are kept separate from the research data, and their source is tracked.

> **Not a medical device.** Outputs are experimental estimates. They do not diagnose stress, anxiety or any other condition.

* Research paper (IEEE LaTeX) and its reproducible experiments: [paper/main.tex](paper/main.tex), [research/README.md](research/README.md)
* Methodology, target justification and actual results: [docs/METHODOLOGY.md](docs/METHODOLOGY.md)
* Every field, its unit and its source: [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md)

---

## 1. Architecture

```
<project root>/
├── qol_stress-…-1.0.0/            ← PhysioNet download (read-only, untouched)
│   └── data/*.csv
├── backend/                       ← Python 3.12, FastAPI, pandas, scikit-learn
│   ├── app/
│   │   ├── main.py                ← FastAPI app, CORS, error handlers
│   │   ├── config.py              ← all settings (env-overridable)
│   │   ├── db.py                  ← SQLite schema (user records, runs, models)
│   │   ├── jobs.py                ← background job runner for training
│   │   ├── dataset/
│   │   │   ├── schema.py          ← expected files/columns, licence, attribution
│   │   │   ├── loader.py          ← discovery, validation, profiling, fingerprint
│   │   │   └── qol.py             ← phase reconstruction, windows, baselines, features
│   │   ├── ml/
│   │   │   ├── definitions.py     ← targets, experiments A–D, feature sets
│   │   │   ├── evaluation.py      ← participant-wise CV, metrics, paired tests
│   │   │   └── registry.py        ← final training, joblib persistence, prediction
│   │   ├── imports/
│   │   │   ├── records.py         ← manual entry, validation, provenance, user baseline
│   │   │   ├── csv_import.py      ← mapping → validation report → confirmed import
│   │   │   └── ocr.py             ← OpenCV + Tesseract, candidate extraction, review
│   │   └── routers/               ← REST endpoints
│   ├── tests/                     ← pytest (synthetic fixtures + real-data integration)
│   ├── requirements.txt
│   └── .env.example
├── frontend/                      ← Next.js 16, React 19, TypeScript, Tailwind 4, Recharts
│   ├── app/                       ← one folder per page
│   ├── components/                ← shadcn-style UI primitives, charts
│   └── lib/                       ← API client, types
└── docs/                          ← methodology and data dictionary
```

The frontend calls the backend over HTTP at `NEXT_PUBLIC_API_URL`, which defaults to `http://localhost:8000`. Persistent state lives in `backend/data/app.db` (SQLite) and `backend/artifacts/models/*.joblib`. The research CSV files are read directly and are **never copied or modified**.

## 2. Requirements

| Tool | Version used | Notes |
|---|---|---|
| Python | 3.12 (3.11+ works) | `python --version` |
| Node.js | 22 (20+ works) | `node --version` |
| Tesseract OCR | 5.x | Optional. Only the screenshot import needs it |

**Tesseract on Windows:** install it from the [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki). The app finds `C:\Program Files\Tesseract-OCR\tesseract.exe` automatically. If you install it somewhere else, set `TESSERACT_CMD` in `backend/.env`. Without Tesseract, everything except screenshot import keeps working.

## 3. Getting the dataset

1. Download the ZIP from <https://physionet.org/content/qol-stress/1.0.0/>. It is open access under CC BY 4.0.
2. Put the data in **one** of these places:
   * Extract the ZIP into the project root, so that `qol_stress-a-multimodal-dataset-of-physiological-and-self-reported-stress-responses-1.0.0/data/*.csv` exists. This is the current set-up.
   * Copy the CSV files into `data/qol_stress/`.
   * Put them anywhere and set `QOL_STRESS_DIR=<folder>` in `backend/.env`.
3. Check the Dataset Explorer page. It should list 8 of 8 files as present.

If the dataset is missing, the app shows setup instructions and disables training. It never substitutes fake data.

| File | Content (verified) | Used for |
|---|---|---|
| fitbit_heart_rate_per_second.csv | Fitbit HR (bpm), clock time, about 2 s sampling | All features |
| stai.csv | STAI state anxiety after the relax phase and after the stress phase, with timestamps | Phase boundaries and STAI target |
| pss_14.csv | PSS-14 (last month), once per person | Participant-level target |
| eda.csv | Skin conductance per phase | Experiment C |
| ecg.csv | One ECG recording per phase, with device HR | Experiment C (device HR only) |
| participants.csv | Demographics | Counts only |
| fitbit_heart_rate_per_minute.csv | Per-minute HR | Explored, not used |
| fitbit_heart_rate_summary.csv | Daily HR-zone minutes | Not used (cannot be linked to a phase) |

## 4. Setup (Windows PowerShell)

Open PowerShell in the project root.

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env        # optional; defaults work without it
.\.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

The API runs at <http://localhost:8000>. Interactive documentation is at <http://localhost:8000/docs>.

### Frontend (second PowerShell window)

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

If PowerShell blocks scripts when you activate a virtual environment, you don't need to activate it. The commands above call `.venv\Scripts\python` directly.

### Production build of the frontend

```powershell
cd frontend
npm run build
npm run start
```

## 5. Using the application

| Page | What it does |
|---|---|
| **Dashboard** | Dataset status, participant counts, selected target, model status, latest real results |
| **Dataset Explorer** | Per-file schema, dtypes, missing values, duplicates, invalid timestamps, sample rows, HR distribution |
| **Data Import** | Manual entry, CSV import, screenshot OCR, and a records explorer with filter, pagination, export and delete |
| **Data Preprocessing** | Phase-reconstruction pipeline, parameters, exclusions, quality checks, feature definitions |
| **Baseline Analysis** | Each participant's calibration baseline, timeline chart and window deviations; baseline for your own records over a chosen period |
| **Model Training** | Train target × experiment × algorithm. Shows cross-validated metrics, confusion matrix or scatter plot, fold table, and saved models with compatibility status |
| **Research Experiments** | Runs all supported experiments, compares A, B and C with paired tests, explains unavailable experiments, CSV download |
| **Stress Estimation** | Exploratory prediction from a heart-rate sequence. Includes input validation, a training-range check and disclaimers |
| **Settings & Docs** | Dataset folder, attribution, OCR status, privacy and consent notice, data dictionary |

### Reproducing the experiments

1. Open **Research Experiments**, tick all targets, and click **Run**. This takes about 40 s.
2. Click **Download CSV summary** to export the results.

You can also do this through the API:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/experiments/run -ContentType "application/json" -Body '{"targets":["phase_window","phase_segment","stai_state","pss14"]}'
```

Every run stores its features, fold assignment, seed, estimator, preprocessing parameters, scikit-learn version and dataset fingerprint.

### Importing a CSV

1. Go to Data Import → CSV import and choose a file.
2. Check the preview. Then check or edit the column mapping:
   * The timestamp column is required.
   * The participant column is optional.
   * Each measurement column needs a type and a unit. Sleep can be in hours and temperature in °F; both are converted.
3. Click **Validate**. The report lists invalid timestamps, missing values, non-numeric values, out-of-range values, duplicates within the file, and duplicates already in the database.
4. Click **Confirm import**. Only valid, new values are stored, with `source = csv`.

Columns named `stress`, `stress_level` and similar are never mapped automatically. You must say whether they are a device score or a self-report. Missing cells are skipped; they are never stored as 0.

### Screenshot extraction

1. Go to Data Import → Screenshot and upload a PNG or JPG.
2. The image is converted to greyscale, inverted if it uses a dark theme, upscaled and thresholded with OpenCV. Tesseract then reads the text.
3. Candidate values are extracted only from visible text with a label or unit. Examples are `72 bpm`, `8,421 steps`, `7h 32min` near "Sleep", and a number near "Stress", which is treated as a **device score**. Low confidence, ambiguity, a missing unit and out-of-range values are all flagged.
4. Review each value against the screenshot, correct it, remove it, or add a value you can see. Enter the measurement date and time, then tick the confirmation box and save. Corrected values are marked `value_was_edited`.
5. Charts are never interpreted, and no value that is not printed in the image is ever created.

By default only the screenshot's file name and SHA-256 hash are kept. Set `STORE_SCREENSHOTS=true` to keep the files in `backend/data/uploads/screenshots/`.

### Interpreting predictions

The primary model answers one question: *does this minute of heart rate look more like the relax phase or the stress phase of the QoL_Stress lab protocol?* It is **not** a measure of how stressed someone feels.

Read each prediction alongside:
* the cross-validated metrics shown with it (balanced accuracy of about 0.6 means it is often wrong)
* the training-range check

Personalised models need at least 45 resting calibration readings. A single heart-rate reading is always rejected. The app makes no claim about accuracy on Amazfit data.

## 6. API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/dashboard` | Dashboard summary |
| GET | `/api/dataset/status` | File presence, attribution, fingerprint, setup message |
| GET | `/api/dataset/files/{name}/validate` | Schema, missing values, duplicates, timestamps, ranges |
| GET | `/api/dataset/files/{name}/preview?n=10` | Sample rows |
| GET | `/api/dataset/hr-distribution` | Histogram of window mean HR by phase |
| POST | `/api/dataset/directory` | Use another dataset folder for this session |
| GET | `/api/preprocessing/summary` | Pipeline parameters, exclusions, quality checks |
| POST | `/api/preprocessing/run` | Re-run preprocessing from the raw files |
| GET | `/api/baseline/participants` | Calibration baselines for all participants |
| GET | `/api/baseline/participants/{username}` | Timeline and window deviations |
| GET | `/api/baseline/user?participant_code&start&end` | Baseline for your own HR records |
| GET | `/api/experiments/catalog` | Targets, experiments (with reasons when unavailable), models |
| POST | `/api/experiments/run` | Run experiments (background job) |
| GET | `/api/jobs/{id}` | Job progress and result |
| GET | `/api/experiments/results` | Stored runs and paired comparisons |
| GET | `/api/experiments/results.csv` | CSV summary of experiments |
| POST | `/api/models/train` | Cross-validate, then fit and save a model (background job) |
| GET | `/api/models`, `/api/models/{id}` | Saved models with compatibility checks |
| POST | `/api/predict` | Exploratory prediction from an HR sequence |
| GET | `/api/records/metrics` | Allowed measurement types, units and ranges |
| POST | `/api/records/manual` | Manual entry |
| GET | `/api/records`, `/api/records/summary`, `/api/records/export.csv` | Records explorer and export |
| DELETE | `/api/records/{id}`, `/api/batches/{id}` | Delete a record or a whole import (withdrawal) |
| POST | `/api/imports/csv/preview` · `/validate` · `/commit` | CSV import steps |
| DELETE | `/api/imports/csv/{token}` | Discard a pending CSV upload |
| GET | `/api/imports/screenshot/status` | Tesseract availability |
| POST | `/api/imports/screenshot/extract` · `/commit` | OCR extraction and confirmed save |
| DELETE | `/api/imports/screenshot/{token}` | Discard a pending screenshot |

Errors return `{"error": "...", "details": ...}` with an appropriate status code:
* 404: not found
* 409: dataset missing, job running, or stale model
* 413/415: file too large or wrong type
* 422: validation error
* 503: OCR unavailable

## 7. Tests and checks

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```

```powershell
cd frontend
npm run lint
npm run typecheck
npm run build
```

The backend tests use a **synthetic test fixture**: clearly labelled, fabricated CSV files written to a temporary folder at test time. They exercise:
* schema validation and a missing dataset
* segmentation and calibration exclusion
* participant-wise CV with no overlap
* identical folds across experiments
* training and prediction validation, including stale schemas, single readings and out-of-range input
* CSV import (mapping, invalid rows, duplicates, no automatic stress labels)
* manual entry validation
* OCR candidate rules

When Tesseract and Arial are present, the tests also run a real OCR round-trip. When the real dataset is present, an integration test checks the real pipeline (66 participants, 57 eligible, PSS scoring verified). Synthetic fixtures are never used for research results.

## 8. Known limitations

* Labels are **protocol conditions**, reconstructed from questionnaire timestamps. They are not momentary self-reported stress. The relax phase always comes first, which is a confound.
* There are 57 eligible adults. The sample is not specifically students and it is lab-based. Heart rate comes from Fitbit only.
* No activity data exist, so Experiment D is disabled. EDA and ECG cannot be aligned to individual windows.
* In the executed runs, heart-rate features did not beat a mean baseline for STAI-state or PSS-14. Personalisation gave small, statistically weak gains for phase recognition (see the methodology document).
* **Amazfit:** no API is used and there is no tested export format. The import architecture is modular, so a dedicated Amazfit/Zepp export parser can be added under `backend/app/imports/` once a real export file is available. Until then, use CSV import or manual entry. Fitbit results do **not** validate the app on Amazfit.
* There is no authentication. Run the app locally only. CORS allows only `FRONTEND_ORIGIN`.
* OCR quality depends on the screenshot. Every value must be confirmed by the user.

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| Frontend says "Cannot reach the backend" | Start the backend (Section 4). Check that port 8000 is free. If you changed the API address, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` |
| Dashboard says "dataset not found" | Check the folder in Settings → Dataset location, or set `QOL_STRESS_DIR` |
| CORS error in the browser | The frontend must run on `http://localhost:3000`, or you must set `FRONTEND_ORIGIN` |
| "OCR unavailable" | Install Tesseract, or set `TESSERACT_CMD` |
| Prediction refused as "Retrain" | The feature schema or preprocessing changed since training. Train the model again |
| `npm run dev` shows `_ref is not defined` or an SWC panic | A `browserslist` in a parent folder's package.json was targeting old browsers. `frontend/package.json` now pins modern targets; delete `frontend/.next` and restart |
| Another job is running (409) | Wait for the current training or experiment run to finish |

## 10. Privacy, consent and ethics

* The tool stores only pseudonymous participant codes. It rejects values that look like e-mail addresses.
* Obtain informed consent through your institution's approved procedure before collecting any data.
* Withdrawal: delete a participant's records on the Imported records page, or delete their import batches with `DELETE /api/batches/{id}`.
* QoL_Stress demographics are not used as features.
* The general wellbeing suggestions are fixed, non-medical text. They are not generated by the model, and the app gives no medication advice.

## 11. Dataset attribution and licence

This project uses the following dataset:

> Calvo, A., Cejudo, A., & Martin, C. *QoL_Stress: a multimodal dataset of physiological and self-reported stress responses* (version 1.0.0). PhysioNet. <https://physionet.org/content/qol-stress/1.0.0/>

The dataset is licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**. When you use it, cite the dataset as above. Also cite the standard PhysioNet reference:

> Goldberger, A., et al. (2000). PhysioBank, PhysioToolkit, and PhysioNet: Components of a new research resource for complex physiologic signals. *Circulation*, 101(23), e215–e220.

Check the PhysioNet page for the authors' preferred citation. The original files are distributed unchanged; this project only reads them.
# Sleep-StressFree
