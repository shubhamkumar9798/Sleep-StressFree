"""Reconstruction of relax/stress phases and derivation of analysis tables.

Why this module exists
----------------------
The Fitbit heart-rate files only contain (username, clock time, bpm). They do
not say which experimental phase a sample belongs to. The STAI questionnaire,
however, was answered once after the relax phase and once after the stress
phase, and both answers carry clock times recorded on the same day. We use
those questionnaire times as phase boundaries:

    HR start ──calibration──┬──── relax (evaluation) ────┤guard│STAI relax│guard├── stress (evaluation) ──┤guard│STAI stress
                            calibration_minutes          2 min             1 min                           2 min

* Calibration: the first `calibration_minutes` of each participant's HR
  recording. It is used ONLY to compute the personal baseline and is never
  evaluated by any experiment (so general and personalised models are scored on
  exactly the same windows).
* Guard bands drop the minutes in which the questionnaire was most likely being
  filled in and the transition between phases.

All parameters are in config.PreprocessingConfig and are reported by the API.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .. import config
from . import loader

_lock = threading.Lock()
_cache: dict[str, "Prepared"] = {}

HR_STAT_FEATURES = ["hr_mean", "hr_median", "hr_std", "hr_min", "hr_max", "hr_iqr", "hr_slope"]
PERSONAL_FEATURES = ["hr_mean_delta", "hr_median_delta", "hr_mean_ratio", "hr_mean_z", "hr_std_ratio"]
MULTIMODAL_FEATURES = ["eda_scl_mean", "eda_scl_std", "eda_activation_frac", "ecg_device_hr"]
MIN_BASELINE_SD = 1.0  # bpm; prevents division by ~0 for very flat calibration periods

# Positively worded items (reverse-scored). Identified from the item wording in the files.
STAI_POSITIVE_ITEMS = [1, 6, 8, 12, 13, 14, 15, 18, 19, 20]
PSS_POSITIVE_ITEMS = [1, 5, 6, 8, 9, 10, 11]


def clear_cache() -> None:
    with _lock:
        _cache.clear()


# ---------------------------------------------------------------------------
# Feature helpers (shared with the prediction endpoint so training and
# inference compute features identically)
# ---------------------------------------------------------------------------
def hr_features(values: np.ndarray, seconds: np.ndarray | None = None) -> dict[str, float]:
    """Summary statistics of a heart-rate sequence.

    hr_slope is the least-squares slope in bpm per minute (needs >= 3 samples).
    """
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    n = len(v)
    out = {k: np.nan for k in HR_STAT_FEATURES}
    out["n_samples"] = float(n)
    if n == 0:
        return out
    out["hr_mean"] = float(np.mean(v))
    out["hr_median"] = float(np.median(v))
    out["hr_min"] = float(np.min(v))
    out["hr_max"] = float(np.max(v))
    out["hr_iqr"] = float(np.percentile(v, 75) - np.percentile(v, 25))
    out["hr_std"] = float(np.std(v, ddof=1)) if n >= 2 else np.nan
    if n >= 3 and seconds is not None:
        t = np.asarray(seconds, dtype=float)
        if len(t) == n and np.ptp(t) > 0:
            out["hr_slope"] = float(np.polyfit(t / 60.0, v, 1)[0])
    return out


def baseline_stats(values: np.ndarray) -> dict[str, float]:
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if len(v) == 0:
        return {"base_mean": np.nan, "base_median": np.nan, "base_sd": np.nan, "base_n": 0}
    return {
        "base_mean": float(np.mean(v)),
        "base_median": float(np.median(v)),
        "base_sd": float(np.std(v, ddof=1)) if len(v) > 1 else np.nan,
        "base_n": int(len(v)),
    }


def personal_features(feats: dict[str, float], base: dict[str, float]) -> dict[str, float]:
    """Deviation of a window/segment from the participant's calibration baseline."""
    bm, bmed, bsd = base["base_mean"], base["base_median"], base["base_sd"]
    sd = max(bsd, MIN_BASELINE_SD) if not np.isnan(bsd) else np.nan
    return {
        "hr_mean_delta": feats["hr_mean"] - bmed,
        "hr_median_delta": feats["hr_median"] - bmed,
        "hr_mean_ratio": feats["hr_mean"] / bmed if bmed else np.nan,
        "hr_mean_z": (feats["hr_mean"] - bm) / sd if sd == sd else np.nan,
        "hr_std_ratio": feats["hr_std"] / sd if sd == sd else np.nan,
    }


