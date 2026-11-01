"use client";

import { Play } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { RunDetail } from "@/components/RunDetail";
import { Alert, Badge, Button, Card, Empty, Field, inputCls, Loading, PageHeader, Table, Td } from "@/components/ui";
import { api, waitForJob, type Job } from "@/lib/api";
import type { Catalog, Run, TrainedModel } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function ModelsPage() {
  const cat = useApi<Catalog>("/api/experiments/catalog");
  const models = useApi<{ models: TrainedModel[]; interactive_targets: string[] }>("/api/models");
  const [target, setTarget] = useState("phase_window");
  const [experiment, setExperiment] = useState("B");
  const [model, setModel] = useState("logistic_regression");
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);

  const task = cat.data?.targets[target]?.task ?? "classification";
  const options = useMemo(() => cat.data?.catalog.filter((c) => c.target === target) ?? [], [cat.data, target]);
  const modelOptions = cat.data ? Object.entries(cat.data.models[task]) : [];

  useEffect(() => {
    if (!cat.data) return;
    const names = Object.keys(cat.data.models[task]);
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (!names.includes(model)) setModel(names[1] ?? names[0]);
    const exp = options.find((o) => o.experiment === experiment);
    if (exp && !exp.available) setExperiment("A");
  }, [cat.data, task, model, options, experiment]);

  const train = async () => {
    setErr(null); setRun(null);
    try {
      const j = await api.post<Job>("/api/models/train", { target, experiment, model });
      const done = await waitForJob(j.id, setJob);
      if (done.status === "failed") { setErr(done.error); return; }
      const res = done.result as { cv_run_id: number };
      const all = await api.get<{ runs: Run[] }>(`/api/experiments/results?target=${target}`);
      setRun(all.runs.find((r) => r.id === res.cv_run_id) ?? null);
      await models.reload();
    } catch (e) { setErr((e as Error).message); }
  };

  const running = job?.status === "running" || job?.status === "queued";
  const selected = options.find((o) => o.experiment === experiment);

  return (
    <>
      <PageHeader title="Model training and evaluation" subtitle="Each training run first reports participant-wise cross-validated metrics, then fits a final model on all eligible participants for the Stress Estimation page. Training never uses your own imported records." />
      {cat.loading ? <Loading /> : cat.error || !cat.data ? <Alert tone="bad">{cat.error}</Alert> : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card title="Train a model">
            <div className="space-y-4">
              <Field label="Prediction target" htmlFor="target" hint={cat.data.targets[target]?.label_source}>
                <select id="target" className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
                  {Object.entries(cat.data.targets).map(([k, t]) => <option key={k} value={k}>{t.name} ({t.task})</option>)}
                </select>
              </Field>
              <Field label="Experiment (feature set)" htmlFor="exp" hint={selected?.available ? selected.description : undefined}>
                <select id="exp" className={inputCls} value={experiment} onChange={(e) => setExperiment(e.target.value)}>
                  {options.map((o) => <option key={o.experiment} value={o.experiment} disabled={!o.available}>{o.name}{o.available ? "" : " — unavailable"}</option>)}
                </select>
              </Field>
              <Field label="Algorithm" htmlFor="model" hint="Fixed hyper-parameters; the majority/mean baseline shows chance-level performance.">
                <select id="model" className={inputCls} value={model} onChange={(e) => setModel(e.target.value)}>
                  {modelOptions.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
                </select>
              </Field>
              <Button onClick={train} loading={running} disabled={!selected?.available}><Play className="h-4 w-4" />Train &amp; evaluate</Button>
              {running && <p className="text-xs text-muted">{job?.message || "Running…"}</p>}
              {err && <Alert tone="bad" title="Training failed">{err}</Alert>}
              {job?.status === "finished" && <Alert tone="ok">Model saved and activated for this target.</Alert>}
            </div>
          </Card>
          <Card title="Cross-validation result" className="lg:col-span-2">
            {run ? <RunDetail run={run} /> : <Empty title="No run selected">Train a model to see its participant-wise evaluation here. All runs are listed on <Link className="text-brand underline" href="/experiments">Research Experiments</Link>.</Empty>}
          </Card>
        </div>
      )}
      <Card title="Saved models" className="mt-6" description="Each model file stores its feature schema, target definition, training ranges and dataset fingerprint. Incompatible or stale models are flagged and refused at prediction time.">
        {models.loading ? <Loading /> : !models.data?.models.length ? <Empty title="No saved models" /> : (
          <Table dense head={["ID", "Target", "Exp.", "Model", "Features", "Created", "Status"]}>
            {models.data.models.map((m) => (
              <tr key={m.id}>
                <Td mono>{m.id}</Td>
                <Td>{cat.data?.targets[m.target]?.name ?? m.target}</Td>
                <Td>{m.experiment}</Td>
                <Td>{m.model.replaceAll("_", " ")}</Td>
                <Td mono>{m.feature_names.length}</Td>
                <Td mono>{m.created_at.replace("T", " ").slice(0, 16)}</Td>
                <Td>
                  {!m.artifact_exists ? <Badge tone="bad">file missing</Badge> : !m.compatible ? <span title={m.incompatibility ?? ""}><Badge tone="bad">incompatible</Badge></span>
                    : !m.dataset_matches_current ? <Badge tone="warn">other data</Badge> : m.is_active ? <Badge tone="ok">active</Badge> : <Badge>inactive</Badge>}
                </Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
