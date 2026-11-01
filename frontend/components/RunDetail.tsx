"use client";

import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Table, Td } from "@/components/ui";
import { fmt } from "@/lib/api";
import { METRIC_LABELS, type Run } from "@/lib/types";

export function ConfusionMatrix({ cm, labels }: { cm: number[][]; labels: string[] }) {
  const max = Math.max(...cm.flat(), 1);
  return (
    <div className="inline-block">
      <div className="mb-1 text-center text-xs text-muted">Predicted</div>
      <div className="flex items-center gap-2">
        <div className="text-xs text-muted [writing-mode:vertical-rl] rotate-180">Actual</div>
        <table className="border-separate border-spacing-1 text-sm">
          <thead>
            <tr><th />{labels.map((l) => <th key={l} className="px-2 text-xs font-medium text-muted">{l}</th>)}</tr>
          </thead>
          <tbody>
            {cm.map((row, i) => (
              <tr key={i}>
                <th className="pr-2 text-right text-xs font-medium text-muted">{labels[i]}</th>
                {row.map((v, j) => (
                  <td
                    key={j}
                    className="num h-14 w-20 rounded-md text-center font-semibold"
                    style={{ background: `rgba(63,81,181,${0.08 + 0.6 * (v / max)})`, color: v / max > 0.6 ? "white" : "#0f172a" }}
                  >
                    {v}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function RunDetail({ run }: { run: Run }) {
  const d = run.details;
  const isClf = !!d?.confusion_matrix;
  const metricKeys = isClf ? ["balanced_accuracy", "macro_f1", "precision_macro", "recall_macro", "roc_auc"] : ["mae", "rmse", "r2", "pearson_r"];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2 text-xs">
        <Badge tone="brand">Experiment {run.experiment}</Badge>
        <Badge>{run.model.replaceAll("_", " ")}</Badge>
        <Badge>{run.n_participants} participants</Badge>
        <Badge>{run.n_samples} samples</Badge>
        {!run.dataset_matches_current && <Badge tone="warn">computed on different dataset files</Badge>}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {metricKeys.map((k) => (
          <div key={k} className="rounded-lg border border-line p-3">
            <div className="text-xs text-muted">{METRIC_LABELS[k]}</div>
            <div className="num text-lg font-semibold">{fmt(run.metrics[k] as number | null)}</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted">
        {run.config?.validation}. Hyper-parameters: {run.config?.hyperparameter_tuning}.
        {isClf
          ? ` Per-fold balanced accuracy ${fmt(run.metrics.fold_balanced_accuracy_mean)} ± ${fmt(run.metrics.fold_balanced_accuracy_sd)}.`
          : ` Per-fold MAE ${fmt(run.metrics.fold_mae_mean)} ± ${fmt(run.metrics.fold_mae_sd)}; target mean ${fmt(run.metrics.target_mean, 1)}, SD ${fmt(run.metrics.target_sd, 1)}.`}
      </p>
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          {isClf && d?.confusion_matrix ? (
            <ConfusionMatrix cm={d.confusion_matrix} labels={d.class_labels ?? []} />
          ) : d?.points ? (
            <div className="h-64">
              <ResponsiveContainer>
                <ScatterChart margin={{ left: 0, right: 12 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="actual" type="number" name="actual" domain={["dataMin - 2", "dataMax + 2"]} tick={{ fontSize: 11 }} label={{ value: "actual", position: "insideBottom", offset: -2, fontSize: 11 }} />
                  <YAxis dataKey="predicted" type="number" name="predicted" domain={["dataMin - 2", "dataMax + 2"]} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmt(Number(v), 1)} />
                  <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 80, y: 80 }]} stroke="#94a3b8" strokeDasharray="4 4" ifOverflow="hidden" />
                  <Scatter data={d.points} fill="#3f51b5" fillOpacity={0.6} />
                </ScatterChart>
              </ResponsiveContainer>
              <p className="text-xs text-muted">Out-of-fold predicted vs. actual (dashed: perfect prediction).</p>
            </div>
          ) : null}
        </div>
        <div className="space-y-3">
          {d?.classification_report && (
            <Table dense head={["Class", "Precision", "Recall", "F1", "Support"]}>
              {(d.class_labels ?? []).map((c) => {
                const r = d.classification_report![c] as Record<string, number>;
                return <tr key={c}><Td>{c}</Td><Td mono>{fmt(r.precision)}</Td><Td mono>{fmt(r.recall)}</Td><Td mono>{fmt(r["f1-score"])}</Td><Td mono>{r.support}</Td></tr>;
              })}
            </Table>
          )}
          {d?.folds && (
            <Table dense head={["Fold", "Train (pt / n)", "Test (pt / n)", "Overlap", isClf ? "Bal. acc." : "MAE"]}>
              {d.folds.map((f) => (
                <tr key={f.fold}>
                  <Td mono>{f.fold + 1}</Td>
                  <Td mono>{f.n_train_participants} / {f.n_train}</Td>
                  <Td mono>{f.n_test_participants} / {f.n_test}</Td>
                  <Td mono>{f.participant_overlap}</Td>
                  <Td mono>{fmt(isClf ? f.balanced_accuracy : f.mae)}</Td>
                </tr>
              ))}
            </Table>
          )}
          {!!d?.n_missing_feature_values_imputed && (
            <p className="text-xs text-warn">{d.n_missing_feature_values_imputed} missing feature values were median-imputed inside each training fold ({Object.entries(d.missing_by_feature ?? {}).map(([k, v]) => `${k}: ${v}`).join(", ")}).</p>
          )}
        </div>
      </div>
      <div className="text-xs text-muted">Features: <span className="font-mono">{run.config?.features?.join(", ")}</span></div>
    </div>
  );
}
