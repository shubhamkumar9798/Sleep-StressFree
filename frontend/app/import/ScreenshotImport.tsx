"use client";

import { Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Empty, Field, inputCls, Loading } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Candidate = { id: string; metric: string; value: number; unit: string; source_text: string; ocr_confidence: number; flags: string[] };
type Extract = {
  token: string; filename: string; ocr_text: string; candidates: Candidate[]; dates_seen: string[]; times_seen: string[];
  warnings: string[]; note: string; store_screenshots: boolean;
};
type Row = { candidate_id?: string; metric: string; value: string; keep: boolean; flags: string[]; source_text?: string; conf?: number };

const METRICS: Record<string, string> = {
  heart_rate: "Heart rate (bpm)", resting_heart_rate: "Resting HR (bpm)", steps: "Steps", sleep_duration: "Sleep (min)",
  hrv: "HRV (ms)", spo2: "SpO₂ (%)", body_temperature: "Temperature (°C)", device_stress_score: "Device stress score",
};

export function ScreenshotImport() {
  const status = useApi<{ available: boolean; version?: string; message?: string; store_screenshots: boolean }>("/api/imports/screenshot/status");
  const [img, setImg] = useState<string | null>(null);
  const [ex, setEx] = useState<Extract | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [when, setWhen] = useState("");
  const [code, setCode] = useState("");
  const [device, setDevice] = useState("Amazfit / Zepp app (model not confirmed)");
  const [confirmed, setConfirmed] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => () => { if (img) URL.revokeObjectURL(img); }, [img]);

  const upload = async (f: File | undefined) => {
    if (!f) return;
    setErr(null); setOk(null); setEx(null); setRows([]); setConfirmed(false);
    if (img) URL.revokeObjectURL(img);
    setImg(URL.createObjectURL(f));
    setBusy(true);
    try {
      const r = await api.upload<Extract>("/api/imports/screenshot/extract", f);
      setEx(r);
      setRows(r.candidates.map((c) => ({ candidate_id: c.id, metric: c.metric, value: String(c.value), keep: c.flags.length === 0, flags: c.flags, source_text: c.source_text, conf: c.ocr_confidence })));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const discard = async () => {
    if (ex) await api.del(`/api/imports/screenshot/${ex.token}`).catch(() => undefined);
    setEx(null); setRows([]); setImg(null);
  };
  const save = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await api.post<{ record_ids: number[]; screenshot_stored: boolean }>("/api/imports/screenshot/commit", {
        token: ex!.token, recorded_at: when, participant_code: code || null, device_label: device || null, confirmed,
        records: rows.filter((r) => r.keep).map((r) => ({ candidate_id: r.candidate_id, metric: r.metric, value: Number(r.value) })),
      });
      setOk(`Saved ${r.record_ids.length} value(s) with source “screenshot”. ${r.screenshot_stored ? "The screenshot was stored." : "Only the screenshot's file name and SHA-256 hash were stored."}`);
      setEx(null); setRows([]); setImg(null);
    } catch (e) {
      const d = (e as ApiError).details;
      setErr((e as Error).message + (Array.isArray(d) ? " " + d.join(" ") : ""));
    } finally { setBusy(false); }
  };
  const upd = (i: number, patch: Partial<Row>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  if (status.loading) return <Loading />;
  return (
    <div className="space-y-6">
      {status.data && !status.data.available && <Alert tone="warn" title="OCR unavailable">{status.data.message}</Alert>}
      <Card title="Upload screenshot" description="PNG or JPG from your smartwatch app. Only numbers that are printed as text are read; values in charts are never estimated.">
        <input type="file" accept="image/png,image/jpeg" aria-label="Screenshot" disabled={!status.data?.available} onChange={(e) => upload(e.target.files?.[0])} className="block text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-3 file:py-2 file:text-sm file:font-medium file:text-white disabled:opacity-50" />
        {status.data?.available && <p className="mt-2 text-xs text-muted">Tesseract {status.data.version}. Screenshot storage: {status.data.store_screenshots ? "enabled (STORE_SCREENSHOTS=true)" : "off – only file name and hash are kept"}.</p>}
        {busy && !ex && <Loading label="Reading text…" />}
        {err && <div className="mt-4"><Alert tone="bad">{err}</Alert></div>}
        {ok && <div className="mt-4"><Alert tone="ok">{ok}</Alert></div>}
      </Card>
      {ex && (
        <div className="grid gap-6 lg:grid-cols-5">
          <Card title="Screenshot" className="lg:col-span-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {img && <img src={img} alt="Uploaded smartwatch screenshot" className="max-h-[640px] w-full rounded-lg border border-line object-contain" />}
            <details className="mt-3 text-xs">
              <summary className="cursor-pointer text-muted">Raw OCR text (with confidence)</summary>
              <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-mono">{ex.ocr_text || "(no text)"}</pre>
            </details>
          </Card>
          <Card title="Review extracted values" className="lg:col-span-3" description={ex.note}>
            <div className="space-y-3">
              {ex.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
              {rows.length === 0 && <Empty title="No candidate values">Add values manually below only if you can see them in the screenshot.</Empty>}
              {rows.map((r, i) => (
                <div key={i} className={`rounded-lg border p-3 ${r.flags.length ? "border-amber-300 bg-amber-50/50" : "border-line"}`}>
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={r.keep} onChange={(e) => upd(i, { keep: e.target.checked })} />Save</label>
                    <div className="min-w-44 flex-1">
                      <label className="text-xs text-muted" htmlFor={`s-m-${i}`}>Measurement</label>
                      <select id={`s-m-${i}`} className={inputCls} value={r.metric} onChange={(e) => upd(i, { metric: e.target.value })}>
                        {Object.entries(METRICS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                      </select>
                    </div>
                    <div className="w-32">
                      <label className="text-xs text-muted" htmlFor={`s-v-${i}`}>Value</label>
                      <input id={`s-v-${i}`} type="number" step="any" className={inputCls} value={r.value} onChange={(e) => upd(i, { value: e.target.value })} />
                    </div>
                    <Button variant="ghost" aria-label="Remove" onClick={() => setRows(rows.filter((_, j) => j !== i))}><Trash2 className="h-4 w-4" /></Button>
                  </div>
                  <div className="mt-2 text-xs text-muted">
                    {r.source_text ? <>Read from: “{r.source_text}” · OCR confidence {r.conf?.toFixed(0)}%</> : "Added manually during review"}
                  </div>
                  {r.flags.map((f) => <div key={f} className="mt-1"><Badge tone="warn">{f}</Badge></div>)}
                </div>
              ))}
              <Button variant="secondary" onClick={() => setRows([...rows, { metric: "heart_rate", value: "", keep: true, flags: [] }])}><Plus className="h-4 w-4" />Add a value visible in the screenshot</Button>
              <div className="grid gap-4 border-t border-line pt-4 md:grid-cols-3">
                <Field label="Measurement date & time" htmlFor="s-when" hint={ex.dates_seen.length || ex.times_seen.length ? `Seen in image: ${[...ex.dates_seen, ...ex.times_seen].join(", ")}` : "No date recognised – enter it from the screenshot."}>
                  <input id="s-when" type="datetime-local" className={inputCls} value={when} onChange={(e) => setWhen(e.target.value)} />
                </Field>
                <Field label="Participant code" htmlFor="s-code"><input id="s-code" className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} /></Field>
                <Field label="Device" htmlFor="s-dev"><input id="s-dev" className={inputCls} value={device} onChange={(e) => setDevice(e.target.value)} /></Field>
              </div>
              <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />I checked every value against the screenshot and corrected OCR errors.</label>
              <div className="flex gap-2">
                <Button onClick={save} loading={busy} disabled={!confirmed || !when || !rows.some((r) => r.keep)}>Save confirmed values</Button>
                <Button variant="ghost" onClick={discard}>Discard upload</Button>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
