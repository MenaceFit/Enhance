"use client";

import { Download, Sparkles, Trash2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Dropzone } from "@/components/dropzone";
import { ExportSheet } from "@/components/export-sheet";
import { PhotoCard, PhotoGrid } from "@/components/photo-card";
import { Button } from "@/components/ui/button";
import { ProgressBar, Segmented, Toggle } from "@/components/ui/controls";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { api, waitForJob } from "@/lib/api";
import { useProject } from "@/lib/hooks";
import type { Intensity, Job } from "@/lib/types";

const INTENSITIES: { value: Intensity; label: string }[] = [
  { value: "leger", label: "Léger" },
  { value: "naturel", label: "Naturel" },
  { value: "premium", label: "Premium" },
  { value: "studio", label: "Studio" },
];

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const { data: project, mutate, error } = useProject(id);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [enhanceOpen, setEnhanceOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [intensity, setIntensity] = useState<Intensity>("naturel");
  const [preserve, setPreserve] = useState(true);
  const [job, setJob] = useState<Job | null>(null);

  if (error) return <p className="p-8 text-sm text-muted">Projet introuvable.</p>;
  if (!project) return <div className="p-8"><div className="skeleton h-8 w-64 rounded-lg" /></div>;

  const photos = project.photos ?? [];
  const ready = photos.filter((p) => p.status === "ready").length;
  const processing = photos.length - ready - photos.filter((p) => p.status === "failed").length;
  const activeJob = job ?? project.active_jobs?.find((j) => j.type === "rerender") ?? null;

  async function saveName() {
    setEditing(false);
    if (name.trim() && name !== project!.name) {
      await api(`/projects/${id}`, { method: "PATCH", json: { name: name.trim() } });
      mutate();
    }
  }

  async function enhanceAll() {
    setEnhanceOpen(false);
    try {
      const created = await api<Job>(`/projects/${id}/enhance`, {
        method: "POST",
        json: { settings: { intensity, preserve_article: preserve } },
      });
      setJob(created);
      await waitForJob(created.id, setJob);
      toast("Toutes les photos ont été améliorées", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setJob(null);
      mutate();
    }
  }

  return (
    <div>
      <div className="flex flex-col gap-4 border-b border-line px-4 py-6 sm:px-8 sm:py-8 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm text-muted">Annonce</p>
          {editing ? (
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={saveName}
              onKeyDown={(e) => e.key === "Enter" && saveName()}
              className="mt-1 w-full border-b border-ink bg-transparent text-2xl font-semibold tracking-[-0.03em] outline-none sm:text-3xl"
            />
          ) : (
            <button
              onClick={() => {
                setName(project.name);
                setEditing(true);
              }}
              className="mt-1 text-left text-2xl font-semibold tracking-[-0.03em] hover:text-graphite sm:text-3xl"
              title="Renommer"
            >
              {project.name}
            </button>
          )}
          <p className="mt-1 text-sm text-muted">
            {photos.length} photo{photos.length > 1 ? "s" : ""}
            {processing > 0 && ` · ${processing} en cours d'amélioration`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" onClick={() => setExportOpen(true)} disabled={!ready}>
            <Download className="size-4" /> Tout télécharger
          </Button>
          <Button size="sm" onClick={() => setEnhanceOpen(true)} disabled={!ready || !!activeJob}>
            <Sparkles className="size-4" /> Améliorer toutes les photos
          </Button>
        </div>
      </div>

      <div className="space-y-8 px-4 py-8 sm:px-8">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
          <div className="rounded-2xl border border-line p-5">
            <Toggle
              checked={project.consistency_enabled}
              onChange={async (v) => {
                await api(`/projects/${id}`, { method: "PATCH", json: { consistency_enabled: v } });
                mutate();
              }}
              label="Cohérence entre les photos"
              description="Même balance des blancs, même luminosité et même température de couleur sur toute l'annonce. Appliquée au prochain « Améliorer toutes les photos »."
            />
          </div>
          {photos.length < 12 && (
            <Dropzone compact projectId={id} onUploaded={() => mutate()} className="lg:w-80" />
          )}
        </div>

        {activeJob && (
          <div className="rounded-2xl bg-mist p-5">
            <p className="mb-3 text-sm font-medium">✨ {activeJob.stage_label ?? "Amélioration en cours…"}</p>
            <ProgressBar value={activeJob.progress} />
          </div>
        )}

        <PhotoGrid>
          {photos.map((p, i) => (
            <PhotoCard key={p.id} photo={p} index={i + 1} refreshKey={`/projects/${id}`} />
          ))}
        </PhotoGrid>

        <div className="border-t border-line pt-6">
          <button
            className="flex items-center gap-2 text-sm text-muted hover:text-[#9b2c2c]"
            onClick={async () => {
              if (!confirm("Supprimer cette annonce et toutes ses photos ?")) return;
              await api(`/projects/${id}`, { method: "DELETE" });
              router.push("/app/projects");
            }}
          >
            <Trash2 className="size-4" /> Supprimer l&apos;annonce
          </button>
        </div>
      </div>

      <Sheet open={enhanceOpen} onClose={() => setEnhanceOpen(false)} title="Améliorer toutes les photos">
        <div className="space-y-6">
          <div className="space-y-2">
            <p className="text-sm font-medium">Intensité</p>
            <Segmented value={intensity} onChange={setIntensity} options={INTENSITIES} />
          </div>
          <Toggle checked={preserve} onChange={setPreserve} label="🔒 Préserver l'article" description="Aucune génération, aucune modification de forme ni de couleur importante." />
          <p className="text-xs text-muted">
            Les mêmes réglages sont appliqués à chaque photo{project.consistency_enabled ? ", avec harmonisation des couleurs et de la lumière" : ""}. Aucun crédit n&apos;est utilisé.
          </p>
          <Button size="lg" className="w-full" onClick={enhanceAll}>
            Lancer
          </Button>
        </div>
      </Sheet>
      <ExportSheet open={exportOpen} onClose={() => setExportOpen(false)} endpoint={`/projects/${id}/exports`} title="Télécharger l'annonce (.zip)" />
    </div>
  );
}
