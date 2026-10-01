"use client";

import { useState } from "react";
import { CompareSlider } from "@/components/compare-slider";
import { Segmented } from "@/components/ui/controls";

export type DemoItem = {
  name: string;
  label: string;
  garment: string;
  intensity: string;
  quality_before: number;
  quality_after: number;
  fidelity: number;
  defects: number;
  specks_removed: number;
  width: number;
  height: number;
};

const INTENSITY: Record<string, string> = { naturel: "Naturel", premium: "Premium", studio: "Studio" };

export function DemoGallery({ items }: { items: DemoItem[] }) {
  const [active, setActive] = useState(items[0]?.name ?? "");
  const item = items.find((i) => i.name === active) ?? items[0];
  if (!item) return null;
  return (
    <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
      <div className="mx-auto w-full max-w-md lg:max-w-none">
        <CompareSlider
          key={item.name}
          before={`/demo/${item.name}-before.webp`}
          after={`/demo/${item.name}-after.webp`}
          width={item.width}
          height={item.height}
          className="shadow-lift"
        />
      </div>
      <div className="space-y-8">
        <Segmented
          ariaLabel="Exemples"
          value={active}
          onChange={setActive}
          options={items.map((i) => ({ value: i.name, label: i.label }))}
        />
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line">
          {[
            ["Qualité", `${item.quality_before} → ${item.quality_after}/100`],
            ["Fidélité couleur", `${item.fidelity} %`],
            ["Poussières retirées", String(item.specks_removed)],
            ["Imperfections signalées", item.defects ? `${item.defects} conservée${item.defects > 1 ? "s" : ""}` : "Aucune"],
          ].map(([k, v]) => (
            <div key={k} className="bg-paper p-5">
              <dt className="text-xs uppercase tracking-[0.12em] text-muted">{k}</dt>
              <dd className="mt-1.5 text-xl font-semibold tracking-tight tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="text-sm leading-relaxed text-muted">
          {item.garment} · intensité {INTENSITY[item.intensity] ?? item.intensity}. Lumière corrigée, couleurs équilibrées,
          poussières retirées, vêtement redressé et recadré.
          {item.defects > 0 &&
            " La tache est restée visible : c'est un défaut de l'article, l'outil ne la masque jamais."}
        </p>
        <p className="text-xs text-subtle">Démonstration sur des scènes de test générées, traitées par le vrai moteur.</p>
      </div>
    </div>
  );
}
