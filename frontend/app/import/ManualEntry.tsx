"use client";

import { useState } from "react";
import { Alert, Button, Card, Field, inputCls } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

const FIELDS: { metric: string; label: string; unit: string; step?: string; hint?: string }[] = [
  { metric: "heart_rate", label: "Heart rate", unit: "bpm" },
  { metric: "resting_heart_rate", label: "Resting heart rate", unit: "bpm" },
  { metric: "steps", label: "Steps", unit: "steps", step: "1" },
  { metric: "sleep_duration", label: "Sleep duration", unit: "minutes", hint: "e.g. 7 h 30 min = 450" },
  { metric: "hrv", label: "HRV", unit: "ms" },
  { metric: "spo2", label: "SpO₂", unit: "%" },
  { metric: "body_temperature", label: "Body / skin temperature", unit: "°C", step: "0.1" },
  { metric: "device_stress_score", label: "Device stress score", unit: "device scale", hint: "Manufacturer's score, stored separately from self-report." },
];

const nowLocal = () => {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
};

export function ManualEntry() {
  const [code, setCode] = useState("");
  const [when, setWhen] = useState(nowLocal());
  const [device, setDevice] = useState("Amazfit (model not confirmed)");
  const [vals, setVals] = useState<Record<string, string>>({});
  const [stress, setStress] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string; details?: string[] } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    const measurements: Record<string, number> = {};
    for (const [k, v] of Object.entries(vals)) if (v.trim() !== "") measurements[k] = Number(v);
    if (stress) measurements.self_reported_stress = Number(stress);
    try {
      const r = await api.post<{ n_records: number }>("/api/records/manual", {
        participant_code: code || null, recorded_at: when, device_label: device || null, measurements, notes: notes || null,
      });
      setMsg({ tone: "ok", text: `Saved ${r.n_records} measurement(s) as source “manual”. Empty fields were stored as missing, not zero.` });
      setVals({}); setStress(""); setNotes("");
    } catch (err) {
      const d = (err as ApiError).details;
      setMsg({ tone: "bad", text: (err as Error).message, details: Array.isArray(d) ? d.map(String) : undefined });
    } finally { setBusy(false); }
  };

  return (
    <Card title="Manual entry" description="All measurement fields are optional; fill in only what you actually observed. Manually entered values are labelled as unverified.">
      <form onSubmit={submit} className="space-y-6">
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="Participant code" htmlFor="m-code" hint="Pseudonymous, e.g. P001"><input id="m-code" className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} maxLength={40} /></Field>
          <Field label="Date and time of measurement" htmlFor="m-when"><input id="m-when" type="datetime-local" required className={inputCls} value={when} onChange={(e) => setWhen(e.target.value)} /></Field>
          <Field label="Device" htmlFor="m-dev" hint="Free text; not verified"><input id="m-dev" className={inputCls} value={device} onChange={(e) => setDevice(e.target.value)} /></Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FIELDS.map((f) => (
            <Field key={f.metric} label={`${f.label} (${f.unit})`} htmlFor={`m-${f.metric}`} hint={f.hint}>
              <input id={`m-${f.metric}`} type="number" step={f.step ?? "any"} inputMode="decimal" className={inputCls} value={vals[f.metric] ?? ""} onChange={(e) => setVals({ ...vals, [f.metric]: e.target.value })} />
            </Field>
          ))}
        </div>
        <fieldset>
          <legend className="text-sm font-medium">How stressed do you feel right now? (optional self-report)</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {[["1", "Not stressed"], ["2", "Slightly"], ["3", "Moderately"], ["4", "Very"], ["5", "Extremely stressed"]].map(([v, l]) => (
              <label key={v} className={`cursor-pointer rounded-lg border px-3 py-2 text-sm ${stress === v ? "border-brand bg-brand-soft text-brand" : "border-line bg-white"}`}>
                <input type="radio" name="stress" value={v} className="sr-only" checked={stress === v} onChange={() => setStress(v)} />
                {v} · {l}
              </label>
            ))}
            {stress && <button type="button" className="text-sm text-muted underline" onClick={() => setStress("")}>clear</button>}
          </div>
        </fieldset>
        <Field label="Notes" htmlFor="m-notes"><textarea id="m-notes" rows={2} className={inputCls} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Context, e.g. after climbing stairs" /></Field>
        <div className="flex items-center gap-3">
          <Button type="submit" loading={busy}>Save record</Button>
        </div>
        {msg && <Alert tone={msg.tone} title={msg.text}>{msg.details && <ul className="list-inside list-disc">{msg.details.map((d) => <li key={d}>{d}</li>)}</ul>}</Alert>}
      </form>
    </Card>
  );
}
