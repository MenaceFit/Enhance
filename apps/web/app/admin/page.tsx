"use client";

import { ArrowLeft, Play } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { CostPerDay, PhotosPerDay } from "@/components/admin/charts";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Badge, Card, Segmented } from "@/components/ui/controls";
import { useToast } from "@/components/ui/toast";
import { api, fetcher } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Plan } from "@/lib/types";
import { cn, formatPrice, relativeTime } from "@/lib/utils";

type Metrics = {
  period_days: number;
  users: { total: number; registered: number; guests: number; new: number };
  photos: { processed: number; avg_per_day: number; per_day: { date: string; photos: number; failed: number; cost_cents: number }[] };
  processing: { avg_ms: number | null; p95_ms: number | null; error_rate: number };
  ai_cost: { total_cents: number; per_photo_cents: number; models: { provider: string; capability: string; model: string | null; calls: number; failure_rate: number; cost_cents: number; avg_ms: number }[] };
  credits: { consumed: number };
  revenue: { mrr_cents: number; paying_users: number; conversion_free_to_paid: number; plans: Record<string, number> };
};
type Provider = { name: string; display_name: string; available: boolean; capabilities: string[]; generative: string[]; cost_cents: Record<string, number>; models: Record<string, string | null> };
type Run = { id: string; status: string; profiles: Record<string, Record<string, string>>; image_count: number; created_at: string; summary: Record<string, number | string | null>[] | null };

