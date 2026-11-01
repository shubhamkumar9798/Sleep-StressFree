"use client";

import { useState } from "react";
import { Alert, PageHeader, Tabs } from "@/components/ui";
import { CsvImport } from "./CsvImport";
import { ManualEntry } from "./ManualEntry";
import { RecordsExplorer } from "./RecordsExplorer";
import { ScreenshotImport } from "./ScreenshotImport";

type Tab = "manual" | "csv" | "screenshot" | "records";

export default function ImportPage() {
  const [tab, setTab] = useState<Tab>("manual");
  return (
    <>
      <PageHeader
        title="Data import"
        subtitle="Add your own smartwatch measurements (for example from an Amazfit / Zepp app) by manual entry, CSV export or screenshot. These records are stored separately from the public research dataset, keep their source label, and are never used for model training."
      />
      <div className="mb-5">
        <Alert tone="info">
          No direct Zepp/Amazfit API is used or assumed. Store only pseudonymous participant codes, never names or e-mail addresses.
        </Alert>
      </div>
      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        items={[
          { value: "manual", label: "Manual entry" },
          { value: "csv", label: "CSV import" },
          { value: "screenshot", label: "Screenshot (OCR)" },
          { value: "records", label: "Imported records" },
        ]}
      />
      {tab === "manual" && <ManualEntry />}
      {tab === "csv" && <CsvImport />}
      {tab === "screenshot" && <ScreenshotImport />}
      {tab === "records" && <RecordsExplorer />}
    </>
  );
}
