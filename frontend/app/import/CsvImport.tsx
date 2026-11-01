"use client";

import { useState } from "react";
import { Alert, Badge, Button, Card, Field, inputCls, Table, Td } from "@/components/ui";
import { api } from "@/lib/api";

type Mapping = {
  timestamp_column: string | null;
  participant_column: string | null;
  metrics: Record<string, string>;
  units: Record<string, string>;
  default_participant_code?: string;
  device_label?: string;
  timestamp_format?: string;
  dayfirst?: boolean;
};
type PreviewRes = {
  token: string; filename: string; n_rows: number; columns: string[]; rows: Record<string, string>[];
  suggested_mapping: Mapping; warnings: string[];
  metrics: Record<string, { label: string; unit: string }>;
  unit_options: Record<string, string[]>;
};
type Report = {
  n_rows: number; invalid_timestamps: number; invalid_timestamp_rows: number[];
  metrics: Record<string, { metric: string; unit: string; converted_from?: string; n_values: number; n_missing: number; n_non_numeric: number; n_out_of_range: number; n_valid: number; example_problems: { row: number; value: string }[] }>;
  duplicate_rows_in_file: number; duplicate_measurements_in_file: number; duplicates_already_in_database: number; n_records_to_import: number; note: string;
  imported?: number;
};

