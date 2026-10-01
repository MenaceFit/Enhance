"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ProgressBar, Segmented } from "@/components/ui/controls";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, waitForJob } from "@/lib/api";
import type { Job } from "@/lib/types";
import { formatBytes, triggerDownload } from "@/lib/utils";

type Format = "jpg" | "png" | "webp";
type Quality = "standard" | "high" | "max";

const QUALITIES: { value: Quality; label: string; hint: string }[] = [
  { value: "standard", label: "Standard", hint: "Pour Vinted · 1600 px" },
  { value: "high", label: "Haute qualité", hint: "Pour archivage · 2400 px" },
  { value: "max", label: "Maximum", hint: "Autres marketplaces · jusqu'à 3072 px" },
];

export function ExportSheet({
  open,
  onClose,
  endpoint,
  versionId,
  title = "Télécharger",
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  endpoint: string; // e.g. /photos/{id}/exports or /projects/{id}/exports
  versionId?: string;
  title?: string;
  onDone?: () => void;
}) {
  const toast = useToast();
  const [format, setFormat] = useState<Format>("jpg");
  const [quality, setQuality] = useState<Quality>("standard");
  const [job, setJob] = useState<Job | null>(null);

  async function run() {
    try {
      const created = await api<Job>(endpoint, { method: "POST", json: { format, quality, version_id: versionId } });
      setJob(created);
      const done = await waitForJob(created.id, setJob, 600);
      if (done.result.download_url) triggerDownload(done.result.download_url);
      toast(`${done.result.filename} · ${formatBytes(Number(done.result.size_bytes ?? 0))}`, "success");
      onDone?.();
      onClose();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setJob(null);
    }
  }

  return (
    <Sheet open={open} onClose={() => !job && onClose()} title={title}>
      <div className="space-y-6">
        <div className="space-y-2">
          <p className="text-sm font-medium">Format</p>
          <Segmented<Format>
            value={format}
            onChange={setFormat}
            options={[
              { value: "jpg", label: "JPG" },
              { value: "png", label: "PNG" },
              { value: "webp", label: "WEBP" },
            ]}
          />
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">Qualité</p>
          <div className="space-y-2">
            {QUALITIES.map((q) => (
              <label
                key={q.value}
                className={`flex cursor-pointer items-center justify-between rounded-xl border px-4 py-3 transition-colors ${
                  quality === q.value ? "border-ink bg-mist" : "border-line hover:border-line-strong"
                }`}
              >
                <span>
                  <span className="block text-sm font-medium">{q.label}</span>
                  <span className="text-xs text-muted">{q.hint}</span>
                </span>
                <input type="radio" name="quality" className="accent-ink" checked={quality === q.value} onChange={() => setQuality(q.value)} />
              </label>
            ))}
          </div>
        </div>
        {job ? (
          <div className="space-y-2">
            <ProgressBar value={job.progress} />
            <p className="text-center text-xs text-muted">{job.stage_label ?? "Préparation…"}</p>
          </div>
        ) : (
          <Button size="lg" className="w-full" onClick={run}>
            <Download className="size-4" /> Télécharger
          </Button>
        )}
        <p className="text-center text-xs text-subtle">Métadonnées (dont GPS) retirées · nom automatique vinted_ai_01.{format}</p>
      </div>
    </Sheet>
  );
}
