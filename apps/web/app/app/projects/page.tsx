"use client";

/* eslint-disable @next/next/no-img-element */
import Link from "next/link";
import { PageHeader } from "@/components/app-shell";
import { EmptyState } from "@/components/photo-card";
import { ButtonLink } from "@/components/ui/button";
import { useMe, useProjects } from "@/lib/hooks";
import { relativeTime } from "@/lib/utils";

export default function ProjectsPage() {
  const { data: me } = useMe();
  const { data } = useProjects(!!me?.user);
  return (
    <div>
      <PageHeader
        title="Mes projets"
        subtitle="Une annonce = un projet de 1 à 12 photos cohérentes."
        actions={<ButtonLink href="/app/enhance" size="sm">+ Nouvelle annonce</ButtonLink>}
      />
      <div className="px-4 py-8 sm:px-8">
        {(data?.projects.length === 0 || (me && !me.user)) && (
          <EmptyState title="Aucun projet" action={<ButtonLink href="/app/enhance">Importer des photos</ButtonLink>}>
            Importe plusieurs photos d&apos;un même article pour créer une annonce harmonisée.
          </EmptyState>
        )}
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {data?.projects.map((p) => (
            <Link key={p.id} href={`/app/projects/${p.id}`} className="group animate-fade-up rounded-2xl border border-line p-3 transition-shadow hover:shadow-soft">
              <div className="aspect-[4/3] overflow-hidden rounded-xl bg-mist">
                {p.cover_url ? (
                  <img src={p.cover_url} alt="" className="size-full object-cover transition-transform duration-500 group-hover:scale-[1.02]" />
                ) : (
                  <div className="skeleton size-full" />
                )}
              </div>
              <div className="flex items-center justify-between px-1 pb-1 pt-3">
                <div>
                  <p className="font-medium">{p.name}</p>
                  <p className="text-xs text-muted">
                    {p.photo_count} photo{p.photo_count > 1 ? "s" : ""} · {relativeTime(p.created_at)}
                  </p>
                </div>
                {p.ready_count < p.photo_count && <span className="text-xs text-muted animate-pulse-soft">en cours…</span>}
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