export function CsvImport() {
  const [pv, setPv] = useState<PreviewRes | null>(null);
  const [map, setMap] = useState<Mapping | null>(null);
  const [rep, setRep] = useState<Report | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async (f: File | undefined) => {
    if (!f) return;
    setErr(null); setRep(null); setDone(null); setBusy(true);
    try {
      const r = await api.upload<PreviewRes>("/api/imports/csv/preview", f);
      setPv(r);
      setMap({ ...r.suggested_mapping, device_label: "" });
    } catch (e) { setErr((e as Error).message); setPv(null); } finally { setBusy(false); }
  };
  const validate = async () => {
    setErr(null); setBusy(true);
    try { setRep(await api.post<Report>("/api/imports/csv/validate", { token: pv!.token, mapping: map })); }
    catch (e) { setErr((e as Error).message); setRep(null); } finally { setBusy(false); }
  };
  const commit = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await api.post<Report>("/api/imports/csv/commit", { token: pv!.token, mapping: map });
      setDone(`Imported ${r.imported} records from ${pv!.filename} with source “csv”.`);
      setPv(null); setMap(null); setRep(null);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const discard = async () => {
    if (pv) await api.del(`/api/imports/csv/${pv.token}`).catch(() => undefined);
    setPv(null); setMap(null); setRep(null);
  };
  const setMetric = (col: string, metric: string) => {
    const metrics = { ...map!.metrics };
    if (metric) metrics[col] = metric; else delete metrics[col];
    setMap({ ...map!, metrics }); setRep(null);
  };

  return (
    <div className="space-y-6">
      <Card title="1. Upload CSV" description="Any column layout is accepted; you map the columns in the next step. Max 20 MB.">
        <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={(e) => upload(e.target.files?.[0])} className="block text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand file:px-3 file:py-2 file:text-sm file:font-medium file:text-white" />
        {done && <div className="mt-4"><Alert tone="ok">{done}</Alert></div>}
        {err && <div className="mt-4"><Alert tone="bad">{err}</Alert></div>}
      </Card>
      {pv && map && (
        <>
          <Card title={`2. Preview: ${pv.filename}`} description={`${pv.n_rows} rows · first ${pv.rows.length} shown`}>
            <Table dense head={pv.columns}>
              {pv.rows.map((r, i) => <tr key={i}>{pv.columns.map((c) => <Td key={c} mono>{r[c] === "" ? <span className="text-bad">∅</span> : r[c]}</Td>)}</tr>)}
            </Table>
            {pv.warnings.map((w) => <div className="mt-3" key={w}><Alert tone="warn">{w}</Alert></div>)}
          </Card>
          <Card title="3. Column mapping" description="Suggested from column names; check and edit. Unmapped columns are ignored.">
            <div className="grid gap-4 md:grid-cols-3">
              <Field label="Timestamp column" htmlFor="c-ts">
                <select id="c-ts" className={inputCls} value={map.timestamp_column ?? ""} onChange={(e) => { setMap({ ...map, timestamp_column: e.target.value || null }); setRep(null); }}>
                  <option value="">— select —</option>{pv.columns.map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Timestamp format (optional)" htmlFor="c-fmt" hint="strftime, e.g. %d/%m/%Y %H:%M. Leave empty to auto-detect.">
                <input id="c-fmt" className={inputCls} value={map.timestamp_format ?? ""} onChange={(e) => { setMap({ ...map, timestamp_format: e.target.value }); setRep(null); }} />
              </Field>
              <label className="flex items-end gap-2 pb-2 text-sm"><input type="checkbox" checked={!!map.dayfirst} onChange={(e) => { setMap({ ...map, dayfirst: e.target.checked }); setRep(null); }} />Dates are day-first (DD/MM)</label>
              <Field label="Participant column" htmlFor="c-p">
                <select id="c-p" className={inputCls} value={map.participant_column ?? ""} onChange={(e) => { setMap({ ...map, participant_column: e.target.value || null }); setRep(null); }}>
                  <option value="">— none —</option>{pv.columns.map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              {!map.participant_column && (
                <Field label="Participant code for all rows" htmlFor="c-dp"><input id="c-dp" className={inputCls} value={map.default_participant_code ?? ""} onChange={(e) => { setMap({ ...map, default_participant_code: e.target.value }); setRep(null); }} /></Field>
              )}
              <Field label="Device label" htmlFor="c-dev" hint="e.g. Amazfit (model unconfirmed) – stored as provided"><input id="c-dev" className={inputCls} value={map.device_label ?? ""} onChange={(e) => setMap({ ...map, device_label: e.target.value })} /></Field>
            </div>
            <div className="mt-5">
              <Table dense head={["Column", "Measurement type", "Unit"]}>
                {pv.columns.filter((c) => c !== map.timestamp_column && c !== map.participant_column).map((c) => {
                  const m = map.metrics[c];
                  return (
                    <tr key={c}>
                      <Td mono>{c}</Td>
                      <Td>
                        <select aria-label={`Measurement for ${c}`} className={inputCls} value={m ?? ""} onChange={(e) => setMetric(c, e.target.value)}>
                          <option value="">— ignore —</option>
                          {Object.entries(pv.metrics).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                        </select>
                      </Td>
                      <Td>
                        {m && pv.unit_options[m] ? (
                          <select aria-label={`Unit for ${c}`} className={inputCls} value={map.units[c] ?? pv.unit_options[m][0]} onChange={(e) => { setMap({ ...map, units: { ...map.units, [c]: e.target.value } }); setRep(null); }}>
                            {pv.unit_options[m].map((u) => <option key={u}>{u}</option>)}
                          </select>
                        ) : m ? <span className="text-xs text-muted">{pv.metrics[m].unit}</span> : null}
                      </Td>
                    </tr>
                  );
                })}
              </Table>
            </div>
            <div className="mt-4 flex gap-2">
              <Button onClick={validate} loading={busy}>Validate</Button>
              <Button variant="ghost" onClick={discard}>Discard upload</Button>
            </div>
          </Card>
        </>
      )}
      {rep && (
        <Card title="4. Validation report" description={rep.note}>
          <div className="grid gap-3 text-sm sm:grid-cols-4">
            <div>Rows: <b className="num">{rep.n_rows}</b></div>
            <div>Invalid timestamps: <b className={rep.invalid_timestamps ? "text-bad" : ""}>{rep.invalid_timestamps}</b>{rep.invalid_timestamp_rows.length > 0 && <span className="text-xs text-muted"> (rows {rep.invalid_timestamp_rows.join(", ")})</span>}</div>
            <div>Duplicates in file: <b>{rep.duplicate_measurements_in_file}</b></div>
            <div>Already in database: <b>{rep.duplicates_already_in_database}</b></div>
          </div>
          <div className="mt-4">
            <Table dense head={["Column", "Type", "Values", "Missing", "Non-numeric", "Out of range", "Valid", "Problems"]}>
              {Object.entries(rep.metrics).map(([c, m]) => (
                <tr key={c}>
                  <Td mono>{c}</Td><Td>{m.metric}{m.converted_from && <Badge tone="brand">from {m.converted_from}</Badge>}</Td>
                  <Td mono>{m.n_values}</Td><Td mono>{m.n_missing}</Td><Td mono>{m.n_non_numeric}</Td><Td mono>{m.n_out_of_range}</Td><Td mono>{m.n_valid}</Td>
                  <Td className="whitespace-normal text-xs">{m.example_problems.map((p) => `row ${p.row}: “${p.value}”`).join(", ")}</Td>
                </tr>
              ))}
            </Table>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button onClick={commit} loading={busy} disabled={!rep.n_records_to_import}>Confirm import of {rep.n_records_to_import} records</Button>
            <span className="text-xs text-muted">Invalid, missing and duplicate values are skipped. No stress label is created.</span>
          </div>
        </Card>
      )}
    </div>
  );
}
