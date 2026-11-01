import io

import pytest

from app.imports import ocr


def test_manual_entry_validation(client):
    ok = client.post("/api/records/manual", json={
        "participant_code": "P001", "recorded_at": "2026-10-30T10:15", "device_label": "Amazfit (model unconfirmed)",
        "measurements": {"heart_rate": 72, "self_reported_stress": 3, "sleep_duration": None},
    })
    assert ok.status_code == 201, ok.text
    assert ok.json()["n_records"] == 2  # missing sleep is skipped, not stored as 0
    rows = client.get("/api/records?participant_code=P001").json()["rows"]
    assert {r["metric"] for r in rows} == {"heart_rate", "self_reported_stress"}
    assert all(r["source"] == "manual" and r["verified_device_measurement"] == 0 for r in rows)

    dup = client.post("/api/records/manual", json={"participant_code": "P001", "recorded_at": "2026-10-30T10:15", "measurements": {"heart_rate": 72}})
    assert dup.status_code == 409
    bad = client.post("/api/records/manual", json={"recorded_at": "2026-10-30T10:15", "measurements": {"heart_rate": 500}})
    assert bad.status_code == 422
    empty = client.post("/api/records/manual", json={"recorded_at": "2026-10-30T10:15", "measurements": {}})
    assert empty.status_code == 422
    badts = client.post("/api/records/manual", json={"recorded_at": "yesterday", "measurements": {"heart_rate": 70}})
    assert badts.status_code == 422
    stress = client.post("/api/records/manual", json={"recorded_at": "2026-10-30T11:00", "measurements": {"self_reported_stress": 2.5}})
    assert stress.status_code == 422
    email = client.post("/api/records/manual", json={"participant_code": "me@x.com", "recorded_at": "2026-10-30T11:00", "measurements": {"heart_rate": 70}})
    assert email.status_code == 422


CSV = b"""timestamp,bpm,steps,stress_level,participant_id
2026-10-01 08:00:00,71,120,3,S01
2026-10-01 08:05:00,,300,2,S01
not a date,75,10,1,S01
2026-10-01 08:10:00,999,50,1,S01
2026-10-01 08:10:00,999,50,1,S01
"""


def test_csv_import_flow(client):
    pv = client.post("/api/imports/csv/preview", files={"file": ("watch.csv", io.BytesIO(CSV), "text/csv")})
    assert pv.status_code == 200, pv.text
    body = pv.json()
    m = body["suggested_mapping"]
    assert m["timestamp_column"] == "timestamp" and m["participant_column"] == "participant_id"
    assert m["metrics"] == {"bpm": "heart_rate", "steps": "steps"}
    assert any("stress_level" in w for w in body["warnings"])  # never auto-mapped
    mapping = {**m, "device_label": "test export"}
    rep = client.post("/api/imports/csv/validate", json={"token": body["token"], "mapping": mapping}).json()
    assert rep["invalid_timestamps"] == 1
    assert rep["metrics"]["bpm"]["n_missing"] == 1
    assert rep["metrics"]["bpm"]["n_out_of_range"] == 2
    assert rep["duplicate_rows_in_file"] == 1
    n = rep["n_records_to_import"]
    assert n == 4  # bpm 71 + steps 120, 300, 50 (the duplicate row collapses)
    done = client.post("/api/imports/csv/commit", json={"token": body["token"], "mapping": mapping}).json()
    assert done["imported"] == n
    rows = client.get("/api/records?source=csv").json()["rows"]
    assert not any(r["metric"] in ("self_reported_stress", "device_stress_score") for r in rows)

    pv2 = client.post("/api/imports/csv/preview", files={"file": ("watch.csv", io.BytesIO(CSV), "text/csv")}).json()
    rep2 = client.post("/api/imports/csv/validate", json={"token": pv2["token"], "mapping": mapping}).json()
    assert rep2["duplicates_already_in_database"] == n and rep2["n_records_to_import"] == 0


