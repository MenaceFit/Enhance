"use client";

import { PageHeader } from "@/components/app-shell";
import { EmptyState, PhotoCard, PhotoGrid } from "@/components/photo-card";
import { ButtonLink } from "@/components/ui/button";
import { useMe, usePhotos } from "@/lib/hooks";

export function PhotoLibrary({ favorites }: { favorites: boolean }) {
  const { data: me } = useMe();
  const { data, isLoading } = usePhotos(favorites, !!me?.user);
  const key = `/photos?favorites=${favorites}&limit=120`;
  return (
    <div>
      <PageHeader
        title={favorites ? "Favoris" : "Mes photos"}
        subtitle={data ? `${data.total} photo${data.total > 1 ? "s" : ""}` : undefined}
        actions={<ButtonLink href="/app/enhance" size="sm">+ Importer</ButtonLink>}
      />
      <div className="px-4 py-8 sm:px-8">
        {isLoading && (
          <PhotoGrid>
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="skeleton aspect-[3/4] rounded-2xl" />
            ))}
          </PhotoGrid>
        )}
        {data && data.photos.length === 0 && (
          <EmptyState
            title={favorites ? "Aucun favori pour l'instant" : "Aucune photo pour l'instant"}
            action={!favorites && <ButtonLink href="/app/enhance">Améliorer ma première photo</ButtonLink>}
          >
            {favorites ? "Ajoute une étoile sur tes meilleures photos pour les retrouver ici." : "Dépose une photo pour commencer."}
          </EmptyState>
        )}
        {me && !me.user && (
          <EmptyState title="Aucune photo pour l'instant" action={<ButtonLink href="/app/enhance">Améliorer ma première photo</ButtonLink>} />
        )}
        {!!data?.photos.length && (
          <PhotoGrid>
            {data.photos.map((p) => (
              <PhotoCard key={p.id} photo={p} refreshKey={key} />
            ))}
          </PhotoGrid>
        )}
      </div>
    </div>
  );
}
