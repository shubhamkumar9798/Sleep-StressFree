"""Figures (PDF + PNG) and LaTeX tables for the paper, generated only from
research/results/*.json|csv produced by run_research.py (plus the raw dataset
for the illustrative timeline in Fig. 2).

Run from the project root:
    backend\\.venv\\Scripts\\python research\\make_outputs.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("APP_DB_PATH", str(Path(tempfile.gettempdir()) / "qol_research_unused.db"))
sys.path.insert(0, str(ROOT / "backend"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

RES = Path(__file__).resolve().parent / "results"
FIG = ROOT / "paper" / "figures"
TAB = ROOT / "paper" / "tables"
FIG.mkdir(parents=True, exist_ok=True)
TAB.mkdir(parents=True, exist_ok=True)
R = json.loads((RES / "results.json").read_text())

plt.rcParams.update({
    "font.size": 8, "font.family": "serif", "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "figure.dpi": 150, "savefig.bbox": "tight", "axes.spines.top": False,
    "axes.spines.right": False,
})
COL1 = 3.45  # IEEE single-column width (in)
COL2 = 7.16
MODEL_LABEL = {"dummy": "Majority", "logistic_regression": "LR", "random_forest": "RF", "svm": "SVM"}
FS_LABEL = {"A_absolute": "Absolute (A)", "R_relative_only": "Relative only (R)",
            "AR_absolute_plus_relative": "Absolute + relative (A+R)", "Zt_transductive_zscore": "Transductive z-score",
            "T_time_only": "Time only"}
C = {"A_absolute": "#4c6ef5", "R_relative_only": "#12b886", "AR_absolute_plus_relative": "#f08c00",
     "Zt_transductive_zscore": "#868e96", "T_time_only": "#c92a2a"}


def save(fig, name):
    fig.savefig(FIG / f"{name}.pdf")
    fig.savefig(FIG / f"{name}.png", dpi=300)
    plt.close(fig)


def f3(x):
    return "--" if x is None else f"{x:.3f}"


# ---------------------------------------------------------------- Fig. 1 (conceptual)
def fig_workflow():
    fig, ax = plt.subplots(figsize=(COL2, 1.35))
    ax.axis("off")
    steps = [
        ("QoL_Stress\n(66 participants)", "Fitbit HR, STAI-S,\nPSS-14, EDA, ECG"),
        ("Phase\nreconstruction", "STAI timestamps,\nguard bands"),
        ("Calibration,\nwindowing", "first 3 min = baseline,\n60-s windows"),
        ("Feature sets", "A, R, A+R\n(+EDA, HRV)"),
        ("Participant-wise\n5-fold CV", "pipelines fitted on\ntraining participants"),
        ("Analysis", "bootstrap CI, Holm,\ncontrols, errors"),
    ]
    w, gap = 0.150, 0.018
    for i, (t, s) in enumerate(steps):
        x = 0.012 + i * (w + gap)
        ax.add_patch(FancyBboxPatch((x, 0.18), w, 0.7, boxstyle="round,pad=0.008", fc="#eef0fb", ec="#3f51b5", lw=0.8))
        ax.text(x + w / 2, 0.66, t, ha="center", va="center", fontsize=6.2, weight="bold")
        ax.text(x + w / 2, 0.36, s, ha="center", va="center", fontsize=5.4, color="#333")
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + w + gap - 0.003, 0.53), xytext=(x + w + 0.003, 0.53),
                        arrowprops=dict(arrowstyle="->", lw=0.8, color="#3f51b5"))
    ax.text(0.5, 0.02, "Conceptual diagram of the implemented pipeline (not a data plot).", ha="center", fontsize=6, style="italic", color="#555")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    save(fig, "fig1_workflow")


# ---------------------------------------------------------------- Fig. 2 example timeline (real data)
def fig_timeline():
    from app.dataset import qol

    p = qol.build()
    s = p.sessions[p.sessions.eligible].iloc[0]
    u = s["username"]
    h = p.hr[p.hr.username == u]
    t = (h["t"] - s["hr_start"]) / 60
    m = lambda k: (s[k] - s["hr_start"]) / 60  # noqa: E731
    fig, ax = plt.subplots(figsize=(COL1, 1.7))
    ax.axvspan(0, m("calib_end"), color="#3f51b5", alpha=0.12, lw=0)
    ax.axvspan(m("relax_eval_start"), m("relax_eval_end"), color="#0e9f8e", alpha=0.12, lw=0)
    ax.axvspan(m("stress_eval_start"), m("stress_eval_end"), color="#e0662b", alpha=0.12, lw=0)
    ax.plot(t, h["value"], lw=0.6, color="#222")
    ax.axhline(s["base_median"], color="#3f51b5", lw=0.8, ls="--")
    for k, c in (("stai_relax_t", "#0e9f8e"), ("stai_stress_t", "#e0662b")):
        ax.axvline(m(k), color=c, lw=0.9, ls=":")
    y1 = ax.get_ylim()[1]
    ax.text(m("calib_end") / 2, y1, "calib.", ha="center", va="top", fontsize=6)
    ax.text((m("relax_eval_start") + m("relax_eval_end")) / 2, y1, "relax", ha="center", va="top", fontsize=6)
    ax.text((m("stress_eval_start") + m("stress_eval_end")) / 2, y1, "stress", ha="center", va="top", fontsize=6)
    ax.set_xlabel("Time from first HR sample (min)")
    ax.set_ylabel("Heart rate (bpm)")
    save(fig, "fig2_timeline")


# ---------------------------------------------------------------- Fig. 3 window-level BA with CIs
def fig_window():
    W = R["window"]
    fig, ax = plt.subplots(figsize=(COL1, 2.0))
    models = ["logistic_regression", "random_forest", "svm"]
    sets = ["A_absolute", "R_relative_only", "AR_absolute_plus_relative"]
    width = 0.25
    for j, fs in enumerate(sets):
        xs, ys, lo, hi = [], [], [], []
        for i, m in enumerate(models):
            d = W[f"{fs}|{m}"]
            xs.append(i + (j - 1) * width)
            ys.append(d["balanced_accuracy"])
            lo.append(d["balanced_accuracy"] - d["ba_ci95"][0])
            hi.append(d["ba_ci95"][1] - d["balanced_accuracy"])
        ax.bar(xs, ys, width * 0.92, yerr=[lo, hi], color=C[fs], label=FS_LABEL[fs], capsize=1.5, error_kw={"lw": 0.6})
    ax.axhline(0.5, color="k", lw=0.6, ls="--")
    ax.text(2.45, 0.505, "chance", fontsize=6, ha="right", va="bottom")
    ax.set_xticks(range(3), [MODEL_LABEL[m] for m in models])
    ax.set_ylim(0.4, 0.75)
    ax.set_ylabel("Balanced accuracy")
    ax.legend(loc="upper left", frameon=False, ncol=1)
    save(fig, "fig3_window_ba")


# ---------------------------------------------------------------- Fig. 4 per-participant A vs A+R
def fig_pp():
    df = pd.read_csv(RES / "per_participant_ba_window.csv", index_col=0)
    a, b = df["A_absolute|logistic_regression"], df["AR_absolute_plus_relative|logistic_regression"]
    fig, ax = plt.subplots(figsize=(COL1 * 0.85, COL1 * 0.85))
    ax.scatter(a, b, s=10, color="#f08c00", edgecolor="k", lw=0.3, alpha=0.85)
    ax.plot([0, 1], [0, 1], color="k", lw=0.6, ls="--")
    ax.axhline(0.5, color="#aaa", lw=0.5)
    ax.axvline(0.5, color="#aaa", lw=0.5)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Per-participant BA, absolute (A), LR")
    ax.set_ylabel("Per-participant BA, A+R, LR")
    c = R["window_comparisons"]["AR_absolute_plus_relative vs A_absolute|logistic_regression"]
    ax.text(0.02, 0.98, f"above diagonal: {c['n_better']}\nbelow: {c['n_worse']}, tied: {c['n_tied']}", va="top", fontsize=6.5)
    save(fig, "fig4_per_participant")


# ---------------------------------------------------------------- Fig. 5 confusion matrices
def fig_cm():
    fig, axes = plt.subplots(1, 2, figsize=(COL1, 1.6))
    for ax, key, title in zip(axes, ["A_absolute|logistic_regression", "AR_absolute_plus_relative|logistic_regression"],
                              ["(a) A, LR", "(b) A+R, LR"]):
        cm = np.array(R["window"][key]["confusion_matrix"])
        rown = cm / cm.sum(axis=1, keepdims=True)
        ax.imshow(rown, cmap="Blues", vmin=0, vmax=1)
        for i in range(2):
            for j in range(2):
                ax.text(j, i, f"{cm[i, j]}\n({rown[i, j]:.2f})", ha="center", va="center", fontsize=6.5,
                        color="white" if rown[i, j] > 0.6 else "black")
        ax.set_xticks([0, 1], ["relax", "stress"])
        ax.set_yticks([0, 1], ["relax", "stress"])
        ax.set_xlabel("Predicted")
        ax.set_title(title)
    axes[0].set_ylabel("Actual")
    save(fig, "fig5_confusion")


# ---------------------------------------------------------------- Fig. 6 controls
def fig_controls():
    rec = R["record_wise"]
    fig, axes = plt.subplots(1, 2, figsize=(COL2, 2.0), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axes[0]
    keys = [("A_absolute", "logistic_regression"), ("A_absolute", "random_forest"), ("A_absolute", "svm"),
            ("AR_absolute_plus_relative", "logistic_regression"), ("AR_absolute_plus_relative", "random_forest"),
            ("AR_absolute_plus_relative", "svm"), ("T_time_only", "logistic_regression"), ("T_time_only", "random_forest")]
    labels = [f"{ {'A_absolute': 'A', 'AR_absolute_plus_relative': 'A+R', 'T_time_only': 'Time'}[f]}\n{MODEL_LABEL[m]}" for f, m in keys]
    pw = [rec[f"{f}|{m}"]["participant_wise_ba"] for f, m in keys]
    rw = [rec[f"{f}|{m}"]["balanced_accuracy"] for f, m in keys]
    x = np.arange(len(keys))
    ax.bar(x - 0.2, pw, 0.38, color="#4c6ef5", label="Participant-wise CV")
    ax.bar(x + 0.2, rw, 0.38, color="#c92a2a", label="Record-wise CV (leaky)")
    ax.axhline(0.5, color="k", lw=0.6, ls="--")
    ax.set_xticks(x, labels)
    ax.set_ylabel("Balanced accuracy")
    ax.set_ylim(0.4, 1.02)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("(a) Splitting strategy and time-only control")
    ax = axes[1]
    mt = R["temporal_controls"]["matched"]
    sets = ["A_absolute", "R_relative_only", "AR_absolute_plus_relative"]
    models = ["logistic_regression", "random_forest", "svm"]
    for j, fs in enumerate(sets):
        vals = [mt[f"{fs}|{m}"]["balanced_accuracy"] for m in models]
        lo = [mt[f"{fs}|{m}"]["balanced_accuracy"] - mt[f"{fs}|{m}"]["ba_ci95"][0] for m in models]
        hi = [mt[f"{fs}|{m}"]["ba_ci95"][1] - mt[f"{fs}|{m}"]["balanced_accuracy"] for m in models]
        ax.bar(np.arange(3) + (j - 1) * 0.25, vals, 0.23, yerr=[lo, hi], color=C[fs], capsize=1.5,
               error_kw={"lw": 0.6}, label=FS_LABEL[fs])
    ax.axhline(0.5, color="k", lw=0.6, ls="--")
    ax.set_xticks(range(3), [MODEL_LABEL[m] for m in models])
    ax.set_ylim(0.3, 0.85)
    ax.set_title(f"(b) Temporally matched windows (n={mt['n_participants']})")
    ax.legend(frameon=False, fontsize=6, loc="upper left")
    save(fig, "fig6_controls")


# ---------------------------------------------------------------- Fig. 7 permutation importance
def fig_importance():
    imp = R["permutation_importance"]
    feats = list(imp["logistic_regression"].keys())
    order = sorted(feats, key=lambda f: imp["logistic_regression"][f]["mean"])
    fig, ax = plt.subplots(figsize=(COL1, 2.3))
    y = np.arange(len(order))
    for k, (m, col) in enumerate((("logistic_regression", "#f08c00"), ("random_forest", "#4c6ef5"))):
        ax.barh(y + (k - 0.5) * 0.38, [imp[m][f]["mean"] for f in order], 0.36,
                xerr=[imp[m][f]["sd_over_folds"] for f in order], color=col, label=MODEL_LABEL[m],
                error_kw={"lw": 0.5}, capsize=1)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_yticks(y, order, fontsize=6.5)
    ax.set_xlabel("Drop in held-out balanced accuracy")
    ax.legend(frameon=False, loc="lower right")
    save(fig, "fig7_importance")


# ---------------------------------------------------------------- Fig. 8 accuracy by position
def fig_position():
    pos = pd.DataFrame(R["error_analysis"]["accuracy_by_position"])
    fig, ax = plt.subplots(figsize=(COL1, 1.7))
    for ph, col, lab in (("relax", "#0e9f8e", "relax: min before end of relax period"),
                         ("stress", "#e0662b", "stress: min after start of stress period")):
        d = pos[(pos.phase == ph) & (pos["size"] >= 20)]
        ax.plot(d["pos_bin"], d["mean"], marker="o", ms=3, color=col, lw=1, label=lab)
    ax.axhline(0.5, color="k", lw=0.6, ls="--")
    ax.set_xlabel("Distance from the relax/stress boundary (min)")
    ax.set_ylabel("Window accuracy")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False, fontsize=6, loc="lower right")
    save(fig, "fig8_position")


# ---------------------------------------------------------------- Fig. 9 segment level
def fig_segment():
    S = R["segment"]
    sets = ["A_absolute", "AR_absolute_plus_relative", "AR+EDA", "AR+ECG_HRV", "AR+EDA+ECG_HRV", "EDA+ECG_HRV_only"]
    lab = ["A", "A+R", "A+R\n+EDA", "A+R\n+HRV", "A+R+EDA\n+HRV", "EDA+HRV\nonly"]
    models = ["logistic_regression", "random_forest", "svm"]
    cols = ["#f08c00", "#4c6ef5", "#12b886"]
    fig, ax = plt.subplots(figsize=(COL2 * 0.62, 1.9))
    for k, m in enumerate(models):
        v = [S[f"{s}|{m}"]["balanced_accuracy"] for s in sets]
        lo = [S[f"{s}|{m}"]["balanced_accuracy"] - S[f"{s}|{m}"]["ba_ci95"][0] for s in sets]
        hi = [S[f"{s}|{m}"]["ba_ci95"][1] - S[f"{s}|{m}"]["balanced_accuracy"] for s in sets]
        ax.bar(np.arange(len(sets)) + (k - 1) * 0.26, v, 0.24, yerr=[lo, hi], color=cols[k], label=MODEL_LABEL[m],
               capsize=1.2, error_kw={"lw": 0.5})
    ax.axhline(0.5, color="k", lw=0.6, ls="--")
    ax.set_xticks(range(len(sets)), lab)
    ax.set_ylabel("Balanced accuracy")
    ax.set_ylim(0.3, 0.9)
    ax.legend(frameon=False, ncol=3, loc="upper left")
    save(fig, "fig9_segment")


# ---------------------------------------------------------------- Fig. 10 ECG detector check
def fig_ecg():
    d = pd.read_csv(RES / "ecg_detector_check.csv")
    d = d[(d.device_class == "NSR") & d.ecg_usable]
    mean = (d.device_hr + d.ecg_hr_derived) / 2
    diff = d.ecg_hr_derived - d.device_hr
    e = R["ecg_detector"]
    fig, ax = plt.subplots(figsize=(COL1, 1.6))
    ax.scatter(mean, diff, s=6, color="#4c6ef5")
    for v, ls in ((e["bias_bpm"], "-"), (e["loa_low"], "--"), (e["loa_high"], "--")):
        ax.axhline(v, color="k", lw=0.6, ls=ls)
    ax.set_xlabel("Mean of device and derived HR (bpm)")
    ax.set_ylabel("Derived $-$ device (bpm)")
    save(fig, "fig10_ecg_agreement")


# ---------------------------------------------------------------- Tables
def tex(name, body):
    (TAB / f"{name}.tex").write_text(body, encoding="utf-8")


def tables():
    D = R["dataset"]
    rows = []
    desc = {"participants.csv": "Demographics", "fitbit_heart_rate_per_second.csv": "Fitbit HR, irregular ($\\approx$2 s)",
            "fitbit_heart_rate_per_minute.csv": "Fitbit HR per minute", "fitbit_heart_rate_summary.csv": "Daily HR-zone minutes",
            "stai.csv": "STAI-S after each phase", "pss_14.csv": "PSS-14 (past month)", "eda.csv": "EDA per phase",
            "ecg.csv": "30-s ECG per phase (250 Hz)"}
    for f, v in D["files"].items():
        rows.append(f"\\texttt{{{f.replace('_', chr(92) + '_')}}} & {desc[f]} & {v['rows']:,} & {v['participants']} \\\\")
    tex("tab_dataset", "\\begin{tabular}{@{}llrr@{}}\n\\toprule\nFile & Content & Rows & IDs \\\\\n\\midrule\n" + "\n".join(rows)
        + "\n\\bottomrule\n\\end{tabular}\n")

    W = R["window"]
    lines = []
    for fs in ["A_absolute", "R_relative_only", "AR_absolute_plus_relative", "Zt_transductive_zscore", "T_time_only"]:
        for m in ["dummy", "logistic_regression", "random_forest", "svm"]:
            k = f"{fs}|{m}"
            if k not in W:
                continue
            d = W[k]
            lines.append(f"{FS_LABEL[fs]} & {MODEL_LABEL[m]} & {d['balanced_accuracy']:.3f} [{d['ba_ci95'][0]:.3f}, {d['ba_ci95'][1]:.3f}] & "
                         f"{d['macro_f1']:.3f} & {d['recall_relax']:.3f} & {d['recall_stress']:.3f} & {f3(d['roc_auc'])} \\\\")
        lines.append("\\midrule")
    lines = lines[:-1]
    tex("tab_window", "\\begin{tabular}{@{}llccccc@{}}\n\\toprule\nFeatures & Model & BA [95\\% CI] & Macro-F1 & Rec.$_\\mathrm{relax}$ & Rec.$_\\mathrm{stress}$ & AUC \\\\\n\\midrule\n"
        + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")

    comp = R["window_comparisons"]
    rep = R["repeated_cv"]
    wins = R["repeated_cv_wins"]
    lines = []
    for m in ["logistic_regression", "random_forest", "svm"]:
        for o, lab in (("R_relative_only", "R vs A"), ("AR_absolute_plus_relative", "A+R vs A")):
            c = comp[f"{o} vs A_absolute|{m}"]
            lines.append(f"{MODEL_LABEL[m]} & {lab} & {c['pooled_ba_diff']:+.3f} [{c['pooled_ba_diff_ci95'][0]:+.3f}, {c['pooled_ba_diff_ci95'][1]:+.3f}] & "
                         f"{c['mean_diff']:+.3f} & {c['n_better']}/{c['n_worse']}/{c['n_tied']} & {c['p']:.3f} & {c['p_holm']:.3f} & "
                         f"{rep[f'{o}|{m}']['mean']:.3f} vs {rep[f'A_absolute|{m}']['mean']:.3f} ({wins[m][o]}/10) \\\\")
    tex("tab_comparisons", "\\begin{tabular}{@{}llcccccc@{}}\n\\toprule\nModel & Comparison & $\\Delta$BA pooled [95\\% CI] & $\\Delta$BA$_\\mathrm{pp}$ & +/$-$/= & $p$ & $p_\\mathrm{Holm}$ & Repeated CV (wins) \\\\\n\\midrule\n"
        + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")

    S = R["segment"]
    lab = {"A_absolute": "A", "AR_absolute_plus_relative": "A+R", "AR+EDA": "A+R+EDA", "AR+ECG_HRV": "A+R+HRV",
           "AR+EDA+ECG_HRV": "A+R+EDA+HRV", "EDA+ECG_HRV_only": "EDA+HRV only"}
    lines = []
    for fs in lab:
        cells = []
        for m in ["logistic_regression", "random_forest", "svm"]:
            d = S[f"{fs}|{m}"]
            cells.append(f"{d['balanced_accuracy']:.3f} [{d['ba_ci95'][0]:.2f}, {d['ba_ci95'][1]:.2f}]")
        lines.append(f"{lab[fs]} & " + " & ".join(cells) + f" & {S[f'{fs}|logistic_regression']['n_missing_values_imputed']} \\\\")
    tex("tab_segment", "\\begin{tabular}{@{}lcccc@{}}\n\\toprule\nFeatures & LR & RF & SVM & Imputed \\\\\n\\midrule\n" + "\n".join(lines)
        + "\n\\bottomrule\n\\end{tabular}\n")

    reg = R["regression"]
    lines = []
    for tgt, tl in (("stai_state", "STAI-S"), ("pss14", "PSS-14")):
        for e in ("A", "B", "C"):
            cells = [f"{reg[f'{tgt}|{e}|{m}']['mae']:.2f} / {reg[f'{tgt}|{e}|{m}']['r2']:.2f}" for m in ("dummy", "ridge", "random_forest", "svr")]
            lines.append(f"{tl} & {e} & " + " & ".join(cells) + " \\\\")
    tex("tab_regression", "\\begin{tabular}{@{}llcccc@{}}\n\\toprule\nTarget & Set & Mean & Ridge & RF & SVR \\\\\n\\midrule\n" + "\n".join(lines)
        + "\n\\bottomrule\n\\end{tabular}\n")

    cal = R["calibration_length"]
    lines = []
    for L in (1, 2, 3):
        cells = [f"{cal[f'{L}min|{fs}|{m}']['balanced_accuracy']:.3f}" for fs in ("R_relative_only", "AR_absolute_plus_relative") for m in ("logistic_regression", "svm")]
        lines.append(f"{L} min & " + " & ".join(cells) + " \\\\")
    tex("tab_calibration", "\\begin{tabular}{@{}lcccc@{}}\n\\toprule\n& \\multicolumn{2}{c}{R only} & \\multicolumn{2}{c}{A+R} \\\\\nCalibration & LR & SVM & LR & SVM \\\\\n\\midrule\n"
        + "\n".join(lines) + "\n\\bottomrule\n\\end{tabular}\n")

    nt = R["nested_tuning"]["results"]
    lines = []
    for fs in ("A_absolute", "AR_absolute_plus_relative"):
        for m in ("logistic_regression", "random_forest", "svm"):
            d = nt[f"{fs}|{m}"]
            lines.append(f"{FS_LABEL[fs]} & {MODEL_LABEL[m]} & {d['fixed_hyperparameters_ba']:.3f} & {d['balanced_accuracy']:.3f} \\\\")
    tex("tab_nested", "\\begin{tabular}{@{}llcc@{}}\n\\toprule\nFeatures & Model & Fixed & Nested-tuned \\\\\n\\midrule\n" + "\n".join(lines)
        + "\n\\bottomrule\n\\end{tabular}\n")


if __name__ == "__main__":
    fig_workflow()
    fig_timeline()
    fig_window()
    fig_pp()
    fig_cm()
    fig_controls()
    fig_importance()
    fig_position()
    fig_segment()
    fig_ecg()
    tables()
    print("figures ->", FIG)
    print("tables  ->", TAB)
