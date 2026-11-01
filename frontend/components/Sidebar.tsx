"use client";

import clsx from "clsx";
import {
  Activity,
  BookOpen,
  Database,
  FlaskConical,
  Gauge,
  LayoutDashboard,
  Menu,
  Microscope,
  Upload,
  UserRound,
  Workflow,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/dataset", label: "Dataset Explorer", icon: Database },
  { href: "/import", label: "Data Import", icon: Upload },
  { href: "/preprocessing", label: "Data Preprocessing", icon: Workflow },
  { href: "/baseline", label: "Baseline Analysis", icon: UserRound },
  { href: "/estimate", label: "Stress Estimation", icon: Gauge },
  { href: "/models", label: "Model Training", icon: Microscope },
  { href: "/experiments", label: "Research Experiments", icon: FlaskConical },
  { href: "/settings", label: "Settings & Docs", icon: BookOpen },
];

export function Sidebar() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const links = (
    <nav aria-label="Main" className="space-y-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={clsx(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium",
              active ? "bg-brand-soft text-brand" : "text-slate-600 hover:bg-slate-100 hover:text-ink",
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
            {label}
          </Link>
        );
      })}
    </nav>
  );
  const brand = (
    <div className="flex items-center gap-2.5 px-2">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-white">
        <Activity className="h-5 w-5" aria-hidden />
      </div>
      <div className="leading-tight">
        <div className="text-sm font-semibold">Wearable Stress</div>
        <div className="text-xs text-muted">Research prototype</div>
      </div>
    </div>
  );
  return (
    <>
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col gap-6 border-r border-line bg-white p-4 lg:flex">
        {brand}
        {links}
        <p className="mt-auto px-2 text-xs leading-relaxed text-muted">
          Final-year project. Not a medical device. Public data: QoL_Stress (PhysioNet, CC BY 4.0).
        </p>
      </aside>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-white px-4 py-3 lg:hidden">
        {brand}
        <button aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)} className="rounded-md p-2 hover:bg-slate-100">
          {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </header>
      {open && <div className="border-b border-line bg-white p-3 lg:hidden">{links}</div>}
    </>
  );
}
