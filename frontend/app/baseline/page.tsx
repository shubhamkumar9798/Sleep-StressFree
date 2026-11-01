"use client";

import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, Badge, Button, Card, Empty, Field, inputCls, Loading, PageHeader, Table, Td } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Row = {
  participant: string;
  username: string;
  eligible: boolean;
  exclusion_reasons: string[];
  calibration_samples: number | null;
  min_calibration_samples: number;
  meets_minimum: boolean;
  baseline_median: number | null;
  baseline_sd: number | null;
  relax_windows: number | null;
  stress_windows: number | null;
  relax_segment_delta: number | null;
  stress_segment_delta: number | null;
};
type Detail = {
  participant: string;
  session: Record<string, unknown>;
  markers_minutes: Record<string, number>;
  raw_hr: { minute: number; hr: number }[];
  windows: { minutes_from_hr_start: number; phase: string; hr_mean: number; hr_mean_delta: number }[];
};
type UserBaseline = {
  n_readings: number; min_readings_required: number; meets_minimum: boolean; baseline_median?: number; baseline_sd?: number | null;
  sources: string[]; note: string; subsequent: { recorded_at: string; value: number; source: string; delta_from_baseline: number }[];
};

export default function BaselinePage() {
  const list = useApi<{ participants: Row[]; note: string; calibration_minutes: number }>("/api/baseline/participants");
  const [sel, setSel] = useState<string | null>(null);
  const detail = useApi<Detail>(sel ? `/api/baseline/participants/${sel}` : null);

  return (
    <>
      <PageHeader
        title="Individual baseline analysis"
        subtitle="Each participant's resting baseline comes from the first minutes of their own heart-rate recording. Exceeding the baseline is not treated as evidence of stress."
      />
      {list.loading ? <Loading /> : list.error || !list.data ? <Alert tone="bad" title="Not available">{list.error}</Alert> : (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="QoL_Stress participants" description={list.data.note}>
            <div className="max-h-[560px] overflow-y-auto">
              <Table dense head={["ID", "Calib. n", "Baseline", "Δ relax", "Δ stress", "Status"]}>
                {list.data.participants.map((r) => (
                  <tr key={r.username} className={sel === r.username ? "bg-brand-soft/50" : "cursor-pointer hover:bg-slate-50"} onClick={() => setSel(r.username)}>
                    <Td mono><button className="text-brand hover:underline" onClick={() => setSel(r.username)}>{r.participant}</button></Td>
                    <Td mono>{r.calibration_samples ?? "—"}</Td>
                    <Td mono>{r.baseline_median != null ? `${fmt(r.baseline_median, 0)} ± ${fmt(r.baseline_sd, 1)}` : "—"}</Td>
                    <Td mono>{fmt(r.relax_segment_delta, 1)}</Td>
                    <Td mono>{fmt(r.stress_segment_delta, 1)}</Td>
                    <Td>{r.eligible ? <Badge tone="ok">valid</Badge> : <span title={r.exclusion_reasons.join("; ")}><Badge tone={r.meets_minimum ? "warn" : "bad"}>{r.meets_minimum ? "excluded" : "insufficient"}</Badge></span>}</Td>
                  </tr>
                ))}
              </Table>
            </div>
            <p className="mt-2 text-xs text-muted">Δ = segment mean HR − baseline median (bpm). Minimum {list.data.participants[0]?.min_calibration_samples} calibration samples.</p>
          </Card>
          <Card title={sel ? `Participant ${sel.slice(0, 8)}` : "Session timeline"}>
            {!sel ? <Empty title="Select a participant">The raw heart rate, calibration period and reconstructed phases will be shown.</Empty>
              : detail.loading ? <Loading /> : detail.error || !detail.data ? <Alert tone="bad">{detail.error}</Alert> : <Timeline d={detail.data} row={list.data.participants.find((p) => p.username === sel)!} />}
          </Card>
        </div>
      )}
      <UserBaselineCard />
    </>
  );
}

