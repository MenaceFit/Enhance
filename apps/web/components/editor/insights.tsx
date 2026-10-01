"use client";

/* eslint-disable @next/next/no-img-element */
import { AlertTriangle, Check, RotateCcw } from "lucide-react";
import type { Analysis, Defect, Metrics, Version } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";
import { DEFECT_MESSAGE } from "./defect-overlay";

const BREAKDOWN_LABELS: Record<string, string> = {
  nettete: "Netteté",
  lumiere: "Lumière",
  couleurs: "Couleurs",
  bruit: "Bruit",
  cadrage: "Cadrage",
  proprete: "Propreté",
  resolution: "Résolution",
};

export function FidelityBadge({ metrics, onReduce }: { metrics?: Metrics; onReduce: () => void }) {
  const f = metrics?.fidelity;
  if (!f) return null;
  return (
    <div className={cn("rounded-2xl p-4", f.passed ? "bg-mist" : "bg-warn-soft")}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm">
          🎨 Fidélité couleur : <b className="tabular-nums">{f.score} %</b>
        </p>
        <span className="flex items-center gap-1.5 text-xs text-muted" title={`Avant ${f.dominant_before} · après ${f.dominant_after}`}>
          <span className="size-3.5 rounded-full border border-line-strong" style={{ background: f.dominant_before }} />→
          <span className="size-3.5 rounded-full border border-line-strong" style={{ background: f.dominant_after }} />
        </span>
      </div>
      {!f.passed && (
        <div className="mt-3 flex items-center justify-between gap-3">
          <p className="text-xs text-warn">⚠️ La correction couleur semble trop importante.</p>
          <button onClick={onReduce} className="shrink-0 rounded-full bg-paper px-3 py-1.5 text-xs font-medium text-ink shadow-soft hover:bg-mist">
            Réduire la correction
          </button>
        </div>
      )}
    </div>
  );
}

export function Warnings({ metrics, analysis }: { metrics?: Metrics; analysis: Analysis | null }) {
  const items = [
    ...(metrics?.auto_adjustments ?? []),
    ...(metrics?.warnings ?? []),
    ...(metrics?.structure && !metrics.structure.passed ? metrics.structure.issues : []),
    ...(analysis?.warnings ?? []),
  ];
  const unique = Array.from(new Set(items));
  if (!unique.length) return null;
  return (
    <ul className="space-y-1.5 rounded-2xl bg-warn-soft p-4 text-xs leading-relaxed text-warn">
      {unique.map((w) => (
        <li key={w} className="flex gap-2">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" /> {w}
        </li>
      ))}
    </ul>
  );
}

