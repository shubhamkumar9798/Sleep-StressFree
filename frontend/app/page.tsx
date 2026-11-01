"use client";

import { ArrowRight, Database, FlaskConical, Gauge, Microscope, Upload, UserRound, Workflow } from "lucide-react";
import Link from "next/link";
import { Alert, Badge, Card, Empty, Loading, PageHeader, Stat, Table, Td } from "@/components/ui";
import { fmt } from "@/lib/api";
import type { CatalogItem, DatasetStatus, Metrics, TargetDef, TrainedModel } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Dashboard = {
  dataset: DatasetStatus;
  user_records: { total: number; by_source: Record<string, number>; participants: number };
  targets: Record<string, TargetDef>;
  preprocessing?: {
    participants_total: number;
    participants_in_files: number | null;
    participants_eligible: number;
    hr_samples: number;
    windows_per_phase: Record<string, number>;
    segments: number;
    manipulation_check?: { n: number; mean_difference: number; sd_difference: number; n_higher_after_stress: number; n_equal: number; n_lower_after_stress: number };
    variables: string[];
  };
  preprocessing_error?: string;
  models: TrainedModel[];
  latest_runs: { id: number; target: string; experiment: string; model: string; metrics: Metrics; n_participants: number; n_samples: number; created_at: string; dataset_matches_current: boolean }[];
  experiments: CatalogItem[];
};

const MODULES = [
  { href: "/dataset", label: "Dataset Explorer", icon: Database, text: "Schemas, sample rows, missing values" },
  { href: "/preprocessing", label: "Preprocessing", icon: Workflow, text: "Phase reconstruction & exclusions" },
  { href: "/baseline", label: "Baseline Analysis", icon: UserRound, text: "Per-participant calibration baselines" },
  { href: "/models", label: "Model Training", icon: Microscope, text: "Participant-wise CV and saved models" },
  { href: "/experiments", label: "Research Experiments", icon: FlaskConical, text: "General vs personalised comparison" },
  { href: "/estimate", label: "Stress Estimation", icon: Gauge, text: "Exploratory predictions" },
  { href: "/import", label: "Data Import", icon: Upload, text: "Manual, CSV and screenshot data" },
];

