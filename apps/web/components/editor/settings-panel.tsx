"use client";

import { Lock, Sparkles } from "lucide-react";
import { RangeField, Segmented, Toggle } from "@/components/ui/controls";
import { INTENSITIES, PRESERVE_LIMITS } from "@/lib/presets";
import type { Aspect, BackgroundColor, BackgroundMode, Intensity, Settings, UpscaleMode, WrinkleLevel } from "@/lib/types";
import { cn } from "@/lib/utils";

const SWATCHES: { value: BackgroundColor; label: string; color: string }[] = [
  { value: "auto", label: "Auto", color: "conic-gradient(#f3f1ec 0 33%, #e7e7e5 0 66%, #efe8dc 0)" },
  { value: "off_white", label: "Blanc cassé", color: "#f3f1ec" },
  { value: "light_gray", label: "Gris clair", color: "#e7e7e5" },
  { value: "light_beige", label: "Beige très léger", color: "#efe8dc" },
];

export function IntensitySlider({ value, onChange }: { value: Intensity; onChange: (v: Intensity) => void }) {
  const idx = INTENSITIES.findIndex((i) => i.value === value);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[13px]">
        <span className="font-medium">Intensité de l&apos;amélioration</span>
        <span className="text-muted">{INTENSITIES[idx]?.label}</span>
      </div>
      <input
        type="range"
        className="range"
        min={0}
        max={INTENSITIES.length - 1}
        step={1}
        value={idx}
        onChange={(e) => onChange(INTENSITIES[Number(e.target.value)].value)}
        style={{ ["--fill" as string]: `${(idx / (INTENSITIES.length - 1)) * 100}%` }}
        aria-label="Intensité de l'amélioration"
      />
      <div className="mt-1 flex justify-between text-[11px] text-subtle">
        {INTENSITIES.map((i, n) => (
          <button key={i.value} onClick={() => onChange(i.value)} className={cn("transition-colors hover:text-ink", n === idx && "font-medium text-ink")}>
            {i.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SettingsPanel({
  settings,
  onChange,
  onIntensity,
  onVinted,
  isVinted,
  segmentationOk,
}: {
  settings: Settings;
  onChange: (patch: Partial<Settings>) => void;
  onIntensity: (v: Intensity) => void;
  onVinted: () => void;
  isVinted: boolean;
  segmentationOk: boolean;
}) {
  const preserve = settings.preserve_article;
  const off = settings.intensity === "original";
  return (
    <div className="space-y-6">
      <button
        onClick={onVinted}
        className={cn(
          "flex w-full items-center justify-between rounded-2xl px-4 py-3.5 text-left transition-all",
          isVinted ? "bg-ink text-paper" : "border border-line hover:border-ink",
        )}
      >
        <span>
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4" /> Amélioration Vinted
          </span>
          <span className={cn("mt-0.5 block text-xs", isVinted ? "text-paper/60" : "text-muted")}>
            Le réglage optimisé pour tes annonces, naturel et fidèle
          </span>
        </span>
        {isVinted && <span className="text-xs text-paper/70">Appliqué</span>}
      </button>

      <div className="rounded-2xl bg-mist p-4">
        <Toggle
          checked={preserve}
          onChange={(v) => onChange({ preserve_article: v })}
          label={
            <span className="flex items-center gap-1.5">
              <Lock className="size-3.5" /> Préserver l&apos;article
            </span>
          }
          description="Pas de génération, pas de modification de forme ni de texture, pas de changement important de couleur, défauts jamais retirés."
        />
      </div>

      <IntensitySlider value={settings.intensity} onChange={onIntensity} />

      <div className="space-y-4">
        <RangeField icon="🧹" label="Nettoyage" value={settings.cleaning ?? 0} onChange={(v) => onChange({ cleaning: v })} disabled={off} />
        <RangeField icon="👕" label="Placement" value={settings.placement ?? 0} onChange={(v) => onChange({ placement: v })} disabled={off} />
        <RangeField icon="💡" label="Lumière" value={settings.light ?? 0} onChange={(v) => onChange({ light: v })} disabled={off} />
        <RangeField
          icon="🎨"
          label="Couleur"
          value={settings.color ?? 0}
          onChange={(v) => onChange({ color: v })}
          disabled={off}
          hint={preserve && (settings.color ?? 0) > PRESERVE_LIMITS.color ? `Limité à ${PRESERVE_LIMITS.color} pour préserver l'article.` : undefined}
        />
        <RangeField icon="🔍" label="Netteté" value={settings.sharpness ?? 0} onChange={(v) => onChange({ sharpness: v })} disabled={off} />
      </div>

      <div className="space-y-2">
        <p className="flex items-center gap-2 text-[13px] font-medium">
          <span className="text-base leading-none">🧺</span> Réduire les plis
        </p>
        <Segmented<WrinkleLevel>
          size="sm"
          value={settings.wrinkles ?? "leger"}
          onChange={(v) => onChange({ wrinkles: v })}
          disabled={off}
          options={[
            { value: "off", label: "Off" },
            { value: "leger", label: "Léger" },
            { value: "moyen", label: "Moyen", disabled: preserve, title: preserve ? "Désactive « Préserver l'article » pour aller plus loin" : undefined },
            { value: "fort", label: "Fort", disabled: preserve, title: preserve ? "Désactive « Préserver l'article » pour aller plus loin" : undefined },
          ]}
        />
      </div>

      <div className="space-y-2">
        <p className="flex items-center gap-2 text-[13px] font-medium">
          <span className="text-base leading-none">🖼️</span> Arrière-plan
        </p>
        <Segmented<BackgroundMode>
          size="sm"
          value={settings.background ?? "clean"}
          onChange={(v) => onChange({ background: v })}
          disabled={off}
          options={[
            { value: "keep", label: "Conserver" },
            { value: "clean", label: "Nettoyer" },
            { value: "neutral", label: "Fond propre", disabled: !segmentationOk, title: !segmentationOk ? "Détourage incertain sur cette photo" : undefined },
          ]}
        />
        {settings.background === "neutral" && (
          <div className="flex gap-2 pt-1">
            {SWATCHES.map((s) => (
              <button
                key={s.value}
                title={s.label}
                onClick={() => onChange({ background_color: s.value })}
                className={cn(
                  "size-8 rounded-full border transition-transform hover:scale-105",
                  settings.background_color === s.value ? "border-ink ring-2 ring-ink ring-offset-2" : "border-line-strong",
                )}
                style={{ background: s.color }}
              />
            ))}
          </div>
        )}
      </div>

      <RangeField
        label="Teinte"
        value={settings.hue}
        min={-10}
        max={10}
        onChange={(v) => onChange({ hue: v })}
        disabled={off}
        format={(v) => (v > 0 ? `+${v}` : String(v))}
        hint={
          preserve
            ? `Volontairement limitée (±${PRESERVE_LIMITS.hue} en mode Préserver) pour ne pas tromper l'acheteur.`
            : "Volontairement limitée pour ne pas tromper l'acheteur."
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
        <div className="space-y-2">
          <p className="text-[13px] font-medium">Cadrage</p>
          <Segmented<Aspect>
            size="sm"
            value={settings.aspect}
            onChange={(v) => onChange({ aspect: v })}
            disabled={off}
            options={[
              { value: "3:4", label: "3:4" },
              { value: "4:5", label: "4:5" },
              { value: "1:1", label: "1:1" },
              { value: "original", label: "Libre" },
            ]}
          />
        </div>
        <div className="space-y-2">
          <p className="text-[13px] font-medium">Résolution</p>
          <Segmented<UpscaleMode>
            size="sm"
            value={settings.upscale}
            onChange={(v) => onChange({ upscale: v })}
            disabled={off}
            options={[
              { value: "auto", label: "Auto" },
              { value: "off", label: "Non" },
              { value: "2x", label: "×2" },
            ]}
          />
        </div>
      </div>
    </div>
  );
}
