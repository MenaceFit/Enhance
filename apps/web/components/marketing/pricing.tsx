"use client";

import { Check } from "lucide-react";
import useSWR from "swr";
import { ButtonLink } from "@/components/ui/button";
import { fetcher } from "@/lib/api";
import type { Plan } from "@/lib/types";
import { cn, formatPrice } from "@/lib/utils";

const FALLBACK: Plan[] = [
  { code: "free", name: "Free", monthly_credits: 5, price_cents: 0 },
  { code: "starter", name: "Starter", monthly_credits: 100, price_cents: 599 },
  { code: "pro", name: "Pro", monthly_credits: 500, price_cents: 1499 },
  { code: "business", name: "Business", monthly_credits: 2000, price_cents: 3999 },
];

const PERKS: Record<string, string[]> = {
  free: ["Toutes les améliorations", "Détection des imperfections", "Export JPG, PNG, WEBP"],
  starter: ["Multi-photos (12 par annonce)", "Cohérence entre les photos", "Historique des versions"],
  pro: ["Exports Haute qualité & Maximum", "Traitement prioritaire", "Fond propre illimité"],
  business: ["Volume pour boutiques", "Plusieurs marketplaces", "Support dédié"],
};

export function Pricing({ ctaHref = "/app/enhance" }: { ctaHref?: string }) {
  const { data } = useSWR<{ plans: Plan[] }>("/billing/plans", fetcher, { fallbackData: { plans: FALLBACK } });
  const plans = data?.plans?.length ? data.plans : FALLBACK;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {plans.map((p) => {
        const featured = p.code === "pro";
        return (
          <div
            key={p.code}
            className={cn(
              "flex flex-col rounded-2xl border p-6 transition-shadow",
              featured ? "border-ink bg-ink text-paper shadow-lift" : "border-line bg-paper hover:shadow-soft",
            )}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">{p.name}</h3>
              {featured && <span className="rounded-full bg-paper/15 px-2 py-0.5 text-[11px]">Populaire</span>}
            </div>
            <p className="mt-6 text-4xl font-semibold tracking-tight tabular-nums">
              {formatPrice(p.price_cents)}
              {p.price_cents > 0 && <span className={cn("ml-1 text-sm font-normal", featured ? "text-paper/60" : "text-muted")}>/mois</span>}
            </p>
            <p className={cn("mt-1 text-sm", featured ? "text-paper/70" : "text-muted")}>
              {p.monthly_credits.toLocaleString("fr-FR")} photos par mois
            </p>
            <ul className="mt-6 flex-1 space-y-2.5 text-sm">
              {(PERKS[p.code] ?? []).map((perk) => (
                <li key={perk} className="flex gap-2">
                  <Check className={cn("mt-0.5 size-4 shrink-0", featured ? "text-paper" : "text-ink")} strokeWidth={2} />
                  <span className={featured ? "text-paper/85" : "text-graphite"}>{perk}</span>
                </li>
              ))}
            </ul>
            <ButtonLink
              href={p.price_cents === 0 ? ctaHref : "/app/billing"}
              variant={featured ? "secondary" : p.price_cents === 0 ? "primary" : "secondary"}
              className={cn("mt-8 w-full", featured && "border-transparent")}
            >
              {p.price_cents === 0 ? "Commencer gratuitement" : `Choisir ${p.name}`}
            </ButtonLink>
          </div>
        );
      })}
    </div>
  );
}
