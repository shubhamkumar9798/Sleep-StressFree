# Research experiments and manuscript

This folder contains the code that produces every number, figure and table in the paper, located at [`../paper/main.tex`](../paper/main.tex).

| File | Purpose |
|---|---|
| `research_gap_analysis.md` | Literature summary, research-gap matrix, the chosen research question, evidence and novelty caveats, and the reference verification log |
| `research_methodology.md` | Dataset, prediction target, preprocessing, features, experimental design, evaluation protocol and limitations |
| `run_research.py` | Runs all experiments and writes `results/results.json` plus CSV files |
| `ecg_hrv.py` | R-peak detection on the 250 Hz ECG (simplified Pan–Tompkins) and ultra-short HRV |
| `make_outputs.py` | Builds `paper/figures/*.pdf|png` and `paper/tables/*.tex` from the results files only |
| `results/` | Generated results: `results.json`, per-participant scores, window predictions and the ECG detector check |

The experiments reuse the application's validated preprocessing (`backend/app/dataset/qol.py`) and model definitions (`backend/app/ml/evaluation.py`). The paper and the app therefore use the same segmentation, features and estimators.

## Reproducing the results (Windows PowerShell, from the project root)

```powershell
# one-time setup (if backend\.venv does not exist yet)
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pip install "matplotlib>=3.9"
cd ..

# 1. run all experiments (a few minutes on a laptop)
.\backend\.venv\Scripts\python research\run_research.py

# 2. regenerate figures and LaTeX tables
.\backend\.venv\Scripts\python research\make_outputs.py
```

**Prerequisites:**
- The QoL_Stress v1.0.0 CSV files must be available. See the main README for where to put them.
- The output is deterministic for the same data, configuration and library versions. Seeds are fixed (`SEED=42`, repeated CV uses seeds 1000–1009) and fold assignment is seeded. The versions used are recorded in `results.json` under `environment`.

## Compiling the paper

LaTeX was not installed on the development machine, so the PDF has **not** been built locally. You can compile it either way:

- **Overleaf.** Upload the whole `paper/` folder (`main.tex`, `references.bib`, `figures/`, `tables/`), then choose the pdfLaTeX compiler. The paper uses the standard `IEEEtran` class, which is included on Overleaf.
- **Local.** Install MiKTeX or TeX Live, then run:

```powershell
cd paper
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

## Integrity notes

- No data are simulated. The only synthetic data in the repository are the clearly labelled fixtures in `backend/tests/`, and they are never used here.
- The transductive per-participant z-score arm uses every window of a test participant, both relax and stress. It is reported **only as an optimistic reference** and is not a deployable protocol.
- Every value in `paper/tables/*.tex` and in the figures is read from `results/results.json`. Numbers quoted in the text were copied from the same file. Re-check them if you re-run the experiments with a different configuration.
