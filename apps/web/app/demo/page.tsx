import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import { DemoGallery, type DemoItem } from "@/components/marketing/demo-gallery";
import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { ButtonLink } from "@/components/ui/button";
import manifest from "@/public/demo/manifest.json";

export const metadata: Metadata = { title: "Démonstration" };

const LABELS: Record<string, string> = { hoodie: "Hoodie", sneakers: "Sneakers", jean: "Jean", veste: "Veste" };

export default function Demo() {
  const items: DemoItem[] = manifest.map((m) => ({ ...m, label: LABELS[m.name] ?? m.garment }));
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <p className="text-sm text-muted">Démonstration</p>
        <h1 className="mt-2 max-w-2xl text-4xl font-semibold tracking-[-0.03em] sm:text-5xl">
          De la photo prise en vitesse à la photo d&apos;annonce.
        </h1>
        <p className="mt-4 max-w-xl text-muted">
          Lumière jaune d&apos;intérieur, vêtement incliné, poussières, sous-exposition : voici ce que fait le moteur, et ce
          qu&apos;il refuse de faire.
        </p>
        <div className="mt-14">
          <DemoGallery items={items} />
        </div>
        <div className="mt-20 flex flex-col items-start gap-4 rounded-3xl bg-mist p-8 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold tracking-tight">À toi d&apos;essayer avec ta propre photo.</h2>
            <p className="mt-1 text-sm text-muted">Sans inscription · 3 photos offertes</p>
          </div>
          <ButtonLink href="/app/enhance" size="lg">
            Améliorer ma photo <ArrowRight className="size-4" />
          </ButtonLink>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
