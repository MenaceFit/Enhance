"use client";

import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={cn("flex items-start justify-between gap-4", disabled ? "opacity-50" : "cursor-pointer")}>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        {description && <span className="mt-0.5 block text-[13px] leading-snug text-muted">{description}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 inline-flex h-6 w-10 shrink-0 items-center rounded-full transition-colors duration-200",
          checked ? "bg-ink" : "bg-line-strong",
        )}
      >
        <span
          className={cn(
            "inline-block size-5 rounded-full bg-paper shadow transition-transform duration-200",
            checked ? "translate-x-[18px]" : "translate-x-0.5",
          )}
        />
      </button>
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  size = "md",
  disabled,
  ariaLabel,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[];
  size?: "sm" | "md";
  disabled?: boolean;
  ariaLabel?: string;
}) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className={cn("flex rounded-full bg-mist p-0.5", disabled && "opacity-50")}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          title={o.title}
          disabled={disabled || o.disabled}
          onClick={() => onChange(o.value)}
          className={cn(
            "flex-1 rounded-full font-medium whitespace-nowrap transition-all duration-200 disabled:opacity-40",
            size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
            value === o.value ? "bg-paper text-ink shadow-[0_1px_3px_rgb(0_0_0/0.1)]" : "text-muted hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function RangeField({
  label,
  icon,
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  disabled,
  format,
  hint,
}: {
  label: ReactNode;
  icon?: ReactNode;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
  format?: (v: number) => string;
  hint?: ReactNode;
}) {
  const fill = ((value - min) / (max - min)) * 100;
  return (
    <div className={cn(disabled && "opacity-60")}>
      <div className="mb-0.5 flex items-center justify-between text-[13px]">
        <span className="flex items-center gap-2 font-medium">
          {icon && <span className="text-base leading-none">{icon}</span>}
          {label}
        </span>
        <span className="font-mono text-xs tabular-nums text-muted">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        className="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ ["--fill" as string]: `${fill}%` }}
        aria-label={typeof label === "string" ? label : undefined}
      />
      {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("rounded-2xl border border-line bg-paper", className)}>{children}</div>;
}

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: "neutral" | "ok" | "warn" | "dark";
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    neutral: "bg-mist text-graphite",
    ok: "bg-ok-soft text-ok",
    warn: "bg-warn-soft text-warn",
    dark: "bg-ink text-paper",
  };
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium", tones[tone], className)}>
      {children}
    </span>
  );
}

export function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn("h-1 overflow-hidden rounded-full bg-line", className)}>
      <div
        className="h-full rounded-full bg-ink transition-[width] duration-500 ease-out"
        style={{ width: `${Math.max(3, Math.min(100, value * 100))}%` }}
      />
    </div>
  );
}
