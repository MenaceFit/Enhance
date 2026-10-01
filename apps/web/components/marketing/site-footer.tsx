import Link from "next/link";
import { Logo } from "@/components/logo";
import { BRAND } from "@/lib/brand";

export function SiteFooter() {
  return (
    <footer className="border-t border-line">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-14 sm:px-6 md:grid-cols-[1.5fr_1fr_1fr]">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-sm text-sm leading-relaxed text-muted">
            Améliorer la présentation, jamais falsifier l&apos;article. Un outil pensé pour les vendeurs de seconde main.
          </p>
        </div>
        <div className="space-y-2 text-sm">
          <p className="font-medium">Produit</p>
          <Link href="/app/enhance" className="block text-muted hover:text-ink">Améliorer une photo</Link>
          <Link href="/demo" className="block text-muted hover:text-ink">Démonstration</Link>
          <Link href="/#tarifs" className="block text-muted hover:text-ink">Tarifs</Link>
        </div>
        <div className="space-y-2 text-sm">
          <p className="font-medium">Légal</p>
          <Link href="/privacy" className="block text-muted hover:text-ink">Confidentialité &amp; RGPD</Link>
          <Link href="/terms" className="block text-muted hover:text-ink">Conditions d&apos;utilisation</Link>
          <a href={`mailto:${BRAND.supportEmail}`} className="block text-muted hover:text-ink">Contact</a>
        </div>
      </div>
      <div className="mx-auto max-w-6xl px-4 pb-10 text-xs text-subtle sm:px-6">
        © {new Date().getFullYear()} {BRAND.name}. Service indépendant, non affilié à Vinted. Vinted est une marque de Vinted UAB.
      </div>
    </footer>
  );
}
