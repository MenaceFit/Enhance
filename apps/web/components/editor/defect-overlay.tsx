"use client";

import { useState } from "react";
import type { Analysis, Defect, Metrics } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Map a normalised point of the analysed photo into the rendered (rotated + cropped) frame. */
export function mapPoint(x: number, y: number, analysis: Analysis, g?: Metrics["geometry"]): [number, number] {
  if (!g) return [x, y];
  const W = analysis.width;
  const H = analysis.height;
  const px = x * W;
  const py = y * H;
  const a = (g.angle * Math.PI) / 180;
  const cos = Math.cos(a);
  const sin = Math.sin(a);
  const cx = W / 2;
  const cy = H / 2;
  // same convention as OpenCV getRotationMatrix2D (positive = counter-clockwise)
  const rx = cos * px + sin * py + (1 - cos) * cx - sin * cy;
  const ry = -sin * px + cos * py + sin * cx + (1 - cos) * cy;
  const [x0, y0, w, h] = g.crop;
  return [(rx - x0 * W) / (w * W), (ry - y0 * H) / (h * H)];
}

export const DEFECT_MESSAGE =
  "Cette zone pourrait correspondre à une imperfection. Nous recommandons de la conserver dans votre annonce.";

export function DefectOverlay({
  defects,
  analysis,
  geometry,
  state,
  onSelect,
}: {
  defects: Defect[];
  analysis: Analysis;
  geometry?: Metrics["geometry"];
  state: Record<string, string>;
  onSelect?: (d: Defect) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <>
      {defects.map((d, i) => {
        const [x, y] = mapPoint(d.bbox.x + d.bbox.w / 2, d.bbox.y + d.bbox.h / 2, analysis, geometry);
        if (x < 0 || x > 1 || y < 0 || y > 1) return null;
        const cropW = geometry?.crop?.[2] ?? 1;
        const size = Math.min(30, Math.max(5, (Math.max(d.bbox.w, d.bbox.h * (analysis.height / analysis.width)) / cropW) * 160));
        const acknowledged = state[d.id] === "acknowledged";
        return (
          <div key={d.id}>
            <span
              className={cn(
                "pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-dashed",
                acknowledged ? "border-paper/70" : "border-[#f5c46b]",
              )}
              style={{ left: `${x * 100}%`, top: `${y * 100}%`, width: `${size}%`, aspectRatio: "1" }}
            />
            <div className="absolute" style={{ left: `${x * 100}%`, top: `${y * 100}%` }}>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(open === d.id ? null : d.id);
                onSelect?.(d);
              }}
              className="pointer-events-auto absolute flex size-6 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-[#f5c46b] text-[11px] font-bold text-ink shadow-lift ring-2 ring-paper"
              aria-label={d.label}
            >
              {i + 1}
            </button>
            {open === d.id && (
              <div
                onPointerDown={(e) => e.stopPropagation()}
                className="pointer-events-auto absolute left-4 top-4 z-10 w-60 animate-fade-in rounded-xl bg-paper p-3 text-xs shadow-lift"
              >
                <p className="font-semibold text-ink">⚠️ {d.label}</p>
                <p className="mt-1 leading-relaxed text-muted">{DEFECT_MESSAGE}</p>
              </div>
            )}
            </div>
          </div>
        );
      })}
    </>
  );
}
