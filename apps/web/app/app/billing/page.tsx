"use client";

import { Check } from "lucide-react";
import useSWR, { useSWRConfig } from "swr";
import { PageHeader } from "@/components/app-shell";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card } from "@/components/ui/controls";
import { useToast } from "@/components/ui/toast";
import { api, fetcher } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import type { Plan } from "@/lib/types";
import { cn, formatDate, formatPrice } from "@/lib/utils";

type Summary = {
  plan_code: string;
  plan_name: string;
  allowance: number;
  used: number;
  remaining: number;
  period_end: string;
  history: { delta: number; reason: string; at: string }[];
  payments_enabled: boolean;
};

const REASONS: Record<string, string> = { enhance: "Photo améliorée", refund: "Crédit rendu (échec)", bonus: "Crédits offerts" };

export default function BillingPage() {
  const toast = useToast();
  const { mutate } = useSWRConfig();
  const { data: me } = useMe();
  const { data: plans } = useSWR<{ plans: Plan[] }>("/billing/plans", fetcher);
  const { data: summary, mutate: refresh } = useSWR<Summary>(me?.user ? "/billing" : null, fetcher);

  async function choose(code: string) {
    try {
      const res = await api<{ mode: string; url?: string }>("/billing/checkout", { method: "POST", json: { plan_code: code } });
      if (res.mode === "redirect" && res.url) window.location.assign(res.url);
      else {
        toast("Offre activée", "success");
        refresh();
        mutate("/auth/me");
      }
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  const pct = summary ? Math.min(100, (summary.used / Math.max(1, summary.allowance)) * 100) : 0;
  return (
    <div>
      <PageHeader title="Abonnement" subtitle="1 crédit = 1 photo améliorée. Retouches et exports inclus." />
      <div className="mx-auto max-w-5xl space-y-8 px-4 py-8 sm:px-8">
        {summary && (
          <Card className="p-6">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <p className="text-sm text-muted">Offre actuelle</p>
                <p className="mt-1 text-2xl font-semibold tracking-tight">{summary.plan_name}</p>
              </div>
              <p className="text-sm text-muted">
                <b className="text-ink tabular-nums">{summary.remaining}</b> crédits restants · renouvellement le {formatDate(summary.period_end, { day: "numeric", month: "long" })}
              </p>
            </div>
            <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-line">
              <div className="h-full rounded-full bg-ink" style={{ width: `${pct}%` }} />
            </div>
            <p className="mt-2 text-xs text-muted">{summary.used} / {summary.allowance} utilisés ce mois-ci</p>
          </Card>
        )}

        {me?.user?.is_guest && (
          <div className="flex flex-col gap-3 rounded-2xl bg-mist p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-graphite">Crée un compte gratuit pour obtenir 5 améliorations par mois et choisir une offre.</p>
            <ButtonLink href="/signup?next=/app/billing" size="sm">Créer un compte</ButtonLink>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {plans?.plans.map((p) => {
            const current = summary?.plan_code === p.code;
            return (
              <div key={p.code} className={cn("flex flex-col rounded-2xl border p-5", current ? "border-ink" : "border-line")}>
                <p className="text-sm font-medium">{p.name}</p>
                <p className="mt-4 text-3xl font-semibold tracking-tight tabular-nums">
                  {formatPrice(p.price_cents)}
                  {p.price_cents > 0 && <span className="ml-1 text-sm font-normal text-muted">/mois</span>}
                </p>
                <p className="mt-1 flex items-center gap-1.5 text-sm text-muted">
                  <Check className="size-3.5" /> {p.monthly_credits.toLocaleString("fr-FR")} photos / mois
                </p>
                <div className="mt-6 flex-1" />
                {current ? (
                  <span className="flex h-10 items-center justify-center rounded-full bg-mist text-sm font-medium">Offre actuelle</span>
                ) : (
                  <Button variant={p.code === "pro" ? "primary" : "secondary"} disabled={!me?.user || me.user.is_guest} onClick={() => choose(p.code)}>
                    Choisir
                  </Button>
                )}
              </div>
            );
          })}
        </div>
        {summary && !summary.payments_enabled && (
          <p className="text-center text-xs text-subtle">Mode démonstration : le paiement n&apos;est pas configuré, les offres s&apos;activent immédiatement.</p>
        )}

        {!!summary?.history.length && (
          <Card className="p-6">
            <h2 className="font-semibold tracking-tight">Historique</h2>
            <ul className="mt-4 divide-y divide-line text-sm">
              {summary.history.map((h, i) => (
                <li key={i} className="flex justify-between py-2.5">
                  <span>{REASONS[h.reason] ?? h.reason}</span>
                  <span className="flex gap-6 text-muted">
                    <span>{formatDate(h.at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
                    <span className={cn("w-8 text-right font-mono tabular-nums", h.delta > 0 ? "text-ok" : "text-ink")}>{h.delta > 0 ? `+${h.delta}` : h.delta}</span>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}
