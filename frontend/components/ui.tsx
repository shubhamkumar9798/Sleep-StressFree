// Small shadcn-style UI primitives (hand-written so no CLI or extra packages are needed).
import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, Loader2, XCircle } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ title, description, children, className, actions }: {
  title?: ReactNode; description?: ReactNode; children?: ReactNode; className?: string; actions?: ReactNode;
}) {
  return (
    <section className={clsx("rounded-xl border border-line bg-panel p-5 shadow-sm", className)}>
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title && <h2 className="text-base font-semibold">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "ok" | "warn" | "bad" }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4 shadow-sm">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{label}</div>
      <div className={clsx("num mt-1 text-2xl font-semibold", tone === "ok" && "text-ok", tone === "warn" && "text-warn", tone === "bad" && "text-bad")}>
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

type Variant = "primary" | "secondary" | "danger" | "ghost";
export function Button({ variant = "primary", loading, className, children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-brand text-white hover:bg-brand/90",
        variant === "secondary" && "border border-line bg-white text-ink hover:bg-slate-50",
        variant === "danger" && "bg-bad text-white hover:bg-bad/90",
        variant === "ghost" && "text-muted hover:bg-slate-100 hover:text-ink",
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "warn" | "bad" | "brand" | "relax" | "stress" }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-slate-100 text-slate-700",
        tone === "ok" && "bg-green-50 text-ok",
        tone === "warn" && "bg-amber-50 text-warn",
        tone === "bad" && "bg-red-50 text-bad",
        tone === "brand" && "bg-brand-soft text-brand",
        tone === "relax" && "bg-teal-50 text-relax",
        tone === "stress" && "bg-orange-50 text-stress",
      )}
    >
      {children}
    </span>
  );
}

export function Alert({ tone = "info", title, children }: { tone?: "info" | "ok" | "warn" | "bad"; title?: ReactNode; children?: ReactNode }) {
  const Icon = { info: Info, ok: CheckCircle2, warn: AlertTriangle, bad: XCircle }[tone];
  return (
    <div
      role={tone === "bad" ? "alert" : "status"}
      className={clsx(
        "flex gap-3 rounded-lg border p-3 text-sm",
        tone === "info" && "border-blue-200 bg-blue-50 text-blue-900",
        tone === "ok" && "border-green-200 bg-green-50 text-green-900",
        tone === "warn" && "border-amber-200 bg-amber-50 text-amber-900",
        tone === "bad" && "border-red-200 bg-red-50 text-red-900",
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0">
        {title && <div className="font-medium">{title}</div>}
        {children && <div className={clsx(title && "mt-0.5")}>{children}</div>}
      </div>
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-line px-6 py-10 text-center">
      {icon && <div className="mb-2 text-muted">{icon}</div>}
      <div className="font-medium">{title}</div>
      {children && <div className="mt-1 max-w-md text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Table({ head, children, dense }: { head: ReactNode[]; children: ReactNode; dense?: boolean }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className={clsx("min-w-full text-left text-sm", dense && "text-xs")}>
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-muted">
          <tr>
            {head.map((h, i) => (
              <th key={i} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-white">{children}</tbody>
      </table>
    </div>
  );
}

export function Td({ children, className, mono }: { children?: ReactNode; className?: string; mono?: boolean }) {
  const wraps = className?.includes("whitespace-normal");
  return <td className={clsx("px-3 py-2 align-top", !wraps && "whitespace-nowrap", mono && "num font-mono text-xs", className)}>{children}</td>;
}

export function Field({ label, htmlFor, hint, error, children }: { label: string; htmlFor: string; hint?: ReactNode; error?: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-muted">{hint}</p>}
      {error && <p className="text-xs text-bad">{error}</p>}
    </div>
  );
}

export const inputCls =
  "w-full rounded-lg border border-line bg-white px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20";

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { value: T; label: string }[] }) {
  return (
    <div role="tablist" className="mb-5 inline-flex flex-wrap gap-1 rounded-lg border border-line bg-white p-1">
      {items.map((it) => (
        <button
          key={it.value}
          role="tab"
          aria-selected={value === it.value}
          onClick={() => onChange(it.value)}
          className={clsx(
            "rounded-md px-3 py-1.5 text-sm font-medium",
            value === it.value ? "bg-brand text-white" : "text-muted hover:bg-slate-100 hover:text-ink",
          )}
        >
          {it.label}
        </button>
      ))}
    </div>
  );
}

export function Disclaimer() {
  return (
    <Alert tone="warn" title="Research prototype - not a medical device">
      Outputs are experimental estimates from a model trained on a small public lab dataset (Fitbit). They are not a diagnosis of
      stress, anxiety or any health condition, and have not been validated on Amazfit or everyday data.
    </Alert>
  );
}
