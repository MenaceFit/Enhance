import { ButtonLink } from "@/components/ui/button";
import { Logo } from "@/components/logo";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-transparent bg-paper/80 backdrop-blur-xl supports-[backdrop-filter]:bg-paper/70">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <nav className="hidden items-center gap-8 text-sm text-muted md:flex">
          <a href="#fonctionnement" className="transition-colors hover:text-ink">Fonctionnement</a>
          <a href="#exemples" className="transition-colors hover:text-ink">Exemples</a>
          <a href="#principes" className="transition-colors hover:text-ink">Principes</a>
          <a href="#tarifs" className="transition-colors hover:text-ink">Tarifs</a>
        </nav>
        <div className="flex items-center gap-2">
          <ButtonLink href="/login" variant="ghost" size="sm" className="hidden sm:inline-flex">
            Se connecter
          </ButtonLink>
          <ButtonLink href="/app/enhance" size="sm">
            Essayer
          </ButtonLink>
        </div>
      </div>
    </header>
  );
}
