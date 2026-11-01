"""Screenshot text extraction with Tesseract OCR.

Only text that Tesseract actually reads from the image is turned into candidate
values. Charts/graphs are never interpreted. Every candidate must be reviewed
and confirmed by the user before it is stored, and uncertain candidates are
flagged.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .. import config, db
from . import records as rec

MAX_BYTES = 10 * 1024 * 1024
LOW_CONFIDENCE = 70.0
WINDOWS_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

INSTALL_HELP = (
    "Tesseract OCR is not installed or not found. On Windows install it from "
    "https://github.com/UB-Mannheim/tesseract/wiki (default path C:\\Program Files\\Tesseract-OCR), "
    "or set TESSERACT_CMD in backend/.env to the full path of tesseract.exe. "
    "Manual entry and CSV import keep working without OCR."
)


class OcrUnavailable(Exception):
    pass


def _configure():
    try:
        import pytesseract  # noqa: F401
    except ImportError as exc:
        raise OcrUnavailable("The pytesseract Python package is not installed. " + INSTALL_HELP) from exc
    import pytesseract

    cmd = config.settings.tesseract_cmd
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    elif not shutil.which("tesseract") and WINDOWS_DEFAULT.exists():
        pytesseract.pytesseract.tesseract_cmd = str(WINDOWS_DEFAULT)
    return pytesseract


def status() -> dict:
    try:
        pt = _configure()
        version = str(pt.get_tesseract_version())
        return {"available": True, "version": version}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "message": str(exc) if isinstance(exc, OcrUnavailable) else INSTALL_HELP}


def _pending_dir() -> Path:
    d = config.settings.upload_dir / "pending"
    d.mkdir(parents=True, exist_ok=True)
    return d


def validate_image(raw: bytes, filename: str) -> str:
    if not raw:
        raise rec.RecordError("The uploaded file is empty.")
    if len(raw) > MAX_BYTES:
        raise rec.RecordError("Image too large (max 10 MB).", 413)
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(raw)) as im:
            fmt = (im.format or "").upper()
            im.verify()
    except (UnidentifiedImageError, OSError):
        raise rec.RecordError("The file is not a readable image.", 415)
    if fmt not in ("PNG", "JPEG"):
        raise rec.RecordError(f"Unsupported image format '{fmt}'. Upload a PNG or JPG/JPEG screenshot.", 415)
    with Image.open(io.BytesIO(raw)) as im:
        if min(im.size) < 100:
            raise rec.RecordError("The image is too small to read reliably (min 100 px).", 422)
    return "png" if fmt == "PNG" else "jpg"


def preprocess(raw: bytes):
    """Greyscale, invert dark-theme screenshots, upscale small images, Otsu threshold."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise rec.RecordError("OpenCV could not decode the image.", 415)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if gray.mean() < 110:  # dark background (e.g. Zepp dark mode) -> dark text on light background
        gray = cv2.bitwise_not(gray)
    if gray.shape[1] < 1200:
        f = 1200 / gray.shape[1]
        gray = cv2.resize(gray, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return th


def ocr_lines(image) -> list[dict]:
    pt = _configure()
    try:
        data = pt.image_to_data(image, config="--psm 11", output_type=pt.Output.DICT)
    except Exception as exc:  # TesseractNotFoundError and friends
        raise OcrUnavailable(INSTALL_HELP) from exc
    lines: dict[tuple, dict] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        ln = lines.setdefault(key, {"words": [], "confs": [], "top": data["top"][i]})
        ln["words"].append(word)
        ln["confs"].append(conf)
    out = [
        {"text": " ".join(v["words"]), "confidence": round(sum(v["confs"]) / len(v["confs"]), 1), "top": v["top"]}
        for v in lines.values()
    ]
    return sorted(out, key=lambda x: x["top"])


# --------------------------------------------------------------------------
# Candidate extraction (pure text -> candidates, unit-tested without images)
# --------------------------------------------------------------------------
RULES: list[tuple[str, str, str | None]] = [
    # (metric, regex on a line, required context keyword in this/previous line or None)
    ("heart_rate", r"\b(\d{2,3})\s*bpm\b", None),
    ("steps", r"\b(\d{1,3}(?:[,.]\d{3})+|\d{1,6})\s*steps?\b", None),
    ("sleep_duration", r"\b(\d{1,2})\s*h(?:rs?|ours?)?\s*(\d{1,2})\s*m(?:in(?:utes?)?)?\b", None),
    ("spo2", r"\b(\d{2,3})\s*%", r"spo2|sp02|oxygen"),
    ("hrv", r"\b(\d{1,3})\s*ms\b", r"hrv|variability"),
    ("device_stress_score", r"^\D*(\d{1,3})\D*$", r"stress"),
    ("steps", r"^\s*(\d{1,3}(?:[,.]\d{3})+|\d{2,6})\s*$", r"steps?"),
    ("heart_rate", r"^\s*(\d{2,3})\s*$", r"heart\s*rate|\bhr\b|pulse"),
]
DATE_PATTERNS = [
    r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b",
    r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b",
    r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\b",
]
TIME_PATTERN = r"\b([01]?\d|2[0-3]):([0-5]\d)\s*(am|pm)?\b"


def extract_candidates(lines: list[dict]) -> dict[str, Any]:
    candidates: list[dict] = []
    for idx, ln in enumerate(lines):
        text = ln["text"]
        low = text.lower()
        context = low + " " + (lines[idx - 1]["text"].lower() if idx > 0 else "")
        for metric, pattern, ctx in RULES:
            if ctx and not re.search(ctx, context):
                continue
            m = re.search(pattern, low)
            if not m:
                continue
            flags: list[str] = []
            if metric == "sleep_duration":
                value = int(m.group(1)) * 60 + int(m.group(2))
                if "sleep" not in context:
                    flags.append("no 'sleep' label nearby - confirm this duration is sleep")
            else:
                digits = re.sub(r"[,.]", "", m.group(1))
                value = float(digits)
            if ctx is not None and metric in ("heart_rate", "steps"):
                flags.append("unit not visible next to the number; identified from a nearby label")
            if metric == "heart_rate" and "resting" in context:
                metric = "resting_heart_rate"
            if metric == "device_stress_score":
                flags.append("manufacturer stress score - not a self-reported stress level")
            if ln["confidence"] < LOW_CONFIDENCE:
                flags.append(f"low OCR confidence ({ln['confidence']:.0f}%)")
            spec = rec.METRICS[metric]
            if not (spec["min"] <= value <= spec["max"]):
                flags.append(f"outside plausible range {spec['min']}-{spec['max']} {spec['unit']}")
            candidates.append({
                "id": uuid.uuid4().hex[:8], "metric": metric, "value": value, "unit": spec["unit"],
                "source_text": text, "ocr_confidence": ln["confidence"], "flags": flags,
            })
            break  # one candidate per line
    # Same metric found with different values -> ambiguous
    by_metric: dict[str, set] = {}
    for c in candidates:
        by_metric.setdefault(c["metric"], set()).add(c["value"])
    for c in candidates:
        if len(by_metric[c["metric"]]) > 1:
            c["flags"].append("several different values found for this measurement (e.g. min/max/average) - keep only the right one")
    dates, times = [], []
    for ln in lines:
        low = ln["text"].lower()
        for p in DATE_PATTERNS:
            for m in re.finditer(p, low):
                dates.append(m.group(0))
        for m in re.finditer(TIME_PATTERN, low):
            times.append(m.group(0))
    return {"candidates": candidates, "dates_seen": sorted(set(dates)), "times_seen": sorted(set(times))}


def extract(raw: bytes, filename: str) -> dict:
    ext = validate_image(raw, filename)
    st = status()
    if not st["available"]:
        raise OcrUnavailable(st["message"])
    image = preprocess(raw)
    lines = ocr_lines(image)
    parsed = extract_candidates(lines)
    token = uuid.uuid4().hex
    sha = hashlib.sha256(raw).hexdigest()
    (_pending_dir() / f"{token}.{ext}").write_bytes(raw)
    meta = {"filename": filename, "sha256": sha, "ext": ext, "candidates": parsed["candidates"]}
    (_pending_dir() / f"{token}.ocr.json").write_text(json.dumps(meta))
    warnings = []
    if not lines:
        warnings.append("No readable text was found. The screenshot may be blurred, too small, or contain only a chart.")
    elif not parsed["candidates"]:
        warnings.append("Text was read but no measurement with a recognisable label/unit was found. Enter values manually if they are visible.")
    if not parsed["dates_seen"]:
        warnings.append("No date was recognised in the screenshot. You must enter the measurement date/time yourself.")
    return {
        "token": token,
        "filename": filename,
        "sha256": sha,
        "ocr_text": "\n".join(f"{l['text']}  [{l['confidence']:.0f}%]" for l in lines),
        "lines": lines,
        **parsed,
        "warnings": warnings,
        "note": "Values are read only from visible text. Charts and graphs are not interpreted. Check every value against the screenshot.",
        "store_screenshots": config.settings.store_screenshots,
    }


def commit(token: str, payload: dict) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise rec.RecordError("Invalid upload token.", 400)
    meta_p = _pending_dir() / f"{token}.ocr.json"
    if not meta_p.exists():
        raise rec.RecordError("This screenshot upload has expired or was discarded.", 404)
    meta = json.loads(meta_p.read_text())
    if not payload.get("confirmed"):
        raise rec.RecordError("Please confirm that you checked the values against the screenshot.")
    recorded_at = rec.normalise_timestamp(payload.get("recorded_at"))
    participant = rec.clean_code(payload.get("participant_code"))
    device_label = (payload.get("device_label") or "").strip() or None
    items = payload.get("records") or []
    if not items:
        raise rec.RecordError("No values selected to save.")
    ocr_values = {c["id"]: c for c in meta["candidates"]}
    clean, errors = [], []
    for it in items:
        try:
            v = rec.validate_value(it.get("metric"), it.get("value"))
        except rec.RecordError as exc:
            errors.append(exc.message)
            continue
        orig = ocr_values.get(it.get("candidate_id"))
        edited = orig is None or orig["metric"] != it.get("metric") or float(orig["value"]) != v
        clean.append({
            "metric": it["metric"], "value": v, "recorded_at": recorded_at, "participant_code": participant,
            "device_label": device_label, "raw_value_text": orig["source_text"] if orig else "(added manually during review)",
            "value_was_edited": edited, "flags": (orig or {}).get("flags", []), "notes": payload.get("notes"),
        })
    if errors:
        raise rec.RecordError("Some values are invalid.", details=errors)
    src = _pending_dir() / f"{token}.{meta['ext']}"
    stored = None
    if config.settings.store_screenshots and src.exists():
        dest_dir = config.settings.upload_dir / "screenshots"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{meta['sha256'][:16]}.{meta['ext']}"
        shutil.copyfile(src, dest)
        stored = str(dest.name)
    with db.connect() as conn:
        batch = rec.create_batch(conn, "screenshot", meta["filename"], meta["sha256"], device_label, stored,
                                 details={"n_candidates": len(meta["candidates"])})
        ids = [rec.insert_record(conn, batch, "screenshot", c) for c in clean]
        rec.update_batch_count(conn, batch)
    discard(token)
    return {"batch_id": batch, "record_ids": ids, "screenshot_stored": stored is not None}


def discard(token: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise rec.RecordError("Invalid upload token.", 400)
    for p in _pending_dir().glob(f"{token}.*"):
        p.unlink(missing_ok=True)
