"use client";

import { Gauge } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Alert, Badge, Button, Card, Disclaimer, Empty, Field, inputCls, Loading, PageHeader, Table, Td } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import type { Catalog, TrainedModel } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Prediction = {
  target_name: string;
  experiment: string;
  model: string;
  prediction: string | number;
  probabilities?: Record<string, number>;
  decision_value?: number;
  features: Record<string, number>;
  within_training_range: boolean;
  out_of_range_features: { feature: string; value: number; training_min: number; training_max: number }[];
  cv_metrics: Record<string, number | null>;
  trained_on: string;
  input_source: string;
  interpretation: string;
  disclaimer: string;
  warnings: string[];
};

const parseList = (s: string) => s.split(/[\s,;]+/).filter(Boolean).map(Number);

const WELLBEING = [
  "Take a short break away from screens and stretch.",
  "Try a few minutes of slow breathing (e.g. breathe out longer than you breathe in).",
  "Keep a regular sleep schedule, including at weekends.",
  "A gentle walk can help when you are able to take one.",
  "If stress or low mood persists, talk to someone you trust or your college counselling / student support service.",
];

export default function EstimatePage() {
  const models = useApi<{ models: TrainedModel[]; interactive_targets: string[] }>("/api/models");
  const cat = useApi<Catalog>("/api/experiments/catalog");
  const usable = useMemo(
    () => (models.data?.models ?? []).filter((m) => m.is_active && m.compatible && m.artifact_exists && models.data!.interactive_targets.includes(m.target)),
    [models.data],
  );
  const [modelId, setModelId] = useState<number | null>(null);
  const current = usable.find((m) => m.id === modelId) ?? usable[0];
  const [hr, setHr] = useState("");
  const [cal, setCal] = useState("");
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [source, setSource] = useState("manual entry");
  const [res, setRes] = useState<Prediction | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const needsCal = current?.feature_names.some((f) => f.includes("delta") || f.endsWith("_ratio") || f.endsWith("_z"));
  const extraFeats = current?.feature_names.filter((f) => f.startsWith("eda_") || f.startsWith("ecg_")) ?? [];
  const hrValues = parseList(hr);
  const calValues = parseList(cal);
  const isWindow = current?.target === "phase_window";

  const submit = async () => {
    if (!current) return;
    setBusy(true); setErr(null); setRes(null);
    try {
      if (hrValues.some((v) => Number.isNaN(v))) throw new Error("Heart-rate values must be numbers separated by commas or spaces.");
      setRes(await api.post<Prediction>("/api/predict", {
        model_id: current.id,
        hr_values: hrValues,
        duration_seconds: isWindow ? 60 : 300,
        calibration_values: needsCal ? calValues : undefined,
        extra_features: extraFeats.length ? Object.fromEntries(extraFeats.map((f) => [f, Number(extra[f])])) : undefined,
        input_source: source,
      }));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Stress estimation (exploratory)" subtitle="Enter a sequence of heart-rate readings to see how a trained research model classifies it. One reading is never enough: models need the same kind of input they were trained on." />
      <Disclaimer />
      {models.loading || cat.loading ? <Loading /> : models.error ? <div className="mt-6"><Alert tone="bad">{models.error}</Alert></div> : usable.length === 0 ? (
        <div className="mt-6"><Empty title="No trained model available" icon={<Gauge className="h-6 w-6" />}>
          Predictions are disabled until a compatible model is trained. Go to <Link href="/models" className="text-brand underline">Model Training</Link> and train a model for the phase or STAI target. Participant-level (PSS-14) models cannot be used here.
        </Empty></div>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <Card title="Input">
            <div className="space-y-4">
              <Field label="Model" htmlFor="model">
                <select id="model" className={inputCls} value={current?.id} onChange={(e) => { setModelId(Number(e.target.value)); setRes(null); }}>
                  {usable.map((m) => <option key={m.id} value={m.id}>#{m.id} · {cat.data?.targets[m.target]?.name} · Exp. {m.experiment} · {m.model.replaceAll("_", " ")}</option>)}
                </select>
              </Field>
              <Field label={isWindow ? "Heart-rate readings over one minute (bpm)" : "Heart-rate readings over the last 5 minutes (bpm)"} htmlFor="hr"
                hint={`${hrValues.length} values entered. Assumed evenly spaced over ${isWindow ? "60 s" : "5 min"}. Training windows had at least ${isWindow ? 15 : 75} readings.`}>
                <textarea id="hr" rows={4} className={inputCls} value={hr} onChange={(e) => setHr(e.target.value)} placeholder="72, 74, 73, 75, …" />
              </Field>
              {needsCal && (
                <Field label="Resting calibration readings (bpm)" htmlFor="cal" hint={`${calValues.length} values. This personalised model needs ≥ 45 readings from about 3 minutes of seated rest.`}>
                  <textarea id="cal" rows={3} className={inputCls} value={cal} onChange={(e) => setCal(e.target.value)} placeholder="66, 65, 67, …" />
                </Field>
              )}
              {extraFeats.map((f) => (
                <Field key={f} label={f} htmlFor={f} hint="Required by this Experiment C model (same units as the QoL_Stress dataset).">
                  <input id={f} type="number" step="any" className={inputCls} value={extra[f] ?? ""} onChange={(e) => setExtra({ ...extra, [f]: e.target.value })} />
                </Field>
              ))}
              <Field label="Where did these values come from?" htmlFor="src">
                <select id="src" className={inputCls} value={source} onChange={(e) => setSource(e.target.value)}>
                  <option>manual entry</option><option>pasted from CSV</option><option>screenshot-derived</option>
                </select>
              </Field>
              <Button onClick={submit} loading={busy} disabled={!hrValues.length}>Estimate</Button>
              {err && <Alert tone="bad">{err}</Alert>}
            </div>
          </Card>
          <Card title="Result">
            {!res ? <Empty title="No estimate yet">Results show the model, its features, its cross-validated performance and whether your input lies within the training data.</Empty> : (
              <div className="space-y-4 text-sm">
                <div className="rounded-lg border border-line bg-slate-50 p-4">
                  <div className="text-xs uppercase tracking-wide text-muted">{res.target_name} · experimental estimate</div>
                  <div className="num mt-1 text-3xl font-semibold capitalize">{typeof res.prediction === "number" ? fmt(res.prediction, 1) : `${res.prediction}-like`}</div>
                  {res.probabilities && <div className="mt-1 text-muted">{Object.entries(res.probabilities).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(" · ")} (model scores, not calibrated certainty)</div>}
                  <p className="mt-2">{res.interpretation}</p>
                </div>
                {res.within_training_range ? <Alert tone="ok">All features are within the range seen in training.</Alert> : (
                  <Alert tone="warn" title="Outside the training data">
                    {res.out_of_range_features.map((o) => `${o.feature} = ${fmt(o.value, 1)} (training ${fmt(o.training_min, 1)}–${fmt(o.training_max, 1)})`).join("; ")}. The estimate is extrapolation and unreliable.
                  </Alert>
                )}
                {res.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
                <Table dense head={["Feature (computed from your input)", "Value"]}>
                  {Object.entries(res.features).map(([k, v]) => <tr key={k}><Td mono>{k}</Td><Td mono>{fmt(v, 2)}</Td></tr>)}
                </Table>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                  <dt className="text-muted">Model</dt><dd>Experiment {res.experiment}, {res.model.replaceAll("_", " ")}</dd>
                  <dt className="text-muted">Trained on</dt><dd>{res.trained_on}</dd>
                  <dt className="text-muted">CV on unseen participants</dt><dd className="num">{res.cv_metrics.balanced_accuracy != null ? `balanced acc. ${fmt(res.cv_metrics.balanced_accuracy)}, macro-F1 ${fmt(res.cv_metrics.macro_f1)}` : `MAE ${fmt(res.cv_metrics.mae, 2)}, R² ${fmt(res.cv_metrics.r2, 2)}`}</dd>
                  <dt className="text-muted">Input source</dt><dd><Badge>{res.input_source}</Badge></dd>
                </dl>
                <p className="text-xs text-muted">{res.disclaimer}</p>
              </div>
            )}
          </Card>
        </div>
      )}
      <Card title="General wellbeing information" className="mt-6" description="General, non-medical suggestions. They are not generated by the research model and do not depend on any estimate above.">
        <ul className="list-inside list-disc space-y-1 text-sm">{WELLBEING.map((w) => <li key={w}>{w}</li>)}</ul>
        <p className="mt-3 text-xs text-muted">This application does not diagnose stress, anxiety, depression or any other condition and gives no medication advice. If you feel unsafe or overwhelmed, contact local emergency services or a crisis line.</p>
      </Card>
    </>
  );
}
