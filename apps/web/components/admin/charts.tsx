"use client";

import { useMemo, useRef, useState } from "react";

// Series colours: the brand's neutral for volume, a muted amber reserved for the failure status.
export const SERIES = { ok: "#3a3a3c", failed: "#b5772a", cost: "#0b0b0c" };

type Day = { date: string; photos: number; failed: number; cost_cents: number };

function niceMax(v: number) {
  if (v <= 4) return 4;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * p;
}

const dayLabel = (iso: string) => new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(new Date(iso));

function Tooltip({ x, y, title, rows }: { x: string; y: number; title: string; rows: { color: string; label: string; value: string }[] }) {
  return (
    <div
      className="pointer-events-none absolute z-10 min-w-36 -translate-x-1/2 -translate-y-full rounded-xl border border-line bg-paper px-3 py-2 text-xs shadow-lift"
      style={{ left: x, top: y - 10 }}
    >
      <p className="mb-1 text-muted">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-2">
          <span className="h-0.5 w-3 rounded-full" style={{ background: r.color }} />
          <b className="tabular-nums">{r.value}</b>
          <span className="text-muted">{r.label}</span>
        </p>
      ))}
    </div>
  );
}

/** Photos per day: stacked columns (processed + failed), per-column hover tooltip. */
export function PhotosPerDay({ days }: { days: Day[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const W = 720;
  const H = 220;
  const pad = { l: 36, r: 8, t: 12, b: 26 };
  const max = niceMax(Math.max(1, ...days.map((d) => d.photos + d.failed)));
  const band = (W - pad.l - pad.r) / Math.max(1, days.length);
  const barW = Math.min(24, Math.max(3, band - 2));
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const ticks = [0, max / 2, max];
  const every = Math.ceil(days.length / 6);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-4 text-xs text-muted">
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: SERIES.ok }} /> Photos traitées</span>
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-[3px]" style={{ background: SERIES.failed }} /> ⚠ Échecs</span>
        </div>
        <button onClick={() => setTable((t) => !t)} className="text-xs text-muted underline-offset-4 hover:text-ink hover:underline">
          {table ? "Voir le graphique" : "Voir le tableau"}
        </button>
      </div>
      {table ? (
        <div className="max-h-64 overflow-auto rounded-xl border border-line">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-mist text-left text-muted">
              <tr><th className="px-3 py-2 font-medium">Jour</th><th className="px-3 py-2 text-right font-medium">Traitées</th><th className="px-3 py-2 text-right font-medium">Échecs</th></tr>
            </thead>
            <tbody className="divide-y divide-line">
              {days.map((d) => (
                <tr key={d.date}><td className="px-3 py-1.5">{dayLabel(d.date)}</td><td className="px-3 py-1.5 text-right tabular-nums">{d.photos}</td><td className="px-3 py-1.5 text-right tabular-nums">{d.failed}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Photos traitées par jour">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#ececea" strokeWidth={1} />
                <text x={pad.l - 8} y={y(t) + 3.5} textAnchor="end" className="fill-[#a1a1a6] text-[10px] tabular-nums">{t.toLocaleString("fr-FR")}</text>
              </g>
            ))}
            {days.map((d, i) => {
              const cx = pad.l + band * i + band / 2;
              const okH = y(0) - y(d.photos);
              const failH = y(0) - y(d.failed);
              const gap = d.photos && d.failed ? 2 : 0;
              const r = 4;
              const top = (h: number, base: number, round: boolean) => {
                if (h <= 0) return null;
                const x0 = cx - barW / 2;
                const rr = round ? Math.min(r, h, barW / 2) : 0;
                const t = base - h;
                return `M${x0},${base} V${t + rr} Q${x0},${t} ${x0 + rr},${t} H${x0 + barW - rr} Q${x0 + barW},${t} ${x0 + barW},${t + rr} V${base} Z`;
              };
              const okPath = top(okH, y(0), !d.failed);
              const failPath = top(failH, y(0) - okH - gap, true);
              return (
                <g key={d.date} opacity={hover === null || hover === i ? 1 : 0.55}>
                  {okPath && <path d={okPath} fill={SERIES.ok} />}
                  {failPath && <path d={failPath} fill={SERIES.failed} />}
                  <rect
                    x={pad.l + band * i}
                    y={pad.t}
                    width={band}
                    height={H - pad.t - pad.b}
                    fill="transparent"
                    tabIndex={0}
                    onPointerEnter={() => setHover(i)}
                    onPointerLeave={() => setHover(null)}
                    onFocus={() => setHover(i)}
                    onBlur={() => setHover(null)}
                  />
                  {i % every === 0 && (
                    <text x={cx} y={H - 8} textAnchor="middle" className="fill-[#a1a1a6] text-[10px]">{dayLabel(d.date)}</text>
                  )}
                </g>
              );
            })}
          </svg>
          {hover !== null && days[hover] && (
            <Tooltip
              x={`${((pad.l + band * hover + band / 2) / W) * 100}%`}
              y={0}
              title={dayLabel(days[hover].date)}
              rows={[
                { color: SERIES.ok, label: "traitées", value: String(days[hover].photos) },
                { color: SERIES.failed, label: "échecs", value: String(days[hover].failed) },
              ]}
            />
          )}
        </div>
      )}
    </div>
  );
}

