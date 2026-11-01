"use client";

import { useState } from "react";
import { Alert, Badge, Button, Card, Field, inputCls, Loading, PageHeader, Table, Td } from "@/components/ui";
import { api, API_URL } from "@/lib/api";
import type { DatasetStatus } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type MetricSpec = { label: string; unit: string; min: number; max: number; note?: string };

export default function SettingsPage() {
  const status = useApi<DatasetStatus>("/api/dataset/status");
  const ocr = useApi<{ available: boolean; version?: string; message?: string; store_screenshots: boolean }>("/api/imports/screenshot/status");
  const metrics = useApi<{ metrics: Record<string, MetricSpec> }>("/api/records/metrics");
  const [dir, setDir] = useState("");
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);

  const apply = async (path: string | null) => {
    setMsg(null);
    try {
      const s = await api.post<DatasetStatus>("/api/dataset/directory", { path });
      setMsg({ tone: s.available ? "ok" : "bad", text: s.available ? `Using ${s.dataset.directory}` : `No dataset files found in ${s.dataset.directory}` });
      await status.reload();
    } catch (e) { setMsg({ tone: "bad", text: (e as Error).message }); }
  };

  return (
    <>
      <PageHeader title="Settings & documentation" subtitle="Dataset location, attribution, OCR status, privacy notice and the data dictionary for user-entered records." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Dataset location">
          {status.loading ? <Loading /> : status.error ? <Alert tone="bad">{status.error}</Alert> : status.data && (
            <div className="space-y-3 text-sm">
              <div>Current folder: <code className="break-all text-xs">{status.data.dataset.directory}</code></div>
              <div>{status.data.available ? <Badge tone="ok">{status.data.files.filter((f) => f.present).length}/{status.data.files.length} files found</Badge> : <Badge tone="bad">not found</Badge>}</div>
              <Field label="Use another folder for this session" htmlFor="dir" hint="Absolute path to the folder that contains the CSV files. For a permanent change set QOL_STRESS_DIR in backend/.env.">
                <input id="dir" className={inputCls} value={dir} onChange={(e) => setDir(e.target.value)} placeholder="C:\\…\\qol_stress\\data" />
              </Field>
              <div className="flex gap-2">
                <Button onClick={() => apply(dir)} disabled={!dir}>Apply</Button>
                <Button variant="secondary" onClick={() => apply(null)}>Reset to default</Button>
              </div>
              {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}
            </div>
          )}
        </Card>
        <Card title="Getting the QoL_Stress dataset">
          <ol className="list-inside list-decimal space-y-1.5 text-sm">
            <li>Open <a className="text-brand underline" href="https://physionet.org/content/qol-stress/1.0.0/" target="_blank" rel="noreferrer">physionet.org/content/qol-stress/1.0.0</a> and download the ZIP (open access, CC BY 4.0).</li>
            <li>Extract it next to the <code>backend</code> and <code>frontend</code> folders, or copy the CSV files into <code>data/qol_stress/</code>.</li>
            <li>Restart the backend or click “Reset to default”. Original files are only read, never changed.</li>
          </ol>
          {status.data && (
            <div className="mt-4 space-y-1 text-xs text-muted">
              <div><b>Attribution:</b> {status.data.dataset.authors}. “{status.data.dataset.name}”, version {status.data.dataset.version}, PhysioNet.</div>
              <div><b>License:</b> {status.data.dataset.license}. Cite the dataset and PhysioNet (see README) in any report.</div>
              <div>{status.data.dataset.device_note}</div>
            </div>
          )}
        </Card>
        <Card title="Screenshot OCR">
          {ocr.data?.available ? <Alert tone="ok">Tesseract {ocr.data.version} is available.</Alert> : <Alert tone="warn" title="Tesseract not available">{ocr.data?.message}</Alert>}
          <p className="mt-3 text-sm">Screenshot files are {ocr.data?.store_screenshots ? <b>stored</b> : <b>not stored</b>} after confirmation (only file name and SHA-256 hash are kept unless <code>STORE_SCREENSHOTS=true</code> in backend/.env).</p>
        </Card>
        <Card title="Documentation">
          <ul className="space-y-1.5 text-sm">
            <li><code>README.md</code> – setup, API, troubleshooting</li>
            <li><code>docs/METHODOLOGY.md</code> – research methodology, target justification, limitations</li>
            <li><code>docs/DATA_DICTIONARY.md</code> – every field, unit and source</li>
            <li><a className="text-brand underline" href={`${API_URL}/docs`} target="_blank" rel="noreferrer">Interactive API documentation</a> (FastAPI / OpenAPI)</li>
          </ul>
        </Card>
      </div>

      <Card title="Privacy and consent notice (research prototype)" className="mt-6">
        <div className="space-y-2 text-sm">
          <p>This tool runs locally on the researcher&apos;s computer. No data is sent to external services; there is no user authentication, so do not expose the server to a network.</p>
          <p>Before entering data from any person, obtain informed consent under your institution&apos;s approved ethics procedure. Explain the purpose, what is recorded, that participation is voluntary, and how to withdraw.</p>
          <p>Use pseudonymous participant codes only. Names, e-mail addresses and contact details must not be entered. The code-to-identity key, if one exists, must be kept separately according to the approved data-management plan.</p>
          <p>Withdrawal: delete a participant&apos;s records in Data Import → Imported records (filter by participant code, then delete), or delete a whole import batch through the API (<code>DELETE /api/batches/&#123;id&#125;</code>).</p>
          <p>Outputs are experimental research estimates, not medical advice or diagnosis.</p>
        </div>
      </Card>

      <Card title="Data dictionary: user-entered measurements" className="mt-6" description="Every record also stores source (manual/csv/screenshot), device label, participant code, timestamp, raw text and whether the value was corrected.">
        {metrics.data && (
          <Table dense head={["Field", "Meaning", "Unit", "Valid range", "Note"]}>
            {Object.entries(metrics.data.metrics).map(([k, m]) => (
              <tr key={k}><Td mono>{k}</Td><Td>{m.label}</Td><Td>{m.unit}</Td><Td mono>{m.min}–{m.max}</Td><Td className="whitespace-normal text-xs">{m.note}</Td></tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
