"use client";

import { Download, Trash2 } from "lucide-react";
import { useState } from "react";
import { Alert, Badge, Button, Card, Empty, Field, inputCls, Loading, Table, Td } from "@/components/ui";
import { api, API_URL } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Rec = {
  id: number; source: string; device_label: string | null; participant_code: string | null; recorded_at: string; metric: string;
  value: number; unit: string; raw_value_text: string | null; value_was_edited: number; verified_device_measurement: number; notes: string | null; batch_id: number;
};

const PAGE = 25;

export function RecordsExplorer() {
  const [source, setSource] = useState("");
  const [metric, setMetric] = useState("");
  const [participant, setParticipant] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [page, setPage] = useState(0);
  const [msg, setMsg] = useState<string | null>(null);
  const qs = new URLSearchParams({ limit: String(PAGE), offset: String(page * PAGE) });
  if (source) qs.set("source", source);
  if (metric) qs.set("metric", metric);
  if (participant) qs.set("participant_code", participant);
  if (start) qs.set("start", start);
  if (end) qs.set("end", end);
  const { data, error, loading, reload } = useApi<{ total: number; rows: Rec[] }>(`/api/records?${qs.toString()}`);
  const exportQs = new URLSearchParams(Array.from(qs.entries()).filter(([k]) => !["limit", "offset", "start", "end"].includes(k)));

  const del = async (r: Rec) => {
    if (!window.confirm(`Delete ${r.metric} = ${r.value} recorded at ${r.recorded_at}? This cannot be undone.`)) return;
    try { await api.del(`/api/records/${r.id}`); setMsg("Record deleted."); await reload(); } catch (e) { setMsg((e as Error).message); }
  };

  return (
    <Card title="Imported records" description="Your own data only (the public dataset is in the Dataset Explorer). Raw text is what was typed, read by OCR or found in the CSV cell."
      actions={<a className="inline-flex items-center gap-2 rounded-lg border border-line bg-white px-3 py-1.5 text-sm hover:bg-slate-50" href={`${API_URL}/api/records/export.csv?${exportQs.toString()}`}><Download className="h-4 w-4" />Export CSV</a>}>
      <div className="mb-4 grid gap-3 md:grid-cols-5">
        <Field label="Source" htmlFor="f-src"><select id="f-src" className={inputCls} value={source} onChange={(e) => { setSource(e.target.value); setPage(0); }}><option value="">All</option><option value="manual">Manual</option><option value="csv">CSV</option><option value="screenshot">Screenshot</option></select></Field>
        <Field label="Metric" htmlFor="f-met"><select id="f-met" className={inputCls} value={metric} onChange={(e) => { setMetric(e.target.value); setPage(0); }}>
          <option value="">All</option>{["heart_rate", "resting_heart_rate", "steps", "sleep_duration", "hrv", "spo2", "body_temperature", "device_stress_score", "self_reported_stress"].map((m) => <option key={m}>{m}</option>)}
        </select></Field>
        <Field label="Participant" htmlFor="f-p"><input id="f-p" className={inputCls} value={participant} onChange={(e) => { setParticipant(e.target.value); setPage(0); }} /></Field>
        <Field label="From" htmlFor="f-s"><input id="f-s" type="datetime-local" className={inputCls} value={start} onChange={(e) => { setStart(e.target.value); setPage(0); }} /></Field>
        <Field label="To" htmlFor="f-e"><input id="f-e" type="datetime-local" className={inputCls} value={end} onChange={(e) => { setEnd(e.target.value); setPage(0); }} /></Field>
      </div>
      {msg && <div className="mb-3"><Alert tone="info">{msg}</Alert></div>}
      {loading ? <Loading /> : error ? <Alert tone="bad">{error}</Alert> : !data?.rows.length ? <Empty title="No records match">Add data with manual entry, CSV import or a screenshot.</Empty> : (
        <>
          <Table dense head={["Recorded at", "Participant", "Metric", "Value", "Source", "Device", "Raw", "Flags", ""]}>
            {data.rows.map((r) => (
              <tr key={r.id}>
                <Td mono>{r.recorded_at.replace("T", " ")}</Td>
                <Td mono>{r.participant_code ?? <span className="text-muted">—</span>}</Td>
                <Td>{r.metric}</Td>
                <Td mono>{r.value} <span className="text-muted">{r.unit}</span></Td>
                <Td><Badge tone={r.source === "screenshot" ? "warn" : r.source === "csv" ? "brand" : "neutral"}>{r.source}</Badge></Td>
                <Td className="max-w-40 truncate">{r.device_label ?? "—"}</Td>
                <Td className="max-w-40 truncate" mono>{r.raw_value_text}</Td>
                <Td>{r.value_was_edited ? <Badge tone="warn">corrected</Badge> : null}{!r.verified_device_measurement && <Badge>unverified</Badge>}</Td>
                <Td><Button variant="ghost" aria-label="Delete record" onClick={() => del(r)}><Trash2 className="h-4 w-4" /></Button></Td>
              </tr>
            ))}
          </Table>
          <div className="mt-3 flex items-center justify-between text-sm text-muted">
            <span>{data.total} records · page {page + 1} of {Math.max(1, Math.ceil(data.total / PAGE))}</span>
            <div className="flex gap-2">
              <Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
              <Button variant="secondary" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}
