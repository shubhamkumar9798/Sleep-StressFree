// Thin client for the FastAPI backend. Every error message shown in the UI
// comes from the backend's structured {error, details} responses.

// Note: written with || (not ??) because the Turbopack dev transform panics on `process.env.X ?? y`.
export const API_URL: string = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  details: unknown;
  constructor(message: string, status: number, details?: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let message = `Request failed (${res.status})`;
  let details: unknown;
  try {
    const body = await res.json();
    if (typeof body?.error === "string") message = body.error;
    else if (typeof body?.detail === "string") message = body.detail;
    else if (Array.isArray(body?.detail))
      message = body.detail.map((d: { loc?: string[]; msg: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`).join("; ");
    details = body?.details;
  } catch {
    /* non-JSON error */
  }
  throw new ApiError(message, res.status, details);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(
      `Cannot reach the backend at ${API_URL}. Start it with: cd backend; .venv\\Scripts\\python -m uvicorn app.main:app --port 8000`,
      0,
    );
  }
  return handle<T>(res);
}

export const api = {
  get: <T>(path: string) => request<T>(path, { cache: "no-store" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<T>(path, { method: "POST", body: fd });
  },
};

export type Job = {
  id: string;
  kind: string;
  status: "queued" | "running" | "finished" | "failed";
  progress: number;
  total: number;
  message: string;
  error: string | null;
  result: unknown;
};

export async function waitForJob(id: string, onUpdate?: (j: Job) => void): Promise<Job> {
  for (;;) {
    const job = await api.get<Job>(`/api/jobs/${id}`);
    onUpdate?.(job);
    if (job.status === "finished" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, 700));
  }
}

export const fmt = (v: number | null | undefined, digits = 3) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : Number(v).toFixed(digits);

export const short = (u: string) => (u?.length > 10 ? u.slice(0, 8) : u);
