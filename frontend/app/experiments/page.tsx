"use client";

import { Download, Play } from "lucide-react";
import { useState } from "react";
import { RunDetail } from "@/components/RunDetail";
import { Alert, Badge, Button, Card, Empty, Loading, PageHeader, Table, Td } from "@/components/ui";
import { api, API_URL, fmt, waitForJob, type Job } from "@/lib/api";
import { type Catalog, type Comparison, METRIC_LABELS, type Run } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LIMITATIONS = [
  "Labels are the protocol phases (relax vs. induced stress), not momentary self-reported stress. A model can only learn what differs between these two lab conditions.",
  "The stress phase always followed the relax phase, so time-on-task, posture and questionnaire effects are confounded with the condition.",
  "Phase boundaries are reconstructed from questionnaire timestamps (documented assumption); exact task start/end times are not in the files.",
  "A small sample of adults from one study (participant counts are shown per target above); not a student-only sample and not representative of everyday life.",
  "Fitbit optical heart rate only. Results do not transfer to Amazfit devices without new validation.",
  "Wilcoxon tests are exploratory and uncorrected for multiple comparisons. A non-significant difference is not evidence of equivalence.",
];

export default function ExperimentsPage() {
  const cat = useApi<Catalog>("/api/experiments/catalog");
  const res = useApi<{ runs: Run[]; comparisons: Comparison[] }>("/api/experiments/results");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<Run | null>(null);
  const [targets, setTargets] = useState<string[]>(["phase_window", "phase_segment", "stai_state", "pss14"]);

  const runAll = async () => {
    setErr(null);
    try {
      const j = await api.post<Job>("/api/experiments/run", { targets });
      const done = await waitForJob(j.id, setJob);
      if (done.status === "failed") setErr(done.error);
      await res.reload();
    } catch (e) { setErr((e as Error).message); }
  };
  const running = job?.status === "running" || job?.status === "queued";

  return (
    <>
      <PageHeader
        title="Research experiments"
        subtitle="General (A) vs. personalised baseline (B) vs. additional physiology (C). All experiments of a target use the same participants and the same participant-wise folds, so comparisons are paired."
        actions={<a href={`${API_URL}/api/experiments/results.csv`} className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3.5 py-2 text-sm font-medium hover:bg-slate-50"><Download className="h-4 w-4" />Download CSV summary</a>}
      />
      <Card title="Run experiments" description="Runs every available experiment × algorithm for the selected targets and stores the configuration and results for reproducibility.">
        <div className="flex flex-wrap items-center gap-4">
          {cat.data && Object.entries(cat.data.targets).map(([k, t]) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={targets.includes(k)} onChange={(e) => setTargets(e.target.checked ? [...targets, k] : targets.filter((x) => x !== k))} />
              {t.name}
            </label>
          ))}
          <Button onClick={runAll} loading={running} disabled={!targets.length}><Play className="h-4 w-4" />Run</Button>
        </div>
        {running && job && <div className="mt-3 text-sm text-muted">Running {job.progress}/{job.total}: {job.message}</div>}
        {err && <div className="mt-3"><Alert tone="bad" title="Experiment run failed">{err}</Alert></div>}
      </Card>

      {res.loading || cat.loading ? <Loading /> : res.error ? <div className="mt-6"><Alert tone="bad">{res.error}</Alert></div> : !res.data?.runs.length ? (
        <div className="mt-6"><Empty title="No experiment results yet">Nothing is shown until experiments have actually been run on the dataset.</Empty></div>
      ) : cat.data && Object.entries(cat.data.targets).map(([t, tdef]) => {
        const runs = res.data!.runs.filter((r) => r.target === t);
        const cmps = res.data!.comparisons.filter((c) => c.target === t);
        const unavailable = cat.data!.catalog.filter((c) => c.target === t && !c.available);
        if (!runs.length) return null;
        const clf = tdef.task === "classification";
        const keys = clf ? ["balanced_accuracy", "macro_f1", "roc_auc"] : ["mae", "rmse", "r2"];
        const ref = runs[0];
        return (
          <Card key={t} className="mt-6" title={<span className="flex flex-wrap items-center gap-2">{tdef.name} <Badge>{tdef.task}</Badge>{tdef.primary && <Badge tone="brand">primary</Badge>}</span>}
            description={`${tdef.label_source} Unit: ${tdef.unit}. ${ref.n_participants} participants, ${ref.n_samples} samples, ${ref.config?.k_folds}-fold participant-wise CV.`}>
            <Table dense head={["Experiment", "Model", ...keys.map((k) => METRIC_LABELS[k]), "Features", ""]}>
              {runs.sort((a, b) => a.experiment.localeCompare(b.experiment) || a.model.localeCompare(b.model)).map((r) => (
                <tr key={r.id} className={selected?.id === r.id ? "bg-brand-soft/50" : undefined}>
                  <Td>{cat.data!.experiments[r.experiment]?.name}</Td>
                  <Td>{r.model.replaceAll("_", " ")}</Td>
                  {keys.map((k) => <Td key={k} mono>{fmt(r.metrics[k])}</Td>)}
                  <Td mono>{r.config?.features?.length}</Td>
                  <Td><button className="text-brand hover:underline" onClick={() => setSelected(r)}>details</button>{!r.dataset_matches_current && <Badge tone="warn">old data</Badge>}</Td>
                </tr>
              ))}
            </Table>
            {cmps.length > 0 && (
              <div className="mt-4">
                <h3 className="mb-2 text-sm font-medium">Paired comparison against Experiment A (per-participant, Wilcoxon signed-rank)</h3>
                <Table dense head={["Model", "Comparison", "Beats trivial baseline", "Mean Δ", "p", "Interpretation"]}>
                  {cmps.filter((c) => c.model !== "dummy").map((c) => (
                    <tr key={c.model + c.experiment}>
                      <Td>{c.model.replaceAll("_", " ")}</Td>
                      <Td>{c.experiment} vs A</Td>
                      <Td>{c.beats_trivial_baseline === null ? "—" : c.beats_trivial_baseline ? <Badge tone="ok">yes</Badge> : <Badge tone="bad">no</Badge>}</Td>
                      <Td mono>{c.test ? `${c.test.mean_difference >= 0 ? "+" : ""}${fmt(c.test.mean_difference)}` : "—"}</Td>
                      <Td mono>{c.test ? fmt(c.test.p_value) : "—"}</Td>
                      <Td className="whitespace-normal text-xs">{c.interpretation}</Td>
                    </tr>
                  ))}
                </Table>
                <p className="mt-1 text-xs text-muted">Δ in per-participant {cmps[0]?.test?.metric}; {clf ? "positive = higher (better)" : "negative = lower error (better)"}.</p>
              </div>
            )}
            {unavailable.length > 0 && (
              <div className="mt-4 space-y-2">
                {unavailable.map((u) => <Alert key={u.experiment} tone="info" title={`${u.name}: not run`}>{u.reason}</Alert>)}
              </div>
            )}
            {selected && selected.target === t && <div className="mt-6 border-t border-line pt-5"><RunDetail run={selected} /></div>}
          </Card>
        );
      })}

      <Card title="Limitations" className="mt-6">
        <ul className="list-inside list-disc space-y-1 text-sm">{LIMITATIONS.map((l) => <li key={l}>{l}</li>)}</ul>
        <p className="mt-3 text-sm text-muted">Conclusions about personalisation should be drawn only from the paired comparisons above and only for this dataset and protocol.</p>
      </Card>
    </>
  );
}
