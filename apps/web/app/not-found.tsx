import { ButtonLink } from "@/components/ui/button";
import { Logo } from "@/components/logo";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 text-center">
      <Logo />
      <div>
        <p className="text-5xl font-semibold tracking-tight">404</p>
        <p className="mt-2 text-muted">Cette page n&apos;existe pas (ou plus).</p>
      </div>
      <ButtonLink href="/">Retour à l&apos;accueil</ButtonLink>
    </div>
  );
}
