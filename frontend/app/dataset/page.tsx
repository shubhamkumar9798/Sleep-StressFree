"use client";

import { FileWarning } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, Badge, Card, Empty, Loading, PageHeader, Table, Td } from "@/components/ui";
import type { DatasetStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Validation = {
  file: string;
  present: boolean;
  issues: string[];
  warnings: string[];
  sha256?: string;
  n_rows?: number;
  n_participants?: number;
  n_duplicate_rows?: number;
  n_duplicate_keys?: number;
  duplicate_key_columns?: string[];
  columns?: { name: string; dtype: string; n_missing: number; n_unique: number; required: boolean }[];
  timestamps?: Record<string, { n_invalid: number; n_non_standard_format: number }>;
  value_summary?: Record<string, number>;
  extra_columns?: number;
};
type Preview = { columns: string[]; rows: Record<string, unknown>[] };

const fmtBytes = (b: number | null) => (b == null ? "—" : b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(1)} kB`);

export default function DatasetPage() {
  const status = useApi<DatasetStatus>("/api/dataset/status");
  const [file, setFile] = useState("fitbit_heart_rate_per_second.csv");
  const present = status.data?.files.find((f) => f.file === file)?.present;
  const val = useApi<Validation>(status.data?.available ? `/api/dataset/files/${file}/validate` : null);
  const prev = useApi<Preview>(present ? `/api/dataset/files/${file}/preview?n=8` : null);
  const dist = useApi<{ bins: { bin: string; relax: number; stress: number }[] }>(status.data?.available ? "/api/dataset/hr-distribution" : null);

  if (status.loading) return <Loading />;
  if (status.error || !status.data) return <Alert tone="bad" title="Backend unavailable">{status.error}</Alert>;
  const s = status.data;

  return (
    <>
      <PageHeader
        title="Dataset explorer"
        subtitle={<>{s.dataset.name}, v{s.dataset.version}. Files are read directly from <code className="text-xs">{s.dataset.directory}</code> and never modified.</>}
      />
      {!s.available && (
        <div className="mb-6">
          <Alert tone="warn" title="Dataset not installed">{s.setup_message} See <Link className="underline" href="/settings">Settings</Link>.</Alert>
        </div>
      )}
      <Card title="Files" description={s.fingerprint ? `Pipeline input fingerprint: ${s.fingerprint}` : undefined}>
        <Table head={["File", "Status", "Size", "Used by pipeline", "Role"]}>
          {s.files.map((f) => (
            <tr key={f.file} className={f.file === file ? "bg-brand-soft/40" : undefined}>
              <Td>
                <button className="font-medium text-brand hover:underline" onClick={() => setFile(f.file)}>{f.file}</button>
                <div className="max-w-sm whitespace-normal text-xs text-muted">{f.description}</div>
              </Td>
              <Td>{f.present ? <Badge tone="ok">present</Badge> : <Badge tone="bad">missing</Badge>}</Td>
              <Td mono>{fmtBytes(f.size_bytes)}</Td>
              <Td>{f.used_by_pipeline ? "yes" : "no"}</Td>
              <Td className="max-w-md whitespace-normal text-xs text-muted">{f.role}</Td>
            </tr>
          ))}
        </Table>
      </Card>

      <div className="mt-6 grid gap-6 xl:grid-cols-5">
        <Card title={`Validation: ${file}`} className="xl:col-span-2">
          {val.loading ? <Loading /> : val.error ? <Alert tone="bad">{val.error}</Alert> : !val.data ? <Empty title="No dataset" /> : (
            <div className="space-y-3 text-sm">
              {val.data.issues.map((i) => <Alert key={i} tone="bad">{i}</Alert>)}
              {val.data.present && val.data.n_rows !== undefined && (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
                  <dt className="text-muted">Rows</dt><dd className="num">{val.data.n_rows.toLocaleString()}</dd>
                  <dt className="text-muted">Participants</dt><dd className="num">{val.data.n_participants ?? "—"}</dd>
                  <dt className="text-muted">Duplicate rows</dt><dd className="num">{val.data.n_duplicate_rows}</dd>
                  {val.data.duplicate_key_columns && (<><dt className="text-muted">Duplicate keys ({val.data.duplicate_key_columns.join(", ")})</dt><dd className="num">{val.data.n_duplicate_keys}</dd></>)}
                  {val.data.timestamps && Object.entries(val.data.timestamps).map(([c, t]) => (
                    <div key={c} className="contents"><dt className="text-muted">Invalid “{c}”</dt><dd className="num">{t.n_invalid} (non-standard: {t.n_non_standard_format})</dd></div>
                  ))}
                  <dt className="text-muted">SHA-256</dt><dd className="truncate font-mono text-xs" title={val.data.sha256}>{val.data.sha256?.slice(0, 16)}…</dd>
                </dl>
              )}
              {val.data.warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
            </div>
          )}
        </Card>
        <Card title="Columns, types and missing values" className="xl:col-span-3">
          {val.data?.columns ? (
            <Table dense head={["Column", "Type", "Missing", "Unique", "Required"]}>
              {val.data.columns.map((c) => (
                <tr key={c.name}>
                  <Td className="max-w-xs truncate" ><span title={c.name}>{c.name.length > 60 ? c.name.slice(0, 57) + "…" : c.name}</span></Td>
                  <Td mono>{c.dtype}</Td>
                  <Td mono>{c.n_missing ? <span className="text-bad">{c.n_missing}</span> : 0}</Td>
                  <Td mono>{c.n_unique}</Td>
                  <Td>{c.required ? <Badge tone="brand">required</Badge> : ""}</Td>
                </tr>
              ))}
            </Table>
          ) : (
            <Empty title="No schema to show" icon={<FileWarning className="h-6 w-6" />} />
          )}
        </Card>
      </div>

      <Card title="Sample rows" className="mt-6" description="Participant IDs are pseudonymous hashes supplied by the dataset authors. Long values are truncated.">
        {prev.loading ? <Loading /> : prev.error ? <Alert tone="bad">{prev.error}</Alert> : prev.data ? (
          <Table dense head={prev.data.columns.map((c) => (c.length > 28 ? c.slice(0, 26) + "…" : c))}>
            {prev.data.rows.map((r, i) => (
              <tr key={i}>
                {prev.data!.columns.map((c) => {
                  const v = r[c];
                  const t = v === null ? "∅" : String(v);
                  return <Td key={c} mono>{c === "username" ? t.slice(0, 8) + "…" : t}</Td>;
                })}
              </tr>
            ))}
          </Table>
        ) : <Empty title="File not present" />}
      </Card>

      <Card title="Window mean heart rate by reconstructed phase" className="mt-6" description="Counts of 60-s windows (eligible participants, calibration minutes excluded). Real QoL_Stress data.">
        {dist.data && dist.data.bins.length ? (
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={dist.data.bins} margin={{ left: 0, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="bin" tick={{ fontSize: 11 }} label={{ value: "bpm", position: "insideBottomRight", offset: -4, fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="relax" fill="#0e9f8e" name="Relax" />
                <Bar dataKey="stress" fill="#e0662b" name="Stress" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : dist.error ? <Alert tone="bad">{dist.error}</Alert> : <Empty title="No data to chart" />}
      </Card>
    </>
  );
}