# ---------------------------------------------------------------------------
@dataclass
class Prepared:
    fingerprint: str
    sessions: pd.DataFrame
    windows: pd.DataFrame
    segments: pd.DataFrame
    participants: pd.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)
    hr: pd.DataFrame | None = None


def _score_check(df: pd.DataFrame, first_item_col: int, positive: list[int], offset: int, n_items: int) -> dict:
    items = df.columns[first_item_col : first_item_col + n_items]
    if len(items) != n_items:
        return {"verified": False, "reason": f"expected {n_items} item columns, found {len(items)}"}
    codes = pd.DataFrame({c: pd.to_numeric(df[c].astype(str).str.extract(r"^\s*(\d)")[0], errors="coerce") for c in items})
    if codes.isna().any().any():
        return {"verified": False, "reason": "some item answers have no numeric code"}
    total = pd.Series(0.0, index=df.index)
    # STAI items are coded 0..3 and scored 1..4 (offset 1); PSS items are coded and scored 0..4 (offset 0).
    # Positively worded items are reverse-scored, which is 4 - code in both scales.
    for i, c in enumerate(items, start=1):
        total += (4 - codes[c]) if i in positive else codes[c] + offset
    agree = (total.round() == pd.to_numeric(df["score"], errors="coerce")).mean()
    return {"verified": bool(agree == 1.0), "agreement": float(agree), "n": int(len(df))}


def build(force: bool = False) -> Prepared:
    fp = loader.fingerprint()
    with _lock:
        if not force and fp in _cache:
            return _cache[fp]
    prepared = _build(fp)
    with _lock:
        _cache.clear()
        _cache[fp] = prepared
    return prepared