/** AI cost per day: single-series line with a 10% wash, crosshair + tooltip. */
export function CostPerDay({ days }: { days: Day[] }) {
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const W = 720;
  const H = 140;
  const pad = { l: 58, r: 12, t: 12, b: 22 };
  const values = days.map((d) => d.cost_cents / 100);
  const max = Math.max(0.01, niceMax(Math.max(...values, 0) * 100) / 100);
  const x = (i: number) => pad.l + ((W - pad.l - pad.r) * i) / Math.max(1, days.length - 1);
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max);
  const line = useMemo(() => values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" "), [values]); // eslint-disable-line react-hooks/exhaustive-deps
  const area = `${line} L${x(values.length - 1)},${y(0)} L${x(0)},${y(0)} Z`;
  const last = values.length - 1;
  const eur = (v: number) => v.toLocaleString("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: v < 1 ? 3 : 2 });

  return (
    <div className="relative">
      <svg
        ref={ref}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label="Coût IA par jour"
        onPointerMove={(e) => {
          const r = ref.current!.getBoundingClientRect();
          const px = ((e.clientX - r.left) / r.width) * W;
          const i = Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (days.length - 1));
          setHover(Math.max(0, Math.min(days.length - 1, i)));
        }}
        onPointerLeave={() => setHover(null)}
      >
        {[0, max].map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="#ececea" strokeWidth={1} />
            <text x={pad.l - 8} y={y(t) + 3.5} textAnchor="end" className="fill-[#a1a1a6] text-[10px]">{eur(t)}</text>
          </g>
        ))}
        <path d={area} fill={SERIES.cost} opacity={0.08} />
        <path d={line} fill="none" stroke={SERIES.cost} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {last >= 0 && <circle cx={x(last)} cy={y(values[last])} r={4} fill={SERIES.cost} stroke="#fff" strokeWidth={2} />}
        {hover !== null && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={pad.t} y2={H - pad.b} stroke="#d6d6d2" strokeWidth={1} />
            <circle cx={x(hover)} cy={y(values[hover])} r={4} fill={SERIES.cost} stroke="#fff" strokeWidth={2} />
          </>
        )}
      </svg>
      {hover !== null && days[hover] && (
        <Tooltip
          x={`${(x(hover) / W) * 100}%`}
          y={0}
          title={dayLabel(days[hover].date)}
          rows={[{ color: SERIES.cost, label: "coût IA", value: eur(values[hover]) }]}
        />
      )}
    </div>
  );
}