const compact = (n: number) => new Intl.NumberFormat("fr-FR", { notation: n >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
const pct = (v: number) => `${(v * 100).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`;
const eur = (cents: number) => (cents / 100).toLocaleString("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: cents < 100 ? 3 : 2 });

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-line p-5">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

function PlansEditor() {
  const toast = useToast();
  const { data, mutate } = useSWR<{ plans: (Plan & { is_active: boolean })[] }>("/admin/plans", fetcher);
  const [draft, setDraft] = useState<Record<string, { monthly_credits: number; price_cents: number }>>({});
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-muted">
        <tr><th className="pb-2 font-medium">Offre</th><th className="pb-2 font-medium">Photos / mois</th><th className="pb-2 font-medium">Prix (centimes)</th><th /></tr>
      </thead>
      <tbody className="divide-y divide-line">
        {data?.plans.map((p) => {
          const d = draft[p.code] ?? { monthly_credits: p.monthly_credits, price_cents: p.price_cents };
          const changed = d.monthly_credits !== p.monthly_credits || d.price_cents !== p.price_cents;
          return (
            <tr key={p.code}>
              <td className="py-2.5 font-medium">{p.name}</td>
              {(["monthly_credits", "price_cents"] as const).map((k) => (
                <td key={k} className="py-2.5 pr-3">
                  <input
                    type="number"
                    min={0}
                    value={d[k]}
                    onChange={(e) => setDraft({ ...draft, [p.code]: { ...d, [k]: Number(e.target.value) } })}
                    className="h-9 w-28 rounded-lg border border-line px-2.5 tabular-nums outline-none focus:border-ink"
                  />
                </td>
              ))}
              <td className="py-2.5 text-right">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={!changed}
                  onClick={async () => {
                    await api(`/admin/plans/${p.code}`, { method: "PATCH", json: d });
                    mutate();
                    toast(`${p.name} mis à jour`, "success");
                  }}
                >
                  Enregistrer
                </Button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Benchmarks({ presets }: { presets: string[] }) {
  const toast = useToast();
  const { data, mutate } = useSWR<{ runs: Run[] }>("/admin/benchmarks", fetcher, {
    refreshInterval: (d) => (d?.runs.some((r) => r.status === "queued" || r.status === "running") ? 1500 : 0),
  });
  const [profiles, setProfiles] = useState<string[]>(["local"]);
  const [count, setCount] = useState(6);
  const latest = data?.runs[0];
  const cols: [string, string, (v: number | string | null) => string][] = [
    ["profile", "Profil", (v) => String(v)],
    ["quality_gain", "Gain qualité", (v) => (v == null ? "–" : `+${v}`)],
    ["fidelity", "Fidélité", (v) => (v == null ? "–" : `${v} %`)],
    ["structure", "Structure", (v) => (v == null ? "–" : String(v))],
    ["duration_ms_p50", "Durée p50", (v) => (v == null ? "–" : `${(Number(v) / 1000).toFixed(1)} s`)],
    ["cost_cents_per_image", "Coût / photo", (v) => (v == null ? "–" : eur(Number(v)))],
    ["error_rate", "Erreurs", (v) => (v == null ? "–" : pct(Number(v)))],
    ["dust_recall", "Poussières", (v) => (v == null ? "–" : pct(Number(v)))],
    ["stain_reported_rate", "Défauts signalés", (v) => (v == null ? "–" : pct(Number(v)))],
  ];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <p className="text-xs text-muted">Profils à comparer</p>
          <div className="flex flex-wrap gap-1.5">
            {presets.map((p) => (
              <button
                key={p}
                onClick={() => setProfiles((s) => (s.includes(p) ? s.filter((x) => x !== p) : [...s, p]))}
                className={cn("h-8 rounded-full border px-3 text-xs", profiles.includes(p) ? "border-ink bg-ink text-paper" : "border-line hover:border-line-strong")}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
        <label className="space-y-1.5">
          <span className="block text-xs text-muted">Images de test</span>
          <input type="number" min={1} max={40} value={count} onChange={(e) => setCount(Number(e.target.value))} className="h-8 w-20 rounded-lg border border-line px-2.5 text-sm tabular-nums" />
        </label>
        <Button
          size="sm"
          disabled={!profiles.length}
          onClick={async () => {
            try {
              await api("/admin/benchmarks", { method: "POST", json: { profiles, synthetic_count: count } });
              mutate();
            } catch (e) {
              toast((e as Error).message, "error");
            }
          }}
        >
          <Play className="size-3.5" /> Lancer la comparaison
        </Button>
      </div>
      {latest && (
        <div>
          <p className="mb-2 text-xs text-muted">
            Dernière comparaison · {relativeTime(latest.created_at)} · {latest.image_count || count} images ·{" "}
            <Badge tone={latest.status === "succeeded" ? "ok" : latest.status === "failed" ? "warn" : "neutral"}>{latest.status}</Badge>
          </p>
          {latest.summary && (
            <div className="overflow-x-auto rounded-xl border border-line">
              <table className="w-full whitespace-nowrap text-sm">
                <thead className="bg-mist text-left text-xs text-muted">
                  <tr>{cols.map(([k, l]) => <th key={k} className="px-3 py-2 font-medium">{l}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {latest.summary.map((row) => (
                    <tr key={String(row.profile)}>
                      {cols.map(([k, , f]) => <td key={k} className={cn("px-3 py-2 tabular-nums", k === "profile" && "font-medium")}>{f(row[k] ?? null)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminPage() {
  const { data: me } = useMe();
  const [days, setDays] = useState("30");
  const allowed = !!me?.user?.is_admin;
  const { data: m, isValidating } = useSWR<Metrics>(allowed ? `/admin/metrics?days=${days}` : null, fetcher, { keepPreviousData: true });
  const { data: prov } = useSWR<{ providers: Provider[]; routing: Record<string, string>; preset_profiles: Record<string, unknown> }>(allowed ? "/admin/providers" : null, fetcher);

  if (me && !allowed) {
    return (
      <div className="mx-auto max-w-md px-4 py-24 text-center">
        <p className="text-lg font-semibold">Accès réservé aux administrateurs.</p>
        <Link href="/app" className="mt-4 inline-block text-sm underline">Retour</Link>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-paper/90 px-4 backdrop-blur sm:px-8">
        <div className="flex items-center gap-4">
          <Logo href="/admin" />
          <span className="rounded-full bg-mist px-2.5 py-0.5 text-xs text-muted">Administration</span>
        </div>
        <Link href="/app" className="flex items-center gap-1.5 text-sm text-muted hover:text-ink"><ArrowLeft className="size-4" /> Application</Link>
      </header>

      <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-8">
        {/* one filter row, scoping everything below */}
        <div className="flex items-center gap-3">
          <Segmented value={days} onChange={setDays} options={[{ value: "7", label: "7 jours" }, { value: "30", label: "30 jours" }, { value: "90", label: "90 jours" }]} />
        </div>

        <div className={cn("space-y-8 transition-opacity", isValidating && m && "opacity-60")}>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
            <Tile label="Utilisateurs" value={m ? compact(m.users.total) : "–"} hint={m ? `${m.users.registered} inscrit${m.users.registered > 1 ? "s" : ""} · +${m.users.new} sur la période` : undefined} />
            <Tile label="Photos traitées" value={m ? compact(m.photos.processed) : "–"} hint={m ? `${m.photos.avg_per_day} / jour en moyenne` : undefined} />
            <Tile label="Coût IA" value={m ? eur(m.ai_cost.total_cents) : "–"} hint={m ? `${eur(m.ai_cost.per_photo_cents)} par photo` : undefined} />
            <Tile label="Temps moyen de traitement" value={m?.processing.avg_ms ? `${(m.processing.avg_ms / 1000).toFixed(1)} s` : "–"} hint={m?.processing.p95_ms ? `p95 ${(m.processing.p95_ms / 1000).toFixed(1)} s` : undefined} />
            <Tile label="Taux d'erreur" value={m ? pct(m.processing.error_rate) : "–"} />
            <Tile label="Crédits consommés" value={m ? compact(m.credits.consumed) : "–"} />
            <Tile label="Conversion Free → Paid" value={m ? pct(m.revenue.conversion_free_to_paid) : "–"} hint={m ? `${m.revenue.paying_users} clients payants` : undefined} />
            <Tile label="MRR" value={m ? formatPrice(m.revenue.mrr_cents) : "–"} />
            <Tile label="Invités" value={m ? compact(m.users.guests) : "–"} />
            <Tile label="Offres" value={m ? Object.entries(m.revenue.plans).map(([k, v]) => `${k} ${v}`).join(" · ") || "–" : "–"} />
          </div>

          <Card className="p-6">
            <h2 className="font-semibold tracking-tight">Photos par jour</h2>
            <p className="mb-4 text-xs text-muted">Traitements terminés, par jour de création</p>
            {m && <PhotosPerDay days={m.photos.per_day} />}
          </Card>

          <Card className="p-6">
            <h2 className="font-semibold tracking-tight">Coût IA par jour</h2>
            <p className="mb-4 text-xs text-muted">Somme des appels aux fournisseurs, en euros</p>
            {m && <CostPerDay days={m.photos.per_day} />}
          </Card>

          <Card className="p-6">
            <h2 className="mb-4 font-semibold tracking-tight">Modèles IA utilisés</h2>
            <div className="overflow-x-auto">
              <table className="w-full whitespace-nowrap text-sm">
                <thead className="text-left text-xs text-muted">
                  <tr>{["Fournisseur", "Capacité", "Modèle", "Appels", "Échecs", "Durée moy.", "Coût"].map((h) => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}</tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {m?.ai_cost.models.map((r) => (
                    <tr key={`${r.provider}-${r.capability}-${r.model}`}>
                      <td className="py-2 pr-4 font-medium">{r.provider}</td>
                      <td className="py-2 pr-4 text-muted">{r.capability}</td>
                      <td className="py-2 pr-4 font-mono text-xs">{r.model ?? "–"}</td>
                      <td className="py-2 pr-4 tabular-nums">{r.calls}</td>
                      <td className="py-2 pr-4 tabular-nums">{pct(r.failure_rate)}</td>
                      <td className="py-2 pr-4 tabular-nums">{Math.round(r.avg_ms)} ms</td>
                      <td className="py-2 tabular-nums">{eur(r.cost_cents)}</td>
                    </tr>
                  ))}
                  {m && !m.ai_cost.models.length && <tr><td colSpan={7} className="py-4 text-center text-muted">Aucun appel sur la période.</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <div className="grid gap-8 lg:grid-cols-2">
          <Card className="p-6">
            <h2 className="font-semibold tracking-tight">Fournisseurs IA</h2>
            <p className="mb-4 text-xs text-muted">
              Routage actuel : {prov && Object.keys(prov.routing).length ? Object.entries(prov.routing).map(([k, v]) => `${k} → ${v}`).join(", ") : "tout en local"} (variable AI_ROUTING)
            </p>
            <ul className="space-y-3">
              {prov?.providers.map((p) => (
                <li key={p.name} className="rounded-xl border border-line p-3">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">{p.display_name}</p>
                    <Badge tone={p.available ? "ok" : "neutral"}>{p.available ? "disponible" : "non configuré"}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    {p.capabilities.join(" · ")}
                    {p.generative.length > 0 && <> · <span className="text-warn">génératif ({p.generative.join(", ")}) : bloqué en mode Préserver</span></>}
                  </p>
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-6">
            <h2 className="mb-4 font-semibold tracking-tight">Offres & limites</h2>
            <PlansEditor />
          </Card>
        </div>

        <Card className="p-6">
          <h2 className="font-semibold tracking-tight">Comparer des modèles IA</h2>
          <p className="mb-5 text-xs text-muted">
            Lance chaque profil de routage sur les mêmes images de test (vérité terrain connue) : qualité, fidélité, vitesse, coût, taux d&apos;erreur.
          </p>
          <Benchmarks presets={Object.keys(prov?.preset_profiles ?? { local: {} })} />
        </Card>
      </div>
    </div>
  );
}
