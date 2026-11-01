"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { Alert, Badge, Button, Card, Empty, Loading, PageHeader, Stat, Table, Td } from "@/components/ui";
import { api, fmt } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Summary = {
  config: Record<string, number>;
  warnings: string[];
  hr_samples: Record<string, number>;
  participants_total: number;
  participants_eligible: number;
  exclusions: { participant: string; reasons: string[] }[];
  windows_per_phase: Record<string, number>;
  segments: number;
  participant_level_rows: number;
  ecg_clock_inconsistent: number;
  eda_rows_used?: number;
  pss_scoring_check?: { verified: boolean; agreement?: number; reason?: string; n?: number };
  stai_scoring_check?: { verified: boolean; agreement?: number; reason?: string; n?: number };
  segment_means?: Record<string, Record<string, number | null>>;
  feature_docs: Record<string, string>;
  fingerprint: string;
};

const CONFIG_LABELS: Record<string, string> = {
  calibration_minutes: "Calibration period (min)",
  guard_before_questionnaire_minutes: "Guard before each STAI (min)",
  guard_after_relax_questionnaire_minutes: "Guard after relax STAI (min)",
  window_seconds: "Window length (s)",
  min_samples_per_window: "Min. HR samples per window",
  min_calibration_samples: "Min. calibration samples",
  min_phase_minutes: "Min. evaluation period per phase (min)",
  segment_minutes: "Segment length (min)",
  hr_valid_min: "Valid HR min (bpm)",
  hr_valid_max: "Valid HR max (bpm)",
};