function Timeline({ d, row }: { d: Detail; row: Row }) {
  const m = d.markers_minutes;
  return (
    <div className="space-y-4">
      {!row.eligible && <Alert tone="warn" title="Not used in experiments">{row.exclusion_reasons.join("; ")}</Alert>}
      <div className="h-64">
        <ResponsiveContainer>
          <LineChart data={d.raw_hr} margin={{ left: 0, right: 12 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="minute" type="number" domain={["dataMin", "dataMax"]} tickFormatter={(v) => `${Math.round(v)}`} tick={{ fontSize: 11 }} label={{ value: "minutes from HR start", position: "insideBottom", offset: -2, fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} unit=" bpm" width={70} />
            <Tooltip formatter={(v) => [`${v} bpm`, "HR"]} labelFormatter={(v) => `${Number(v).toFixed(1)} min`} />
            {m.calib_end !== undefined && <ReferenceArea x1={0} x2={m.calib_end} fill="#3f51b5" fillOpacity={0.08} label={{ value: "calibration", fontSize: 10, position: "insideTop" }} />}
            {m.calib_end !== undefined && m.relax_eval_end !== undefined && <ReferenceArea x1={m.calib_end} x2={m.relax_eval_end} fill="#0e9f8e" fillOpacity={0.08} label={{ value: "relax", fontSize: 10, position: "insideTop" }} />}
            {m.stress_eval_start !== undefined && m.stress_eval_end !== undefined && <ReferenceArea x1={m.stress_eval_start} x2={m.stress_eval_end} fill="#e0662b" fillOpacity={0.08} label={{ value: "stress", fontSize: 10, position: "insideTop" }} />}
            {m.stai_relax_t !== undefined && <ReferenceLine x={m.stai_relax_t} stroke="#0e9f8e" strokeDasharray="4 4" />}
            {m.stai_stress_t !== undefined && <ReferenceLine x={m.stai_stress_t} stroke="#e0662b" strokeDasharray="4 4" />}
            {row.baseline_median != null && <ReferenceLine y={row.baseline_median} stroke="#3f51b5" label={{ value: "baseline", fontSize: 10, position: "right" }} />}
            <Line dataKey="hr" dot={false} stroke="#334155" strokeWidth={1.2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted">Dashed lines: STAI questionnaire timestamps (phase ends). Shaded: calibration and evaluation periods after guard bands. Raw Fitbit samples (down-sampled for display).</p>
      <div className="h-52">
        <ResponsiveContainer>
          <ScatterChart margin={{ left: 0, right: 12 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="minutes_from_hr_start" type="number" name="minute" tick={{ fontSize: 11 }} domain={["dataMin", "dataMax"]} tickFormatter={(v) => `${Math.round(v)}`} />
            <YAxis dataKey="hr_mean_delta" name="Δ from baseline" unit=" bpm" tick={{ fontSize: 11 }} width={70} />
            <ReferenceLine y={0} stroke="#94a3b8" />
            <Tooltip formatter={(v) => fmt(Number(v), 1)} />
            <Scatter data={d.windows.filter((w) => w.phase === "relax")} fill="#0e9f8e" name="relax windows" />
            <Scatter data={d.windows.filter((w) => w.phase === "stress")} fill="#e0662b" name="stress windows" />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted">Window mean HR minus baseline median. Teal = relax windows, orange = stress windows.</p>
    </div>
  );
}

function UserBaselineCard() {
  const [code, setCode] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [res, setRes] = useState<UserBaseline | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true); setErr(null); setRes(null);
    try {
      setRes(await api.get<UserBaseline>(`/api/baseline/user?participant_code=${encodeURIComponent(code)}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`));
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Card title="Baseline for your own records" className="mt-6" description="For manually entered, CSV or screenshot heart-rate records (e.g. a future Amazfit export). Choose the baseline period explicitly.">
      <div className="grid gap-4 md:grid-cols-4">
        <Field label="Participant code" htmlFor="ub-code"><input id="ub-code" className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} placeholder="P001" /></Field>
        <Field label="Baseline start" htmlFor="ub-start"><input id="ub-start" type="datetime-local" className={inputCls} value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="Baseline end" htmlFor="ub-end"><input id="ub-end" type="datetime-local" className={inputCls} value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        <div className="flex items-end"><Button onClick={run} loading={busy} disabled={!code || !start || !end}>Calculate baseline</Button></div>
      </div>
      {err && <div className="mt-4"><Alert tone="bad">{err}</Alert></div>}
      {res && (
        <div className="mt-4 space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-3">
            <span>{res.n_readings} heart-rate readings in the period ({res.sources.join(", ") || "none"})</span>
            {res.meets_minimum ? <Badge tone="ok">meets minimum ({res.min_readings_required})</Badge> : <Badge tone="bad">below minimum of {res.min_readings_required} — not reliable</Badge>}
            {res.baseline_median !== undefined && <span className="num">Baseline median {fmt(res.baseline_median, 1)} bpm (SD {fmt(res.baseline_sd ?? null, 1)})</span>}
          </div>
          <Alert tone="info">{res.note}</Alert>
          {res.subsequent.length > 0 && (
            <Table dense head={["Recorded at", "HR (bpm)", "Δ from baseline", "Source"]}>
              {res.subsequent.slice(0, 50).map((s) => (
                <tr key={s.recorded_at + s.value}><Td mono>{s.recorded_at}</Td><Td mono>{s.value}</Td><Td mono>{fmt(s.delta_from_baseline, 1)}</Td><Td>{s.source}</Td></tr>
              ))}
            </Table>
          )}
        </div>
      )}
    </Card>
  );
}