def _build(fp: str) -> Prepared:
    pp = config.settings.preprocessing
    hr_raw = loader.load("fitbit_heart_rate_per_second.csv").copy()
    stai = loader.load("stai.csv").copy()

    summary: dict[str, Any] = {"config": pp.__dict__.copy(), "warnings": []}

    # ---- heart rate cleaning -------------------------------------------------
    hr_raw["t"] = loader.parse_clock(hr_raw["time"])
    hr_raw["value"] = pd.to_numeric(hr_raw["value"], errors="coerce")
    n0 = len(hr_raw)
    bad_time = hr_raw["t"].isna()
    bad_val = hr_raw["value"].isna() | (hr_raw["value"] < pp.hr_valid_min) | (hr_raw["value"] > pp.hr_valid_max)
    hr = hr_raw[~bad_time & ~bad_val]
    n_dup = int(hr.duplicated(["username", "t"]).sum())
    hr = hr.drop_duplicates(["username", "t"], keep="first").sort_values(["username", "t"]).reset_index(drop=True)
    summary["hr_samples"] = {
        "raw": n0,
        "invalid_time": int(bad_time.sum()),
        "invalid_or_out_of_range_value": int((bad_val & ~bad_time).sum()),
        "duplicates_dropped": n_dup,
        "clean": int(len(hr)),
    }

    # ---- questionnaire timing ---------------------------------------------
    stai["t"] = loader.parse_clock(stai["time"])
    stai = stai.drop_duplicates(["username", "phase"], keep="first")
    stai_t = stai.pivot(index="username", columns="phase", values="t")
    stai_score = stai.pivot(index="username", columns="phase", values="score")

    # Optional modalities (Experiment C) ------------------------------------
    eda_phase = pd.DataFrame(columns=["username", "phase"] + MULTIMODAL_FEATURES[:3])
    try:
        eda = loader.load("eda.csv")
        e = eda[(eda["valid_data"].astype(bool)) & (pd.to_numeric(eda["time_sec"], errors="coerce") >= 0)]
        eda_phase = (
            e.groupby(["username", "phase"])
            .agg(eda_scl_mean=("scl_avg", "mean"), eda_scl_std=("scl_avg", "std"), eda_activation_frac=("activation", "mean"), eda_n=("scl_avg", "size"))
            .reset_index()
        )
        summary["eda_rows_used"] = int(len(e))
    except loader.DatasetError as exc:
        summary["warnings"].append(f"EDA unavailable: {exc.message}")
    ecg_phase = pd.DataFrame(columns=["username", "phase", "ecg_device_hr", "ecg_t"])
    try:
        ecg = loader.load("ecg.csv").copy()
        ecg = ecg.drop_duplicates(["username", "phase"], keep="first")
        ecg["ecg_device_hr"] = pd.to_numeric(ecg["heart_rate"], errors="coerce").where(ecg["result_classification"] == "NSR")
        ecg["ecg_t"] = loader.parse_clock(ecg["reading_time"])
        ecg_phase = ecg[["username", "phase", "ecg_device_hr", "ecg_t"]]
    except loader.DatasetError as exc:
        summary["warnings"].append(f"ECG unavailable: {exc.message}")

    # ---- per participant sessions -------------------------------------------
    cal = pp.calibration_minutes * 60
    g_before = pp.guard_before_questionnaire_minutes * 60
    g_after = pp.guard_after_relax_questionnaire_minutes * 60
    min_phase = pp.min_phase_minutes * 60
    seg_len = pp.segment_minutes * 60

    session_rows, window_rows, segment_rows = [], [], []
    hr_groups = {u: g for u, g in hr.groupby("username")}
    usernames = sorted(set(stai["username"]) | set(hr_groups))
    for u in usernames:
        reasons: list[str] = []
        g = hr_groups.get(u)
        tr = stai_t.loc[u, "relax"] if u in stai_t.index and "relax" in stai_t.columns else np.nan
        ts = stai_t.loc[u, "stress"] if u in stai_t.index and "stress" in stai_t.columns else np.nan
        row: dict[str, Any] = {"username": u, "stai_relax_t": tr, "stai_stress_t": ts}
        if g is None or len(g) == 0:
            reasons.append("no valid heart-rate samples")
        if np.isnan(tr) or np.isnan(ts):
            reasons.append("STAI relax/stress timestamp missing")
        elif ts <= tr:
            reasons.append("stress questionnaire is not after relax questionnaire (phase order cannot be reconstructed)")
        if g is not None and len(g):
            t, v = g["t"].to_numpy(), g["value"].to_numpy(dtype=float)
            hr_start, hr_end = float(t.min()), float(t.max())
            row.update(hr_start=hr_start, hr_end=hr_end, n_hr_samples=int(len(g)))
            if not reasons:
                calib_end = hr_start + cal
                relax_eval = (calib_end, tr - g_before)
                stress_eval = (tr + g_after, ts - g_before)
                cmask = (t >= hr_start) & (t < calib_end)
                base = baseline_stats(v[cmask])
                row.update(base, calib_start=hr_start, calib_end=calib_end,
                           relax_eval_start=relax_eval[0], relax_eval_end=relax_eval[1],
                           stress_eval_start=stress_eval[0], stress_eval_end=stress_eval[1])
                if calib_end > tr - g_before:
                    reasons.append("heart-rate recording starts too close to the relax questionnaire for a calibration period")
                if base["base_n"] < pp.min_calibration_samples:
                    reasons.append(f"calibration has {base['base_n']} samples (< {pp.min_calibration_samples})")
                if hr_end < stress_eval[1] - 60:
                    reasons.append("heart-rate recording ends before the end of the stress phase")
                for phase, (a, b) in (("relax", relax_eval), ("stress", stress_eval)):
                    if b - a < min_phase:
                        reasons.append(f"{phase} evaluation period shorter than {pp.min_phase_minutes} min")
                        continue
                    # windows
                    n_win = int((b - a) // pp.window_seconds)
                    n_valid = 0
                    for k in range(n_win):
                        ws = a + k * pp.window_seconds
                        m = (t >= ws) & (t < ws + pp.window_seconds)
                        if m.sum() < pp.min_samples_per_window:
                            continue
                        f = hr_features(v[m], t[m] - ws)
                        f.update(personal_features(f, base))
                        f.update(username=u, phase=phase, label=int(phase == "stress"), window_start=ws,
                                 minutes_from_hr_start=(ws - hr_start) / 60.0)
                        window_rows.append(f)
                        n_valid += 1
                    row[f"{phase}_windows"] = n_valid
                    if n_valid < 2:
                        reasons.append(f"fewer than 2 valid {phase} windows")
                    # segment = last `segment_minutes` of the evaluation period
                    sa = max(a, b - seg_len)
                    m = (t >= sa) & (t < b)
                    if m.sum() < pp.min_samples_per_window * max(1, (b - sa) / 60):
                        reasons.append(f"{phase} segment has too few samples")
                        continue
                    f = hr_features(v[m], t[m] - sa)
                    f.update(personal_features(f, base))
                    f.update(username=u, phase=phase, label=int(phase == "stress"), segment_start=sa, segment_end=b,
                             segment_minutes=(b - sa) / 60.0,
                             stai_score=float(stai_score.loc[u, phase]) if u in stai_score.index else np.nan)
                    segment_rows.append(f)
        # ECG clock consistency flag (informational only; ECG times are NOT used for windows)
        ecg_u = ecg_phase[ecg_phase["username"] == u].set_index("phase")["ecg_t"] if len(ecg_phase) else pd.Series(dtype=float)
        if not reasons and "relax" in ecg_u and "stress" in ecg_u:
            row["ecg_clock_consistent"] = bool(row["hr_start"] <= ecg_u["relax"] <= tr and tr < ecg_u["stress"] <= ts)
        row["eligible"] = not reasons
        row["exclusion_reasons"] = reasons
        session_rows.append(row)

    sessions = pd.DataFrame(session_rows)
    eligible = set(sessions.loc[sessions["eligible"], "username"]) if len(sessions) else set()
    windows = pd.DataFrame(window_rows)
    segments = pd.DataFrame(segment_rows)
    if len(windows):
        windows = windows[windows["username"].isin(eligible)].reset_index(drop=True)
    if len(segments):
        segments = segments[segments["username"].isin(eligible)].reset_index(drop=True)
        segments = segments.merge(eda_phase, on=["username", "phase"], how="left")
        segments = segments.merge(ecg_phase[["username", "phase", "ecg_device_hr"]], on=["username", "phase"], how="left")

    # ---- participant-level table (PSS-14) ----------------------------------
    participants = pd.DataFrame()
    try:
        pss = loader.load("pss_14.csv").drop_duplicates("username")
        if len(segments):
            wide = segments.pivot(index="username", columns="phase")
            part = pd.DataFrame(index=wide.index)
            for f in HR_STAT_FEATURES:
                part[f"rest_{f}"] = wide[(f, "relax")]
            for f in ["hr_mean_delta", "hr_mean_ratio", "hr_mean_z"]:
                part[f"rest_{f}"] = wide[(f, "relax")]
                part[f"stress_{f}"] = wide[(f, "stress")]
            part["reactivity_hr_mean"] = wide[("hr_mean", "stress")] - wide[("hr_mean", "relax")]
            for f in MULTIMODAL_FEATURES:
                if (f, "relax") in wide.columns:
                    part[f"rest_{f}"] = wide[(f, "relax")]
                    part[f"stress_{f}"] = wide[(f, "stress")]
            part = part.reset_index().merge(pss[["username", "score"]].rename(columns={"score": "pss_score"}), on="username", how="inner")
            participants = part
        summary["pss_scoring_check"] = _score_check(pss, 3, PSS_POSITIVE_ITEMS, 0, 14)
    except loader.DatasetError as exc:
        summary["warnings"].append(f"PSS-14 unavailable: {exc.message}")
    summary["stai_scoring_check"] = _score_check(stai, 4, STAI_POSITIVE_ITEMS, 1, 20)

    # ---- summary ----------------------------------------------------------
    excluded = sessions[~sessions["eligible"]] if len(sessions) else sessions
    summary.update(
        participants_total=int(len(sessions)),
        participants_eligible=int(len(eligible)),
        exclusions=[{"username": r.username, "reasons": r.exclusion_reasons} for r in excluded.itertuples()],
        windows_per_phase=windows["phase"].value_counts().to_dict() if len(windows) else {},
        segments=int(len(segments)),
        participant_level_rows=int(len(participants)),
        ecg_clock_inconsistent=int((sessions.get("ecg_clock_consistent") == False).sum()) if len(sessions) else 0,  # noqa: E712
    )
    if summary["ecg_clock_inconsistent"]:
        summary["warnings"].append(
            f"{summary['ecg_clock_inconsistent']} eligible participants have ECG reading times outside the phase reconstructed "
            "from questionnaire times (most are offset by ~54 min, suggesting a device clock offset). ECG times are therefore not used for alignment."
        )
    if len(segments):
        paired = segments.pivot(index="username", columns="phase", values="stai_score").dropna()
        diff = paired["stress"] - paired["relax"]
        summary["manipulation_check"] = {
            "description": "STAI-state score after stress minus after relax (eligible participants)",
            "n": int(len(diff)),
            "mean_difference": float(diff.mean()),
            "sd_difference": float(diff.std(ddof=1)),
            "n_higher_after_stress": int((diff > 0).sum()),
            "n_equal": int((diff == 0).sum()),
            "n_lower_after_stress": int((diff < 0).sum()),
        }
    return Prepared(fp, sessions, windows, segments, participants, summary, hr)