export default function PreprocessingPage() {
  const { data, error, loading, reload } = useApi<Summary>("/api/preprocessing/summary");
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const rerun = async () => {
    setRunning(true);
    setMsg(null);
    try {
      await api.post("/api/preprocessing/run");
      await reload();
      setMsg("Preprocessing re-run from the raw CSV files.");
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Data preprocessing"
        subtitle="How raw Fitbit heart rate is turned into labelled analysis units. Phases are reconstructed from the STAI questionnaire timestamps because the heart-rate files carry no phase label."
        actions={<Button variant="secondary" onClick={rerun} loading={running}><RefreshCw className="h-4 w-4" />Re-run preprocessing</Button>}
      />
      {msg && <div className="mb-4"><Alert tone="info">{msg}</Alert></div>}
      {loading ? <Loading /> : error || !data ? <Alert tone="bad" title="Preprocessing unavailable">{error}</Alert> : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Participants" value={data.participants_total} hint="with STAI or HR data" />
            <Stat label="Eligible" value={data.participants_eligible} tone="ok" hint={`${data.exclusions.length} excluded`} />
            <Stat label="60-s windows" value={`${data.windows_per_phase.relax ?? 0} / ${data.windows_per_phase.stress ?? 0}`} hint="relax / stress" />
            <Stat label="Phase segments" value={data.segments} hint="last 5 min of each phase" />
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card title="Pipeline" description="Applied identically to every participant; parameters below.">
              <ol className="list-inside list-decimal space-y-1.5 text-sm">
                <li>Parse clock times (no dates in the files) and drop invalid times, out-of-range HR and duplicate (participant, time) samples. No interpolation or filling.</li>
                <li>Per participant, sort by time. Relax ends at the STAI-relax timestamp, stress ends at the STAI-stress timestamp.</li>
                <li>The first {data.config.calibration_minutes} min of HR are the <b>calibration</b> period: used only to compute the personal baseline, never evaluated.</li>
                <li>Guard bands remove the minutes around each questionnaire and the phase transition.</li>
                <li>Non-overlapping {data.config.window_seconds}-s windows (≥ {data.config.min_samples_per_window} samples) give window features; the last {data.config.segment_minutes} min of each phase give segment features.</li>
                <li>EDA and ECG are summarised per phase (they carry their own phase label) and joined at segment level only.</li>
                <li>Scaling and imputation happen later inside scikit-learn pipelines, fitted on training participants only.</li>
              </ol>
            </Card>
            <Card title="Parameters">
              <Table dense head={["Parameter", "Value"]}>
                {Object.entries(data.config).map(([k, v]) => (
                  <tr key={k}><Td>{CONFIG_LABELS[k] ?? k}</Td><Td mono>{v}</Td></tr>
                ))}
              </Table>
              <p className="mt-2 text-xs text-muted">Change with environment variables in backend/.env (see README), then re-run.</p>
            </Card>
          </div>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card title="Data-quality checks">
              <ul className="space-y-2 text-sm">
                <li className="flex justify-between gap-2"><span>HR samples raw → clean</span><span className="num">{data.hr_samples.raw} → {data.hr_samples.clean}</span></li>
                <li className="flex justify-between gap-2"><span>Invalid times / out-of-range values / duplicates</span><span className="num">{data.hr_samples.invalid_time} / {data.hr_samples.invalid_or_out_of_range_value} / {data.hr_samples.duplicates_dropped}</span></li>
                <li className="flex justify-between gap-2"><span>EDA rows used (valid, time ≥ 0)</span><span className="num">{data.eda_rows_used ?? "—"}</span></li>
                <li className="flex justify-between gap-2"><span>PSS-14 total reproduced from item answers</span>
                  <span>{data.pss_scoring_check?.verified ? <Badge tone="ok">{fmt((data.pss_scoring_check.agreement ?? 0) * 100, 0)}% match</Badge> : <Badge tone="warn">{data.pss_scoring_check?.agreement !== undefined ? `${fmt(data.pss_scoring_check.agreement * 100, 1)}% match` : data.pss_scoring_check?.reason}</Badge>}</span></li>
                <li className="flex justify-between gap-2"><span>STAI total reproduced from item answers</span>
                  <span>{data.stai_scoring_check?.verified ? <Badge tone="ok">100% match</Badge> : <Badge tone="warn">{data.stai_scoring_check?.agreement !== undefined ? `${fmt(data.stai_scoring_check.agreement * 100, 1)}% match` : data.stai_scoring_check?.reason}</Badge>}</span></li>
                <li className="flex justify-between gap-2"><span>ECG clock inconsistent with reconstructed phases</span><span className="num">{data.ecg_clock_inconsistent}</span></li>
              </ul>
              <div className="mt-3 space-y-2">{data.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}</div>
              <p className="mt-2 text-xs text-muted">Provided questionnaire totals are used as-is; mismatches are reported, not corrected.</p>
            </Card>
            <Card title="Excluded participants" description="Excluded from all experiments so every comparison uses the same people.">
              {data.exclusions.length === 0 ? <Empty title="No exclusions" /> : (
                <Table dense head={["Participant", "Reason(s)"]}>
                  {data.exclusions.map((e) => (
                    <tr key={e.participant}><Td mono>{e.participant}</Td><Td className="whitespace-normal">{e.reasons.join("; ")}</Td></tr>
                  ))}
                </Table>
              )}
            </Card>
          </div>

          {data.segment_means && (
            <Card title="Segment means by phase (descriptive)" className="mt-6" description="Averages over eligible participants. Descriptive statistics, not model results.">
              <Table dense head={["Phase", ...Object.keys(data.segment_means.relax ?? {})]}>
                {Object.entries(data.segment_means).map(([phase, vals]) => (
                  <tr key={phase}>
                    <Td><Badge tone={phase === "stress" ? "stress" : "relax"}>{phase}</Badge></Td>
                    {Object.values(vals).map((v, i) => <Td key={i} mono>{fmt(v, 2)}</Td>)}
                  </tr>
                ))}
              </Table>
            </Card>
          )}

          <Card title="Feature definitions" className="mt-6">
            <Table dense head={["Feature", "Calculation"]}>
              {Object.entries(data.feature_docs).map(([k, v]) => (
                <tr key={k}><Td mono>{k}</Td><Td className="whitespace-normal">{v}</Td></tr>
              ))}
            </Table>
            <p className="mt-2 text-xs text-muted">Not computed: time-of-day features (sessions were scheduled at different times, a confound), HRV from the Fitbit HR stream (it has no beat-to-beat intervals), ECG waveform HRV in the app (computed only in the research scripts from the 250 Hz waveforms), activity features (no activity data).</p>
          </Card>
        </>
      )}
    </>
  );
}
