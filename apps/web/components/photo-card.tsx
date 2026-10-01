"use client";

/* eslint-disable @next/next/no-img-element */
import { AlertTriangle, Star } from "lucide-react";
import Link from "next/link";
import { useSWRConfig } from "swr";
import { api } from "@/lib/api";
import type { PhotoSummary } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Checklist({ photo, compact }: { photo: PhotoSummary; compact?: boolean }) {
  const items = [
    ["Nettoyée", photo.checklist.cleaned],
    ["Couleurs", photo.checklist.colors],
    ["Cadrage", photo.checklist.framing],
  ] as const;
  return (
    <ul className={cn("flex flex-wrap gap-x-3 gap-y-1 text-xs", compact && "gap-x-2")}>
      {items.map(([label, ok]) => (
        <li key={label} className={ok ? "text-ok" : "text-subtle"}>
          {ok ? "✓" : "·"} {label}
        </li>
      ))}
    </ul>
  );
}

export function PhotoCard({ photo, index, refreshKey }: { photo: PhotoSummary; index?: number; refreshKey?: string }) {
  const { mutate } = useSWRConfig();
  const busy = photo.status === "queued" || photo.status === "processing";
  const failed = photo.status === "failed";
  const toggleFav = async (e: React.MouseEvent) => {
    e.preventDefault();
    await api(`/photos/${photo.id}`, { method: "PATCH", json: { is_favorite: !photo.is_favorite } });
    if (refreshKey) mutate(refreshKey);
    mutate((key) => typeof key === "string" && key.startsWith("/photos"));
  };
  return (
    <Link href={`/app/photos/${photo.id}`} className="group block animate-fade-up">
      <div className="relative aspect-[3/4] overflow-hidden rounded-2xl bg-mist">
        {photo.thumb_url || photo.original_thumb_url ? (
          <img
            src={(photo.thumb_url || photo.original_thumb_url) as string}
            alt={photo.filename}
            className={cn("size-full object-cover transition-transform duration-500 group-hover:scale-[1.02]", busy && "opacity-60 blur-[1px]")}
          />
        ) : (
          <div className="skeleton size-full" />
        )}
        {busy && (
          <div className="absolute inset-0 overflow-hidden">
            <div className="absolute inset-x-0 top-0 h-8 animate-scan bg-gradient-to-b from-transparent via-paper/50 to-transparent" />
            <span className="absolute inset-x-3 bottom-3 rounded-full bg-paper/90 px-3 py-1.5 text-center text-xs font-medium backdrop-blur">
              {photo.status === "queued" ? "En attente…" : "Amélioration en cours…"}
            </span>
          </div>
        )}
        {failed && (
          <div className="absolute inset-0 flex items-center justify-center bg-paper/70 p-4 text-center text-xs text-[#9b2c2c]">
            {photo.error ?? "Échec du traitement"}
          </div>
        )}
        {typeof index === "number" && (
          <span className="absolute left-3 top-3 rounded-full bg-paper/90 px-2 py-0.5 font-mono text-[11px] backdrop-blur">
            PHOTO {String(index).padStart(2, "0")}
          </span>
        )}
        <button
          onClick={toggleFav}
          aria-label={photo.is_favorite ? "Retirer des favoris" : "Ajouter aux favoris"}
          className={cn(
            "absolute right-3 top-3 rounded-full bg-paper/90 p-1.5 backdrop-blur transition-opacity",
            photo.is_favorite ? "opacity-100" : "opacity-0 group-hover:opacity-100",
          )}
        >
          <Star className={cn("size-3.5", photo.is_favorite && "fill-ink")} />
        </button>
        {photo.defects_count > 0 && !busy && (
          <span className="absolute bottom-3 left-3 flex items-center gap-1 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] text-warn">
            <AlertTriangle className="size-3" /> {photo.defects_count}
          </span>
        )}
      </div>
      <div className="mt-2.5 space-y-1 px-0.5">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium">{photo.garment ?? photo.filename}</p>
          {photo.fidelity != null && <span className="shrink-0 font-mono text-[11px] text-muted">🎨 {photo.fidelity}%</span>}
        </div>
        {photo.status === "ready" && <Checklist photo={photo} compact />}
      </div>
    </Link>
  );
}

export function PhotoGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">{children}</div>;
}

export function EmptyState({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-3xl border border-dashed border-line px-6 py-20 text-center">
      <p className="text-lg font-semibold tracking-tight">{title}</p>
      {children && <p className="mt-2 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
