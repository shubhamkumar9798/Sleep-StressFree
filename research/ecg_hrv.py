"""Ultra-short HRV from the QoL_Stress 30-s ECG recordings (250 Hz, Fitbit Charge 6).

R-peaks are detected with a simplified Pan-Tompkins pipeline [Pan & Tompkins 1985]:
5-15 Hz band-pass -> derivative -> squaring -> 150-ms moving-window integration
-> peak picking with a 300-ms refractory period, then each peak is refined to
the maximum absolute band-passed amplitude within +/-60 ms.

RR intervals outside 300-2000 ms, or differing by more than 30 % from the
median RR, are rejected. A recording is considered usable when at least 15 valid
RR intervals remain. Derived mean HR is compared with the device-reported HR as
a check of the detector.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks

FS = 250.0
MIN_RR = 15


def r_peaks(x: np.ndarray, fs: float = FS) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x - np.median(x)
    b, a = butter(2, [5 / (fs / 2), 15 / (fs / 2)], btype="band")
    bp = filtfilt(b, a, x)
    d = np.gradient(bp)
    sq = d ** 2
    win = int(0.150 * fs)
    mwi = np.convolve(sq, np.ones(win) / win, mode="same")
    thr = 0.3 * np.percentile(mwi, 99)
    peaks, _ = find_peaks(mwi, height=thr, distance=int(0.30 * fs))
    half = int(0.060 * fs)
    refined = []
    for p in peaks:
        lo, hi = max(0, p - half), min(len(bp), p + half)
        refined.append(lo + int(np.argmax(np.abs(bp[lo:hi]))))
    return np.unique(np.array(refined, dtype=int))


def hrv(x: np.ndarray, fs: float = FS) -> dict:
    pk = r_peaks(x, fs)
    rr = np.diff(pk) / fs * 1000.0
    rr = rr[(rr >= 300) & (rr <= 2000)]
    if len(rr) >= 3:
        rr = rr[np.abs(rr - np.median(rr)) <= 0.3 * np.median(rr)]
    out = {"ecg_n_rr": int(len(rr)), "ecg_usable": bool(len(rr) >= MIN_RR)}
    if out["ecg_usable"]:
        out["ecg_hr_derived"] = float(60000.0 / rr.mean())
        out["ecg_sdnn"] = float(np.std(rr, ddof=1))
        out["ecg_rmssd"] = float(np.sqrt(np.mean(np.diff(rr) ** 2)))
    else:
        out.update(ecg_hr_derived=np.nan, ecg_sdnn=np.nan, ecg_rmssd=np.nan)
    return out


def hrv_table(ecg: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in ecg.drop_duplicates(["username", "phase"]).itertuples():
        # A few recordings contain non-numeric tokens (e.g. a lone '-'). They are treated as
        # missing samples and bridged by linear interpolation of the 4-ms gap; the count is reported.
        s = pd.to_numeric(pd.Series(str(r.waveform_samples).split()), errors="coerce")
        n_bad = int(s.isna().sum())
        x = s.interpolate(limit_direction="both").to_numpy()
        rows.append({"username": r.username, "phase": r.phase, "device_hr": r.heart_rate,
                     "device_class": r.result_classification, "ecg_n_samples": int(len(s)),
                     "ecg_n_invalid_samples": n_bad, **hrv(x)})
    return pd.DataFrame(rows)
