export type Intensity = "original" | "leger" | "naturel" | "premium" | "studio";
export type WrinkleLevel = "off" | "leger" | "moyen" | "fort";
export type BackgroundMode = "keep" | "clean" | "neutral";
export type BackgroundColor = "auto" | "off_white" | "light_gray" | "light_beige";
export type Aspect = "original" | "3:4" | "4:5" | "1:1";
export type UpscaleMode = "auto" | "off" | "2x";

export interface Settings {
  intensity: Intensity;
  preserve_article: boolean;
  cleaning: number | null;
  placement: number | null;
  light: number | null;
  color: number | null;
  sharpness: number | null;
  wrinkles: WrinkleLevel | null;
  background: BackgroundMode | null;
  background_color: BackgroundColor;
  hue: number;
  aspect: Aspect;
  upscale: UpscaleMode;
  retouch_specks: number[];
}

export interface User {
  id: string;
  email: string | null;
  display_name: string | null;
  is_guest: boolean;
  is_admin: boolean;
  plan_code: string;
  preferences: { default_intensity?: Intensity; default_preserve?: boolean };
  retention_days: number;
  created_at: string;
}

export interface Credits {
  plan_code: string;
  plan_name: string;
  allowance: number;
  used: number;
  remaining: number;
  period_end: string;
}

export interface Me {
  user: User | null;
  credits: Credits | null;
}

export interface BBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Defect {
  id: string;
  kind: "stain" | "discoloration" | "hole" | "snag" | "wear" | "pilling" | "speck";
  label: string;
  bbox: BBox;
  confidence: number;
  area: number;
  removable_as_dust: boolean;
  speck_id: number | null;
}

export interface Analysis {
  width: number;
  height: number;
  quality: { score: number; breakdown: Record<string, number>; issues: string[] };
  segmentation: { confidence: number; touches: Record<string, boolean> };
  clothing: {
    category: string;
    label: string;
    confidence: number;
    dominant_colors: { hex: string | null; name: string; share: number }[];
    pattern: string;
    texture: string;
    features: Record<string, unknown>;
    provider: string;
  };
  illuminant: { cast_label: string | null; cast_strength: number; confidence: number };
  composition: { tilt_deg: number; tilt_confidence: number };
  specks: { id: number; kind: string; region: string; confidence: number }[];
  defects: Defect[];
  warnings: string[];
  consistency?: { gains: number[]; exposure_factor: number; group_size: number } | null;
}

export interface Fidelity {
  score: number;
  mean_delta_e: number;
  hue_shift_deg: number;
  chroma_ratio: number;
  dominant_before: string;
  dominant_after: string;
  passed: boolean;
  warning: string | null;
}

export interface Structure {
  score: number;
  silhouette_iou: number;
  edge_recall: number;
  detail_correlation: number;
  passed: boolean;
  issues: string[];
}

export interface Metrics {
  fidelity: Fidelity | null;
  structure: Structure | null;
  quality: { score: number; breakdown: Record<string, number>; issues: string[] } | null;
  quality_before: number | null;
  applied: Record<string, boolean>;
  warnings: string[];
  geometry: { angle: number; crop: [number, number, number, number]; padded: boolean; output: [number, number]; background: string };
  upscale_factor: number;
  removed_specks: number;
  auto_adjustments: string[];
  needs_validation: boolean;
  capped: string[];
  export?: { format: string; quality: string; width: number; height: number };
}

export interface Version {
  id: string;
  kind: "ai" | "edited" | "final";
  label: string;
  created_at: string;
  settings: Settings;
  metrics: Metrics;
  width: number;
  height: number;
  after_url: string;
  before_url: string;
  thumb_url: string;
}

export interface Job {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed";
  progress: number;
  stage: string | null;
  stage_label: string | null;
  error: string | null;
  photo_id: string | null;
  project_id: string | null;
  created_at: string;
  finished_at: string | null;
  result: Record<string, unknown> & { download_url?: string; filename?: string };
}

export interface PhotoSummary {
  id: string;
  project_id: string;
  position: number;
  filename: string;
  status: "queued" | "processing" | "ready" | "failed";
  error: string | null;
  width: number;
  height: number;
  is_favorite: boolean;
  created_at: string;
  expires_at: string | null;
  thumb_url: string | null;
  original_thumb_url: string | null;
  garment: string | null;
  quality_before: number | null;
  quality_after: number | null;
  fidelity: number | null;
  defects_count: number;
  checklist: { cleaned: boolean; colors: boolean; framing: boolean; background: boolean };
}

export interface PhotoDetail extends PhotoSummary {
  original_preview_url: string | null;
  analysis: Analysis | null;
  defect_state: Record<string, "acknowledged" | "kept">;
  current_version: Version | null;
  versions: Version[];
  latest_job: Job | null;
  siblings: string[];
}

export interface Project {
  id: string;
  name: string;
  marketplace: string;
  consistency_enabled: boolean;
  settings: Partial<Settings>;
  created_at: string;
  updated_at: string | null;
  photo_count: number;
  ready_count: number;
  cover_url: string | null;
  photos?: PhotoSummary[];
  active_jobs?: Job[];
}

export interface Preview {
  after_url: string;
  before_url: string;
  width: number;
  height: number;
  settings: Settings;
  metrics: Metrics;
}

export interface Plan {
  code: string;
  name: string;
  monthly_credits: number;
  price_cents: number;
  currency?: string;
  is_active?: boolean;
}

export interface Dashboard {
  photos_enhanced: number;
  credits: { remaining: number; allowance: number; plan_name: string };
  minutes_saved: number;
  recent_photos: PhotoSummary[];
  recent_projects: Project[];
}
