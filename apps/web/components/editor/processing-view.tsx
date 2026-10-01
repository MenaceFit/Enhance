"use client";

/* eslint-disable @next/next/no-img-element */
import { Check } from "lucide-react";
import { ProgressBar } from "@/components/ui/controls";
import type { PhotoDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

const STEPS: [number, string][] = [
  [0.02, "Analyse de la qualité de la photo"],
  [0.08, "Détection du vêtement"],
  [0.3, "Recherche des poussières"],
  [0.4, "Détection des imperfections"],
  [0.5, "Analyse des couleurs et de la lumière"],
  [0.6, "Analyse du cadrage"],
  [0.7, "Amélioration non destructive"],
  [0.88, "Contrôle de la fidélité des couleurs"],
  [0.97, "Contrôle qualité final"],
];

export function ProcessingView({ photo }: { photo: PhotoDetail }) {
  const job = photo.latest_job;
  const progress = job?.progress ?? 0;
  const analysing = progress < 0.66;
  const img = photo.original_preview_url ?? photo.original_thumb_url;
  return (
    <div className="mx-auto grid max-w-5xl items-center gap-10 px-4 py-10 sm:px-8 lg:grid-cols-[1fr_1fr]">
      <div className="relative mx-auto aspect-[3/4] w-full max-w-sm overflow-hidden rounded-2xl bg-mist shadow-soft">
        {img ? <img src={img} alt="" className="size-full object-cover" /> : <div className="skeleton size-full" />}
        <div className="absolute inset-0 bg-paper/10" />
        <div className="absolute inset-x-0 top-0 h-16 animate-scan bg-gradient-to-b from-transparent via-paper/60 to-transparent" />
      </div>
      <div>
        <p className="text-2xl font-semibold tracking-[-0.03em]">
          {analysing ? "🔍 Analyse de votre photo…" : "✨ Votre photo est en cours d'amélioration…"}
        </p>
        <p className="mt-2 text-sm text-muted">Quelques secondes. Tu peux continuer à naviguer, rien n&apos;est bloqué.</p>
        <ProgressBar value={progress} className="mt-6" />
        <ul className="mt-6 space-y-2.5">
          {STEPS.map(([at, label], i) => {
            const next = STEPS[i + 1]?.[0] ?? 1.01;
            const done = progress >= next;
            const current = !done && progress >= at;
            return (
              <li key={label} className={cn("flex items-center gap-3 text-sm transition-colors", done ? "text-ink" : current ? "text-ink" : "text-subtle")}>
                <span className={cn("flex size-5 items-center justify-center rounded-full border", done ? "border-ink bg-ink text-paper" : "border-line-strong")}>
                  {done ? <Check className="size-3" strokeWidth={3} /> : current ? <span className="size-1.5 animate-pulse-soft rounded-full bg-ink" /> : null}
                </span>
                {label}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