export function DefectsList({
  defects,
  state,
  onAcknowledge,
  retouch,
  onToggleRetouch,
  preserve,
}: {
  defects: Defect[];
  state: Record<string, string>;
  onAcknowledge: (d: Defect) => void;
  retouch: number[];
  onToggleRetouch: (id: number) => void;
  preserve: boolean;
}) {
  if (!defects.length) {
    return <p className="flex items-center gap-2 text-sm text-muted"><Check className="size-4 text-ok" /> Aucune imperfection détectée.</p>;
  }
  const real = defects.filter((d) => d.kind !== "speck");
  return (
    <div className="space-y-3">
      {real.length > 0 && (
        <p className="text-sm font-medium text-warn">
          ⚠️ {real.length} potentielle{real.length > 1 ? "s" : ""} imperfection{real.length > 1 ? "s" : ""} détectée{real.length > 1 ? "s" : ""}
        </p>
      )}
      <p className="text-xs leading-relaxed text-muted">{DEFECT_MESSAGE}</p>
      <ul className="space-y-2">
        {defects.map((d, i) => {
          const ack = state[d.id] === "acknowledged";
          const speck = d.kind === "speck" && d.speck_id != null;
          const retouched = speck && retouch.includes(d.speck_id as number);
          return (
            <li key={d.id} className="flex items-start gap-3 rounded-xl border border-line p-3">
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-[#f5c46b] text-[10px] font-bold">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{d.label}</p>
                <p className="text-xs text-muted">Confiance {Math.round(d.confidence * 100)} %{ack ? " · vu, conservé" : ""}</p>
                {speck && (
                  <button
                    disabled={preserve}
                    onClick={() => onToggleRetouch(d.speck_id as number)}
                    title={preserve ? "Désactive « Préserver l'article » pour retoucher" : undefined}
                    className="mt-1.5 text-xs font-medium underline underline-offset-4 disabled:cursor-not-allowed disabled:no-underline disabled:opacity-40"
                  >
                    {retouched ? "Conserver finalement" : "C'est une poussière, la retirer"}
                  </button>
                )}
              </div>
              {!ack && !speck && (
                <button onClick={() => onAcknowledge(d)} className="shrink-0 rounded-full border border-line px-2.5 py-1 text-xs hover:bg-mist">
                  Conserver
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function AnalysisDetails({ analysis, metrics }: { analysis: Analysis; metrics?: Metrics }) {
  const c = analysis.clothing;
  const before = analysis.quality;
  const after = metrics?.quality;
  return (
    <div className="space-y-5 text-sm">
      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-mist p-3">
          <p className="text-xs text-muted">Vêtement détecté</p>
          <p className="mt-1 font-medium">{c.label}</p>
          <p className="text-xs text-subtle">Confiance {Math.round(c.confidence * 100)} %{c.provider !== "local" ? ` · ${c.provider}` : ""}</p>
        </div>
        <div className="rounded-xl bg-mist p-3">
          <p className="text-xs text-muted">Couleurs dominantes</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {c.dominant_colors.map((col) => (
              <span key={col.name} className="flex items-center gap-1 text-xs">
                <span className="size-3 rounded-full border border-line-strong" style={{ background: col.hex ?? "#ccc" }} />
                {col.name}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 text-xs text-muted">
        {analysis.illuminant.cast_label && <span className="rounded-full bg-mist px-2.5 py-1">Corrigé : {analysis.illuminant.cast_label}</span>}
        {Math.abs(analysis.composition.tilt_deg) >= 0.6 && analysis.composition.tilt_confidence >= 0.3 && (
          <span className="rounded-full bg-mist px-2.5 py-1">Inclinaison : {analysis.composition.tilt_deg.toFixed(1)}°</span>
        )}
        <span className="rounded-full bg-mist px-2.5 py-1">Motif : {c.pattern}</span>
        {metrics && metrics.removed_specks > 0 && <span className="rounded-full bg-mist px-2.5 py-1">{metrics.removed_specks} poussières retirées</span>}
      </div>
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <p className="font-medium">Qualité de la photo</p>
          <p className="tabular-nums">
            <span className="text-muted">{before.score}</span> → <b>{after?.score ?? "…"}</b>
            <span className="text-muted">/100</span>
          </p>
        </div>
        <div className="space-y-1.5">
          {Object.entries(before.breakdown).map(([k, v]) => {
            const a = after?.breakdown?.[k];
            return (
              <div key={k} className="grid grid-cols-[84px_1fr_32px] items-center gap-3 text-xs">
                <span className="text-muted">{BREAKDOWN_LABELS[k] ?? k}</span>
                <div className="relative h-1.5 overflow-hidden rounded-full bg-line">
                  <div className="absolute inset-y-0 left-0 rounded-full bg-line-strong" style={{ width: `${v}%` }} />
                  {a != null && <div className="absolute inset-y-0 left-0 rounded-full bg-ink transition-all duration-500" style={{ width: `${a}%` }} />}
                </div>
                <span className="text-right font-mono tabular-nums">{a ?? v}</span>
              </div>
            );
          })}
        </div>
      </div>
      {metrics?.structure && (
        <p className="text-xs text-muted">
          Contrôle anti-modification : silhouette {Math.round(metrics.structure.silhouette_iou * 100)} % · détails{" "}
          {Math.round(metrics.structure.edge_recall * 100)} % · {metrics.structure.passed ? "✓ conforme" : "⚠️ à vérifier"}
        </p>
      )}
    </div>
  );
}

export function History({
  versions,
  currentId,
  onRestore,
}: {
  versions: Version[];
  currentId?: string;
  onRestore: (v: Version) => void;
}) {
  return (
    <ol className="space-y-2">
      <li className="flex items-center gap-3 rounded-xl px-2 py-1.5 text-xs text-muted">Original · photo importée</li>
      {[...versions].reverse().map((v) => (
        <li
          key={v.id}
          className={cn("flex items-center gap-3 rounded-xl border p-2", v.id === currentId ? "border-ink" : "border-line")}
        >
          <img src={v.thumb_url} alt="" className="h-12 w-9 rounded-md object-cover" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{v.label}</p>
            <p className="text-xs text-muted">{relativeTime(v.created_at)}</p>
          </div>
          {v.id === currentId ? (
            <span className="text-xs text-muted">Actuelle</span>
          ) : (
            <button onClick={() => onRestore(v)} className="flex items-center gap-1 rounded-full px-2.5 py-1 text-xs hover:bg-mist">
              <RotateCcw className="size-3" /> Revenir
            </button>
          )}
        </li>
      ))}
    </ol>
  );
}
