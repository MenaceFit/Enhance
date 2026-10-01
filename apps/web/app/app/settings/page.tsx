"use client";

import { Download, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { PageHeader } from "@/components/app-shell";
import { Button, ButtonLink } from "@/components/ui/button";
import { Card, ProgressBar, Segmented, Toggle } from "@/components/ui/controls";
import { useToast } from "@/components/ui/toast";
import { api, fetcher, waitForJob } from "@/lib/api";
import { INTENSITIES } from "@/lib/presets";
import type { Intensity, Job, Me } from "@/lib/types";
import { triggerDownload } from "@/lib/utils";

type Account = Me & { consents: Record<string, boolean>; privacy_policy_version: string };

const RETENTION = [7, 30, 90, 180, 365];

function Section({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <Card className="p-6">
      <h2 className="font-semibold tracking-tight">{title}</h2>
      {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      <div className="mt-5 space-y-5">{children}</div>
    </Card>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const toast = useToast();
  const { mutate: globalMutate } = useSWRConfig();
  const { data, mutate, error } = useSWR<Account>("/account", fetcher);
  const [name, setName] = useState("");
  const [nameFor, setNameFor] = useState<string | null>(null);
  const [exportJob, setExportJob] = useState<Job | null>(null);
  const [confirm, setConfirm] = useState("");

  // initialise the field once per loaded account (state adjusted during render, no effect)
  if (data?.user && nameFor !== data.user.id) {
    setNameFor(data.user.id);
    setName(data.user.display_name ?? "");
  }

  if (error?.status === 401) {
    return (
      <div className="mx-auto max-w-md px-4 py-20 text-center">
        <p className="text-lg font-semibold">Connecte-toi pour accéder à tes paramètres.</p>
        <ButtonLink href="/login?next=/app/settings" className="mt-6">Se connecter</ButtonLink>
      </div>
    );
  }
  if (!data?.user) return <div className="p-8"><div className="skeleton h-8 w-48 rounded-lg" /></div>;
  const user = data.user;

  async function update(body: Record<string, unknown>) {
    try {
      await api("/account", { method: "PATCH", json: body });
      await mutate();
      globalMutate("/auth/me");
      toast("Enregistré", "success");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  }

  return (
    <div>
      <PageHeader title="Paramètres" subtitle={user.is_guest ? "Mode invité" : user.email ?? undefined} />
      <div className="mx-auto max-w-3xl space-y-6 px-4 py-8 sm:px-8">
        {user.is_guest && (
          <div className="flex flex-col gap-3 rounded-2xl bg-mist p-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-graphite">Crée un compte pour choisir la durée de conservation et garder tes photos.</p>
            <ButtonLink href="/signup?next=/app/settings" size="sm">Créer un compte</ButtonLink>
          </div>
        )}

        <Section title="Profil">
          <div className="flex gap-2">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Prénom"
              maxLength={80}
              className="h-10 flex-1 rounded-xl border border-line px-3.5 text-sm outline-none focus:border-ink"
            />
            <Button variant="secondary" onClick={() => update({ display_name: name })}>Enregistrer</Button>
          </div>
        </Section>

        <Section title="Amélioration par défaut" description="Appliquée automatiquement à chaque nouvelle photo.">
          <Toggle
            checked={user.preferences.default_preserve ?? true}
            onChange={(v) => update({ default_preserve: v })}
            label="🔒 Préserver l'article"
            description="Recommandé. Garantit qu'aucune modification trompeuse n'est appliquée."
          />
          <div className="space-y-2">
            <p className="text-sm font-medium">Intensité</p>
            <Segmented<Intensity>
              value={user.preferences.default_intensity ?? "naturel"}
              onChange={(v) => update({ default_intensity: v })}
              options={INTENSITIES.filter((i) => i.value !== "original")}
            />
          </div>
        </Section>

        <Section title="Confidentialité" description="Tes photos sont privées, chiffrées et accessibles uniquement par des liens temporaires.">
          <div className="space-y-2">
            <p className="text-sm font-medium">Suppression automatique des photos après</p>
            <Segmented<string>
              value={String(user.retention_days)}
              onChange={(v) => update({ retention_days: Number(v) })}
              disabled={user.is_guest}
              options={RETENTION.map((d) => ({ value: String(d), label: d === 365 ? "1 an" : `${d} j` }))}
            />
          </div>
          <Toggle
            checked={!!data.consents.analytics}
            onChange={async (v) => {
              await api("/account/consents", { method: "POST", json: { kind: "analytics", granted: v } });
              mutate();
            }}
            label="Mesure d'audience anonyme"
            description="Nous aide à améliorer le service. Aucune donnée n'est revendue."
          />
          <Toggle
            checked={!!data.consents.marketing}
            onChange={async (v) => {
              await api("/account/consents", { method: "POST", json: { kind: "marketing", granted: v } });
              mutate();
            }}
            label="Nouveautés par e-mail"
            description="Au plus une fois par mois."
          />
        </Section>

        <Section title="Mes données" description="Tes droits RGPD, en un clic.">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium">Exporter mes données</p>
              <p className="text-xs text-muted">Archive .zip : compte, consentements, crédits, photos originales et améliorées.</p>
            </div>
            <Button
              variant="secondary"
              disabled={user.is_guest || !!exportJob}
              onClick={async () => {
                try {
                  const job = await api<Job>("/account/export", { method: "POST" });
                  setExportJob(job);
                  const done = await waitForJob(job.id, setExportJob);
                  if (done.result.download_url) triggerDownload(done.result.download_url);
                } catch (e) {
                  toast((e as Error).message, "error");
                } finally {
                  setExportJob(null);
                }
              }}
            >
              <Download className="size-4" /> Exporter
            </Button>
          </div>
          {exportJob && <ProgressBar value={exportJob.progress} />}
          <div className="rounded-2xl border border-[#ecd2d2] p-4">
            <p className="text-sm font-medium">Supprimer mon compte</p>
            <p className="mt-1 text-xs text-muted">Suppression immédiate et définitive de ton compte, de tes photos et de tes exports. Tape SUPPRIMER pour confirmer.</p>
            <div className="mt-3 flex gap-2">
              <input
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="SUPPRIMER"
                className="h-10 flex-1 rounded-xl border border-line px-3.5 text-sm outline-none focus:border-ink"
              />
              <Button
                variant="danger"
                disabled={confirm.trim().toUpperCase() !== "SUPPRIMER"}
                onClick={async () => {
                  await api("/account/delete", { method: "POST", json: { confirm } });
                  await globalMutate(() => true, undefined, { revalidate: true });
                  router.push("/");
                }}
              >
                <Trash2 className="size-4" /> Supprimer
              </Button>
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}