export default function DashboardPage() {
  const { data, error, loading } = useApi<Dashboard>("/api/dashboard");
  if (loading) return <Loading label="Loading dashboard…" />;
  if (error || !data) return <Alert tone="bad" title="Backend unavailable">{error}</Alert>;

  const pp = data.preprocessing;
  const primary = Object.entries(data.targets).find(([, t]) => t.primary);
  const activeModels = data.models.filter((m) => m.is_active);
  const primaryRuns = data.latest_runs.filter((r) => r.target === "phase_window" && r.model !== "dummy");

  return (
    <>
      <PageHeader
        title="Research dashboard"
        subtitle="Can personalised heart-rate features based on individual baselines improve stress estimation compared with a general model? Everything on this page is computed from the files and runs that actually exist."
      />

      {!data.dataset.available && (
        <div className="mb-6">
          <Alert tone="warn" title="QoL_Stress dataset not found">
            {data.dataset.setup_message} <Link className="font-medium underline" href="/settings">Setup instructions</Link>
          </Alert>
        </div>
      )}
      {data.preprocessing_error && (
        <div className="mb-6">
          <Alert tone="bad" title="Preprocessing failed">{data.preprocessing_error}</Alert>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Dataset" value={data.dataset.available ? (data.dataset.complete ? "Ready" : "Partial") : "Missing"} tone={data.dataset.available ? (data.dataset.complete ? "ok" : "warn") : "bad"} hint={`${data.dataset.files.filter((f) => f.present).length}/${data.dataset.files.length} files`} />
        <Stat label="Participants" value={pp?.participants_in_files ?? "—"} hint="in participants.csv" />
        <Stat label="Eligible" value={pp?.participants_eligible ?? "—"} hint="after preprocessing checks" />
        <Stat label="HR samples" value={pp ? pp.hr_samples.toLocaleString() : "—"} hint="Fitbit, per-second file" />
        <Stat label="Windows" value={pp ? `${pp.windows_per_phase.relax ?? 0} / ${pp.windows_per_phase.stress ?? 0}` : "—"} hint="relax / stress (60 s)" />
        <Stat label="Your records" value={data.user_records.total} hint="manual, CSV, screenshot" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Selected prediction target" className="lg:col-span-2">
          {primary && (
            <div className="space-y-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{primary[1].name}</span>
                <Badge tone="brand">primary</Badge>
                <Badge>{primary[1].task}</Badge>
              </div>
              <p className="text-muted">{primary[1].description}</p>
              <p><span className="font-medium">Label source:</span> {primary[1].label_source}</p>
              <p className="text-muted">
                Secondary targets: {Object.entries(data.targets).filter(([, t]) => !t.primary).map(([, t]) => t.name).join(" · ")}.
                Rationale on the <Link href="/preprocessing" className="text-brand underline">preprocessing</Link> page and in docs/METHODOLOGY.md.
              </p>
            </div>
          )}
        </Card>
        <Card title="Model status">
          {activeModels.length === 0 ? (
            <Empty title="No model trained yet">
              Train one on the <Link className="text-brand underline" href="/models">Model Training</Link> page.
            </Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {activeModels.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center justify-between gap-2">
                  <span>
                    {data.targets[m.target]?.name ?? m.target} · Exp. {m.experiment} · {m.model.replaceAll("_", " ")}
                  </span>
                  {m.compatible && m.dataset_matches_current ? <Badge tone="ok">ready</Badge> : <Badge tone="warn">retrain</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Latest experiment results (primary target)" description="Out-of-fold metrics on held-out participants." className="lg:col-span-2">
          {primaryRuns.length === 0 ? (
            <Empty title="No experiments have been run">
              Results appear here only after you run them on the <Link className="text-brand underline" href="/experiments">Research Experiments</Link> page.
            </Empty>
          ) : (
            <Table head={["Experiment", "Model", "Participants", "Windows", "Balanced acc.", "Macro-F1", "Run"]}>
              {primaryRuns.map((r) => (
                <tr key={r.id}>
                  <Td>{r.experiment}</Td>
                  <Td>{r.model.replaceAll("_", " ")}</Td>
                  <Td mono>{r.n_participants}</Td>
                  <Td mono>{r.n_samples}</Td>
                  <Td mono>{fmt(r.metrics.balanced_accuracy)}</Td>
                  <Td mono>{fmt(r.metrics.macro_f1)}</Td>
                  <Td>{r.dataset_matches_current ? <span className="text-xs text-muted">#{r.id}</span> : <Badge tone="warn">old data</Badge>}</Td>
                </tr>
              ))}
            </Table>
          )}
        </Card>
        <Card title="Manipulation check" description="STAI state anxiety after stress minus after relax (eligible participants).">
          {pp?.manipulation_check ? (
            <div className="space-y-2 text-sm">
              <div className="num text-3xl font-semibold">{pp.manipulation_check.mean_difference >= 0 ? "+" : ""}{fmt(pp.manipulation_check.mean_difference, 2)}</div>
              <div className="text-muted">mean difference (SD {fmt(pp.manipulation_check.sd_difference, 2)}), n = {pp.manipulation_check.n}</div>
              <div className="flex flex-wrap gap-2">
                <Badge tone="stress">{pp.manipulation_check.n_higher_after_stress} higher</Badge>
                <Badge>{pp.manipulation_check.n_equal} equal</Badge>
                <Badge tone="relax">{pp.manipulation_check.n_lower_after_stress} lower</Badge>
              </div>
              <p className="text-xs text-muted">Descriptive only. Not a model result.</p>
            </div>
          ) : (
            <Empty title="Not available">Requires the STAI file.</Empty>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card title="Available physiological variables">
          {pp ? (
            <ul className="list-inside list-disc space-y-1 text-sm">{pp.variables.map((v) => <li key={v}>{v}</li>)}</ul>
          ) : (
            <Empty title="No dataset loaded" />
          )}
          <p className="mt-3 text-xs text-muted">{data.dataset.dataset.device_note} No step or activity data is present.</p>
        </Card>
        <Card title="Your imported data" description="Kept separate from the research dataset; never used for training.">
          {data.user_records.total === 0 ? (
            <Empty title="No records yet"><Link href="/import" className="text-brand underline">Add data</Link></Empty>
          ) : (
            <ul className="space-y-1 text-sm">
              {Object.entries(data.user_records.by_source).map(([s, n]) => (
                <li key={s} className="flex justify-between"><span className="capitalize">{s}</span><span className="num">{n}</span></li>
              ))}
              <li className="flex justify-between text-muted"><span>Participant codes</span><span className="num">{data.user_records.participants}</span></li>
            </ul>
          )}
        </Card>
        <Card title="Experiments">
          <ul className="space-y-1.5 text-sm">
            {["A", "B", "C", "D"].map((e) => {
              const items = data.experiments.filter((x) => x.experiment === e);
              const avail = items.filter((x) => x.available).length;
              return (
                <li key={e} className="flex items-center justify-between gap-2">
                  <span>{items[0]?.name}</span>
                  {avail ? <Badge tone="ok">{avail}/{items.length} targets</Badge> : <Badge tone="bad">unavailable</Badge>}
                </li>
              );
            })}
          </ul>
        </Card>
      </div>

      <h2 className="mt-8 mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Modules</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {MODULES.map(({ href, label, icon: Icon, text }) => (
          <Link key={href} href={href} className="group rounded-xl border border-line bg-white p-4 shadow-sm hover:border-brand/40">
            <div className="flex items-center justify-between">
              <Icon className="h-5 w-5 text-brand" aria-hidden />
              <ArrowRight className="h-4 w-4 text-muted transition group-hover:translate-x-0.5" aria-hidden />
            </div>
            <div className="mt-2 font-medium">{label}</div>
            <div className="text-xs text-muted">{text}</div>
          </Link>
        ))}
      </div>
    </>
  );
}