def test_csv_rejects_bad_files(client):
    r = client.post("/api/imports/csv/preview", files={"file": ("x.xlsx", io.BytesIO(b"abc"), "application/octet-stream")})
    assert r.status_code == 415
    r = client.delete("/api/imports/csv/..%2F..%2Fsecret")
    assert r.status_code in (400, 404)


def test_ocr_candidate_rules():
    lines = [
        {"text": "Heart rate", "confidence": 95},
        {"text": "72 bpm", "confidence": 93},
        {"text": "8,421 steps", "confidence": 88},
        {"text": "Sleep", "confidence": 90},
        {"text": "7h 32min", "confidence": 60},
        {"text": "Stress", "confidence": 91},
        {"text": "38", "confidence": 90},
        {"text": "Oct 28 10:42", "confidence": 90},
    ]
    res = ocr.extract_candidates(lines)
    got = {c["metric"]: c for c in res["candidates"]}
    assert got["heart_rate"]["value"] == 72
    assert got["steps"]["value"] == 8421
    assert got["sleep_duration"]["value"] == 7 * 60 + 32
    assert any("low OCR confidence" in f for f in got["sleep_duration"]["flags"])
    assert any("manufacturer" in f for f in got["device_stress_score"]["flags"])
    assert "self_reported_stress" not in got
    assert res["dates_seen"] and res["times_seen"]


def test_ocr_no_invention():
    res = ocr.extract_candidates([{"text": "Good morning", "confidence": 95}, {"text": "Today", "confidence": 95}])
    assert res["candidates"] == []


def test_screenshot_rejects_non_images(client):
    r = client.post("/api/imports/screenshot/extract", files={"file": ("a.png", io.BytesIO(b"not an image"), "image/png")})
    assert r.status_code == 415


@pytest.mark.skipif(not ocr.status()["available"], reason="Tesseract not installed")
def test_screenshot_end_to_end(client):
    from PIL import Image, ImageDraw, ImageFont

    try:
        font = ImageFont.truetype("arial.ttf", 56)
    except OSError:
        pytest.skip("Arial font not available to render the test image")
    img = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(img)
    d.text((60, 60), "Heart rate", fill="black", font=font)
    d.text((60, 160), "72 bpm", fill="black", font=font)
    d.text((60, 300), "8,421 steps", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    r = client.post("/api/imports/screenshot/extract", files={"file": ("shot.png", io.BytesIO(buf.getvalue()), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    got = {c["metric"]: c for c in body["candidates"]}
    assert got["heart_rate"]["value"] == 72 and got["steps"]["value"] == 8421
    no_confirm = client.post("/api/imports/screenshot/commit", json={"token": body["token"], "recorded_at": "2026-10-30T09:00", "records": []})
    assert no_confirm.status_code == 422
    save = client.post("/api/imports/screenshot/commit", json={
        "token": body["token"], "recorded_at": "2026-10-30T09:00", "participant_code": "OCR1", "confirmed": True,
        "records": [{"candidate_id": got["heart_rate"]["id"], "metric": "heart_rate", "value": 73}],
    })
    assert save.status_code == 201, save.text
    rows = client.get("/api/records?participant_code=OCR1").json()["rows"]
    assert rows[0]["source"] == "screenshot" and rows[0]["value_was_edited"] == 1 and rows[0]["value"] == 73


def test_user_baseline(client):
    for i, v in enumerate([60, 62, 61, 63, 60, 59, 61, 62, 60, 61]):
        client.post("/api/records/manual", json={"participant_code": "B01", "recorded_at": f"2026-10-20T08:{i:02d}", "measurements": {"heart_rate": v}})
    client.post("/api/records/manual", json={"participant_code": "B01", "recorded_at": "2026-10-21T08:00", "measurements": {"heart_rate": 75}})
    r = client.get("/api/baseline/user", params={"participant_code": "B01", "start": "2026-10-20T00:00", "end": "2026-10-20T23:59"}).json()
    assert r["n_readings"] == 10 and r["meets_minimum"]
    assert r["subsequent"][0]["delta_from_baseline"] == 75 - r["baseline_median"]
