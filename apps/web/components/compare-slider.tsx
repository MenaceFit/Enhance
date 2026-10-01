"use client";

/* eslint-disable @next/next/no-img-element -- signed, short-lived URLs are served as-is */
import { useCallback, useRef, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Before/after comparator: a vertical bar that can be dragged (mouse, touch, keyboard).
 * "ORIGINAL" is on the left, "IA" on the right. `showOriginal` forces the original
 * (used by the "Maintenir pour voir l'original" button).
 */
export function CompareSlider({
  before,
  after,
  width,
  height,
  showOriginal = false,
  loading = false,
  initial = 50,
  className,
  overlay,
  rounded = true,
  priority = false,
}: {
  before: string;
  after: string;
  width: number;
  height: number;
  showOriginal?: boolean;
  loading?: boolean;
  initial?: number;
  className?: string;
  overlay?: ReactNode;
  rounded?: boolean;
  priority?: boolean;
}) {
  const [pos, setPos] = useState(initial);
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const moveTo = useCallback((clientX: number) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  }, []);

  const p = showOriginal ? 100 : pos;

  return (
    <div
      ref={ref}
      className={cn(
        "group relative select-none overflow-hidden bg-mist touch-none",
        rounded && "rounded-2xl",
        dragging ? "cursor-grabbing" : "cursor-ew-resize",
        className,
      )}
      style={{ aspectRatio: `${width} / ${height}` }}
      onPointerDown={(e) => {
        (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
        setDragging(true);
        moveTo(e.clientX);
      }}
      onPointerMove={(e) => dragging && moveTo(e.clientX)}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
    >
      <img
        src={after}
        alt="Photo améliorée"
        draggable={false}
        fetchPriority={priority ? "high" : undefined}
        className="absolute inset-0 size-full object-cover"
      />
      <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - p}% 0 0)` }}>
        <img src={before} alt="Photo originale" draggable={false} className="absolute inset-0 size-full object-cover" />
      </div>

      {overlay && <div className="pointer-events-none absolute inset-0">{overlay}</div>}

      <span
        className={cn(
          "pointer-events-none absolute left-3 top-3 rounded-full bg-paper/85 px-2.5 py-1 text-[10px] font-semibold tracking-[0.14em] text-ink backdrop-blur transition-opacity",
          p < 12 && "opacity-0",
        )}
      >
        ORIGINAL
      </span>
      <span
        className={cn(
          "pointer-events-none absolute right-3 top-3 rounded-full bg-ink/80 px-2.5 py-1 text-[10px] font-semibold tracking-[0.14em] text-paper backdrop-blur transition-opacity",
          p > 88 && "opacity-0",
        )}
      >
        IA
      </span>

      {!showOriginal && (
        <div className="absolute inset-y-0" style={{ left: `${p}%` }}>
          <div className="absolute inset-y-0 -translate-x-1/2 w-px bg-paper shadow-[0_0_0_0.5px_rgb(0_0_0/0.15)]" />
          <button
            type="button"
            role="slider"
            aria-label="Comparer l'original et la version IA"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(p)}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft") setPos((v) => Math.max(0, v - 5));
              if (e.key === "ArrowRight") setPos((v) => Math.min(100, v + 5));
            }}
            className="absolute top-1/2 flex size-10 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-paper text-ink shadow-lift transition-transform group-active:scale-95"
          >
            <svg viewBox="0 0 24 24" className="size-4" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="m9 7-5 5 5 5M15 7l5 5-5 5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      )}

      {loading && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-0.5 overflow-hidden">
          <div className="h-full w-1/3 animate-[slide_1.1s_ease-in-out_infinite] bg-ink/70" />
        </div>
      )}
    </div>
  );
}
