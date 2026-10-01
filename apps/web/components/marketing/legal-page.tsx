import type { ReactNode } from "react";
import { SiteFooter } from "./site-footer";
import { SiteHeader } from "./site-header";

export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-2xl px-4 py-16 sm:px-6">
        <h1 className="text-4xl font-semibold tracking-[-0.03em]">{title}</h1>
        <p className="mt-2 text-sm text-muted">Dernière mise à jour : {updated}</p>
        <div className="prose-legal mt-10 space-y-6 text-[15px] leading-relaxed text-graphite [&_h2]:mt-10 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-ink [&_li]:ml-5 [&_li]:list-disc [&_ul]:space-y-1.5">
          {children}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
