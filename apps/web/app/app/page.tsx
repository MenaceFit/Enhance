"use client";

import { ArrowRight, Clock, Images, Sparkles } from "lucide-react";
import Link from "next/link";
import { Dropzone } from "@/components/dropzone";
import { PhotoCard, PhotoGrid } from "@/components/photo-card";
import { ButtonLink } from "@/components/ui/button";
import { useDashboard, useMe } from "@/lib/hooks";
import { formatDuration } from "@/lib/utils";

function Stat({ icon: Icon, label, value, hint }: { icon: typeof Images; label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-2xl border border-line p-5">
      <div className="flex items-center gap-2 text-xs text-muted">
        <Icon className="size-3.5" /> {label}
      </div>
      <p className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const { data: me, isLoading } = useMe();
  const user = me?.user;
  const { data } = useDashboard(!!user);
  const name = user?.display_name ? ` ${user.display_name}` : "";

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-8 sm:py-10">
      <p className="text-sm text-muted">Bonjour{name} 👋</p>
      <h1 className="mt-1 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Améliore ta prochaine photo</h1>

      <div className="mt-8">
        <Dropzone />
      </div>

      {user?.is_guest && (
        <div className="mt-6 flex flex-col gap-3 rounded-2xl bg-mist p-5 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-graphite">
            Tu utilises le mode invité : tes photos sont gardées 2 jours. Crée un compte gratuit pour les conserver et obtenir
            5 améliorations par mois.
          </p>
          <ButtonLink href="/signup?next=/app" size="sm">Créer mon compte</ButtonLink>
        </div>
      )}

      {user && (
        <div className="mt-10 grid gap-4 sm:grid-cols-3">
          <Stat icon={Images} label="Photos améliorées" value={String(data?.photos_enhanced ?? "–")} />
          <Stat
            icon={Sparkles}
            label="Crédits restants"
            value={data ? String(data.credits.remaining) : "–"}
            hint={data ? `sur ${data.credits.allowance} · offre ${data.credits.plan_name}` : undefined}
          />
          <Stat
            icon={Clock}
            label="Temps économisé"
            value={data ? formatDuration(data.minutes_saved) : "–"}
            hint="estimé par rapport à une retouche manuelle"
          />
        </div>
      )}

      {!!data?.recent_photos.length && (
        <section className="mt-12">
          <div className="mb-5 flex items-center justify-between">
            <h2 className="text-lg font-semibold tracking-tight">Photos récentes</h2>
            <Link href="/app/photos" className="flex items-center gap-1 text-sm text-muted hover:text-ink">
              Tout voir <ArrowRight className="size-3.5" />
            </Link>
          </div>
          <PhotoGrid>
            {data.recent_photos.map((p) => (
              <PhotoCard key={p.id} photo={p} refreshKey="/dashboard" />
            ))}
          </PhotoGrid>
        </section>
      )}

      {!isLoading && !user && (
        <p className="mt-8 text-center text-sm text-muted">
          Aucune inscription nécessaire pour essayer. Déjà un compte ?{" "}
          <Link href="/login" className="font-medium text-ink underline underline-offset-4">Se connecter</Link>
        </p>
      )}
    </div>
  );
}
