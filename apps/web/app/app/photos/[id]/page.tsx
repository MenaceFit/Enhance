"use client";

import { ArrowLeft, ChevronLeft, ChevronRight, Download, Eye, RotateCcw, Save, ScanSearch, Star } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CompareSlider } from "@/components/compare-slider";
import { DefectOverlay } from "@/components/editor/defect-overlay";
import { AnalysisDetails, DefectsList, FidelityBadge, History, Warnings } from "@/components/editor/insights";
import { ProcessingView } from "@/components/editor/processing-view";
import { SettingsPanel } from "@/components/editor/settings-panel";
import { ExportSheet } from "@/components/export-sheet";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/controls";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api";
import { usePhoto } from "@/lib/hooks";
import { sameSettings, usePresets, vintedPreset, withIntensity } from "@/lib/presets";
import type { Defect, Intensity, Preview, Settings, Version } from "@/lib/types";
import { cn } from "@/lib/utils";

type Tab = "reglages" | "imperfections" | "analyse" | "historique";

export default function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const presets = usePresets();
  const { data: photo, mutate, error } = usePhoto(id);

  const [settings, setSettings] = useState<Settings | null>(null);
  const [baseVersionId, setBaseVersionId] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ key: string; data: Preview } | null>(null);
  const [holdOriginal, setHoldOriginal] = useState(false);
  const [showDefects, setShowDefects] = useState(true);
  const [tab, setTab] = useState<Tab>("reglages");
  const [exportOpen, setExportOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const requestId = useRef(0);

  const version = photo?.current_version ?? null;

  // (Re)initialise the editor from the current version (first load, restore, save):
  // state adjusted during render rather than synchronised in an effect.
  if (version && version.id !== baseVersionId) {
    setBaseVersionId(version.id);
    setSettings(version.settings);
    setPreview(null);
  }

  const dirty = !!settings && !!version && !sameSettings(settings, version.settings);
  const settingsKey = settings ? JSON.stringify(settings) : "";
  const ready = photo?.status === "ready";
  const livePreview = dirty && preview?.key === settingsKey ? preview.data : null;
  const lastPreview = dirty ? preview?.data ?? null : null; // keep showing the previous render while the next one computes
  const rendering = dirty && preview?.key !== settingsKey;

  // Live preview: debounced, cached server-side, stale responses ignored.
  useEffect(() => {
    if (!settingsKey || !ready || !dirty) return;
    const rid = ++requestId.current;
    const t = setTimeout(async () => {
      try {
        const res = await api<Preview>(`/photos/${id}/preview`, { method: "POST", json: { settings: JSON.parse(settingsKey) } });
        if (rid === requestId.current) setPreview({ key: settingsKey, data: res });
      } catch (e) {
        if (rid === requestId.current) toast((e as Error).message, "error");
      }
    }, 320);
    return () => clearTimeout(t);
  }, [settingsKey, dirty, ready, id, toast]);

  const shown = useMemo(() => {
    const p = livePreview ?? lastPreview;
    if (p) return p;
    if (version)
      return { after_url: version.after_url, before_url: version.before_url, width: version.width, height: version.height, metrics: version.metrics, settings: version.settings };
    return null;
  }, [livePreview, lastPreview, version]);

  const patch = useCallback((p: Partial<Settings>) => setSettings((s) => (s ? { ...s, ...p } : s)), []);
  const setIntensity = useCallback((v: Intensity) => setSettings((s) => (s ? withIntensity(s, v, presets) : s)), [presets]);

  // keyboard: hold space to see the original
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === "Space" && !(e.target instanceof HTMLInputElement) && !(e.target instanceof HTMLButtonElement)) {
        e.preventDefault();
        setHoldOriginal(true);
      }
    };
    const up = (e: KeyboardEvent) => e.code === "Space" && setHoldOriginal(false);
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  if (error) {
    return (
      <div className="p-8">
        <p className="text-sm text-muted">Photo introuvable ou expirée.</p>
        <Link href="/app/photos" className="mt-4 inline-block text-sm underline">Retour à mes photos</Link>
      </div>
    );
  }
  if (!photo) {
    return (
      <div className="grid gap-8 p-4 sm:p-8 lg:grid-cols-[1fr_380px]">
        <div className="skeleton aspect-[3/4] max-h-[80vh] rounded-2xl" />
        <div className="space-y-4">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-10 rounded-xl" />)}
        </div>
      </div>
    );
  }

  if (photo.status === "queued" || photo.status === "processing") return <ProcessingView photo={photo} />;

  if (photo.status === "failed") {
    return (
      <div className="mx-auto max-w-md px-4 py-20 text-center">
        <p className="text-xl font-semibold tracking-tight">Cette photo n&apos;a pas pu être améliorée</p>
        <p className="mt-2 text-sm text-muted">{photo.error ?? "Une erreur est survenue."} Le crédit t&apos;a été rendu.</p>
        <div className="mt-6 flex justify-center gap-2">
          <Button
            onClick={async () => {
              try {
                await api(`/photos/${id}/retry`, { method: "POST" });
                mutate();
              } catch (e) {
                toast((e as Error).message, "error");
              }
            }}
          >
            Réessayer
          </Button>
          <Button variant="secondary" onClick={() => router.push("/app/enhance")}>Importer une autre photo</Button>
        </div>
      </div>
    );
  }

  if (!settings || !shown || !photo.analysis) return null;

  const analysis = photo.analysis;
  const defects = analysis.defects;
  const realDefects = defects.filter((d) => d.kind !== "speck");
  const metrics = shown.metrics;
  const siblings = photo.siblings ?? [];
  const idx = siblings.indexOf(photo.id);
  const isVinted = sameSettings(settings, vintedPreset(presets));
  const aiVersion = photo.versions.find((v) => v.kind === "ai");

  async function save(label?: string): Promise<Version | null> {
    if (!settings) return null;
    setSaving(true);
    try {
      const v = await api<Version>(`/photos/${id}/versions`, { method: "POST", json: { settings, label } });
      await mutate();
      toast("Version enregistrée", "success");
      return v;
    } catch (e) {
      toast((e as Error).message, "error");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function restore(v: Version) {
    await api(`/photos/${id}/versions/${v.id}/restore`, { method: "POST" });
    await mutate();
    toast("Version restaurée");
  }

  async function acknowledge(d: Defect) {
    await api(`/photos/${id}/defects/${d.id}`, { method: "PATCH", json: { status: "acknowledged" } });
    mutate();
  }

  async function openExport() {
    if (dirty) {
      const v = await save();
      if (!v) return;
    }
    setExportOpen(true);
  }

  const reduceCorrection = () => patch({ color: Math.round((settings.color ?? 40) * 0.5), hue: 0 });

  return (
    <div className="flex min-h-[calc(100vh-56px)] flex-col lg:min-h-screen">
      {/* top bar */}
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <Link href={`/app/projects/${photo.project_id}`} className="rounded-lg p-2 text-muted hover:bg-mist hover:text-ink" aria-label="Retour à l'annonce">
            <ArrowLeft className="size-4" />
          </Link>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">{analysis.clothing.label}</p>
            <p className="truncate text-xs text-muted">{photo.filename}</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          {siblings.length > 1 && (
            <div className="mr-2 flex items-center gap-1 text-xs text-muted">
              <button disabled={idx <= 0} onClick={() => router.push(`/app/photos/${siblings[idx - 1]}`)} className="rounded-lg p-1.5 hover:bg-mist disabled:opacity-30" aria-label="Photo précédente">
                <ChevronLeft className="size-4" />
              </button>
              <span className="tabular-nums">{String(idx + 1).padStart(2, "0")} / {String(siblings.length).padStart(2, "0")}</span>
              <button disabled={idx >= siblings.length - 1} onClick={() => router.push(`/app/photos/${siblings[idx + 1]}`)} className="rounded-lg p-1.5 hover:bg-mist disabled:opacity-30" aria-label="Photo suivante">
                <ChevronRight className="size-4" />
              </button>
            </div>
          )}
          <button
            onClick={async () => {
              await api(`/photos/${id}`, { method: "PATCH", json: { is_favorite: !photo.is_favorite } });
              mutate();
            }}
            className="rounded-lg p-2 hover:bg-mist"
            aria-label="Favori"
          >
            <Star className={cn("size-4", photo.is_favorite && "fill-ink")} />
          </button>
        </div>
      </div>

      <div className="grid flex-1 lg:grid-cols-[1fr_400px]">
        {/* canvas */}
        <div className="flex flex-col items-center gap-4 bg-mist/50 px-4 py-6 sm:px-8 lg:sticky lg:top-0 lg:h-[calc(100vh-57px)] lg:justify-center">
          <div className="w-full" style={{ maxWidth: `min(100%, calc((100vh - 220px) * ${shown.width / shown.height}))` }}>
            <CompareSlider
              before={shown.before_url}
              after={shown.after_url}
              width={shown.width}
              height={shown.height}
              showOriginal={holdOriginal}
              loading={rendering}
              className="shadow-lift"
              overlay={
                showDefects && realDefects.length > 0 && !holdOriginal ? (
                  <DefectOverlay defects={realDefects} analysis={analysis} geometry={metrics.geometry} state={photo.defect_state} onSelect={() => setTab("imperfections")} />
                ) : undefined
              }
            />
          </div>
          <div className="flex flex-wrap items-center justify-center gap-2">
            <button
              onPointerDown={() => setHoldOriginal(true)}
              onPointerUp={() => setHoldOriginal(false)}
              onPointerLeave={() => setHoldOriginal(false)}
              className={cn("flex h-9 items-center gap-2 rounded-full border px-4 text-xs font-medium transition-colors select-none", holdOriginal ? "border-ink bg-ink text-paper" : "border-line bg-paper hover:border-line-strong")}
            >
              <Eye className="size-3.5" /> Maintenir pour voir l&apos;original
            </button>
            {realDefects.length > 0 && (
              <button
                onClick={() => setShowDefects((v) => !v)}
                className={cn("flex h-9 items-center gap-2 rounded-full border px-4 text-xs font-medium", showDefects ? "border-[#f0d9a8] bg-warn-soft text-warn" : "border-line bg-paper")}
              >
                <ScanSearch className="size-3.5" /> {realDefects.length} imperfection{realDefects.length > 1 ? "s" : ""}
              </button>
            )}
          </div>
        </div>

        {/* panel */}
        <aside className="flex flex-col border-l border-line bg-paper">
          <div className="space-y-4 border-b border-line p-5">
            <FidelityBadge metrics={metrics} onReduce={reduceCorrection} />
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">Qualité</span>
              <span className="tabular-nums">
                <span className="text-muted">{analysis.quality.score}</span> → <b>{metrics.quality?.score ?? "…"}</b>/100
              </span>
            </div>
            <Warnings metrics={metrics} analysis={analysis} />
          </div>

          <div className="border-b border-line px-5 py-3">
            <Segmented<Tab>
              size="sm"
              value={tab}
              onChange={setTab}
              options={[
                { value: "reglages", label: "Réglages" },
                { value: "imperfections", label: `Défauts${realDefects.length ? ` (${realDefects.length})` : ""}` },
                { value: "analyse", label: "Analyse" },
                { value: "historique", label: "Historique" },
              ]}
            />
          </div>

          <div className="flex-1 overflow-y-auto p-5">
            {tab === "reglages" && (
              <SettingsPanel
                settings={settings}
                onChange={patch}
                onIntensity={setIntensity}
                onVinted={() => setSettings(vintedPreset(presets))}
                isVinted={isVinted}
                segmentationOk={analysis.segmentation.confidence >= 0.45}
              />
            )}
            {tab === "imperfections" && (
              <DefectsList
                defects={defects}
                state={photo.defect_state}
                onAcknowledge={acknowledge}
                retouch={settings.retouch_specks}
                preserve={settings.preserve_article}
                onToggleRetouch={(sid) =>
                  patch({
                    retouch_specks: settings.retouch_specks.includes(sid)
                      ? settings.retouch_specks.filter((x) => x !== sid)
                      : [...settings.retouch_specks, sid],
                  })
                }
              />
            )}
            {tab === "analyse" && <AnalysisDetails analysis={analysis} metrics={metrics} />}
            {tab === "historique" && <History versions={photo.versions} currentId={version?.id} onRestore={restore} />}
          </div>

          <div className="sticky bottom-0 grid grid-cols-[auto_auto_1fr] gap-2 border-t border-line bg-paper/95 p-4 backdrop-blur">
            <Button
              variant="ghost"
              size="md"
              title="Réinitialiser"
              onClick={() => {
                setSettings((aiVersion ?? version)?.settings ?? settings);
                toast("Réglages de la version IA rétablis");
              }}
            >
              <RotateCcw className="size-4" />
            </Button>
            <Button variant="secondary" onClick={() => save()} disabled={!dirty} loading={saving} title="Enregistrer cette version">
              <Save className="size-4" />
            </Button>
            <Button onClick={openExport} loading={saving}>
              <Download className="size-4" /> Télécharger
            </Button>
          </div>
        </aside>
      </div>

      <ExportSheet open={exportOpen} onClose={() => setExportOpen(false)} endpoint={`/photos/${id}/exports`} versionId={photo.current_version?.id} onDone={() => mutate()} />
    </div>
  );
}
