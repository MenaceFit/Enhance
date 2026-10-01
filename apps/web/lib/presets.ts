"use client";

import useSWR from "swr";
import { fetcher } from "./api";
import type { Intensity, Settings } from "./types";

type Preset = Pick<Settings, "cleaning" | "placement" | "light" | "color" | "sharpness" | "wrinkles" | "background">;

// Mirror of the API presets (served by GET /config) used until the config is loaded.
const FALLBACK: Record<Intensity, Preset> = {
  original: { cleaning: 0, placement: 0, light: 0, color: 0, sharpness: 0, wrinkles: "off", background: "keep" },
  leger: { cleaning: 50, placement: 40, light: 40, color: 25, sharpness: 20, wrinkles: "leger", background: "keep" },
  naturel: { cleaning: 70, placement: 60, light: 60, color: 40, sharpness: 35, wrinkles: "leger", background: "clean" },
  premium: { cleaning: 85, placement: 75, light: 72, color: 55, sharpness: 45, wrinkles: "moyen", background: "clean" },
  studio: { cleaning: 100, placement: 85, light: 80, color: 62, sharpness: 55, wrinkles: "moyen", background: "neutral" },
};

export const INTENSITIES: { value: Intensity; label: string }[] = [
  { value: "original", label: "Original" },
  { value: "leger", label: "Léger" },
  { value: "naturel", label: "Naturel" },
  { value: "premium", label: "Premium" },
  { value: "studio", label: "Studio" },
];

export const PRESERVE_LIMITS = { color: 55, hue: 6 };

export function usePresets(): Record<Intensity, Preset> {
  const { data } = useSWR<{ presets: Record<Intensity, Preset> }>("/config", fetcher, { revalidateOnFocus: false });
  return data?.presets ?? FALLBACK;
}

export function withIntensity(s: Settings, intensity: Intensity, presets: Record<Intensity, Preset>): Settings {
  return { ...s, intensity, ...presets[intensity] };
}

export function vintedPreset(presets: Record<Intensity, Preset>): Settings {
  return {
    intensity: "naturel",
    preserve_article: true,
    ...presets.naturel,
    background_color: "auto",
    hue: 0,
    aspect: "3:4",
    upscale: "auto",
    retouch_specks: [],
  };
}

export function sameSettings(a: Settings | null | undefined, b: Settings | null | undefined) {
  if (!a || !b) return false;
  const keys = Object.keys(a) as (keyof Settings)[];
  return keys.every((k) => JSON.stringify(a[k]) === JSON.stringify(b[k]));
}
