"use client";

import { CreditCard, Folder, Home, Images, LogOut, Menu, Settings, Shield, Sparkles, Star, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { useSWRConfig } from "swr";
import { Logo } from "@/components/logo";
import { ButtonLink } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useMe } from "@/lib/hooks";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/app", label: "Dashboard", icon: Home, exact: true },
  { href: "/app/photos", label: "Mes photos", icon: Images },
  { href: "/app/enhance", label: "Améliorer", icon: Sparkles },
  { href: "/app/projects", label: "Mes projets", icon: Folder },
  { href: "/app/favorites", label: "Favoris", icon: Star },
  { href: "/app/settings", label: "Paramètres", icon: Settings },
  { href: "/app/billing", label: "Abonnement", icon: CreditCard },
];

function NavLinks({ onNavigate, isAdmin }: { onNavigate?: () => void; isAdmin?: boolean }) {
  const path = usePathname();
  const items = isAdmin ? [...NAV, { href: "/admin", label: "Administration", icon: Shield }] : NAV;
  return (
    <nav className="space-y-0.5">
      {items.map(({ href, label, icon: Icon, ...rest }) => {
        const active = "exact" in rest && rest.exact ? path === href : path === href || path.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "flex h-10 items-center gap-3 rounded-xl px-3 text-sm transition-colors",
              active ? "bg-mist font-medium text-ink" : "text-muted hover:bg-mist/70 hover:text-ink",
            )}
          >
            <Icon className="size-[18px]" strokeWidth={active ? 2 : 1.6} />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function CreditsCard() {
  const { data } = useMe();
  if (!data?.credits) return null;
  const { remaining, allowance, plan_name } = data.credits;
  const pct = allowance ? Math.min(100, (remaining / allowance) * 100) : 0;
  return (
    <div className="rounded-2xl border border-line p-4">
      <div className="flex items-baseline justify-between">
        <p className="text-xs text-muted">Crédits · {plan_name}</p>
        <p className="text-sm font-semibold tabular-nums">
          {remaining}
          <span className="font-normal text-muted">/{allowance}</span>
        </p>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-ink" style={{ width: `${pct}%` }} />
      </div>
      {data.user?.is_guest ? (
        <ButtonLink href="/signup" size="sm" className="mt-3 w-full">
          Créer un compte gratuit
        </ButtonLink>
      ) : (
        remaining <= Math.max(2, allowance * 0.2) && (
          <ButtonLink href="/app/billing" variant="secondary" size="sm" className="mt-3 w-full">
            Plus de crédits
          </ButtonLink>
        )
      )}
    </div>
  );
}

function UserRow() {
  const { data } = useMe();
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const user = data?.user;
  if (!user) {
    return (
      <Link href="/login" className="block rounded-xl px-3 py-2 text-sm text-muted hover:bg-mist hover:text-ink">
        Se connecter
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-3 px-1">
      <div className="flex size-8 items-center justify-center rounded-full bg-ink text-xs font-semibold text-paper">
        {(user.display_name || user.email || "I").slice(0, 1).toUpperCase()}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{user.is_guest ? "Invité" : user.display_name || user.email}</p>
        <p className="truncate text-xs text-muted">{user.is_guest ? "Photos gardées 2 jours" : user.email}</p>
      </div>
      {!user.is_guest && (
        <button
          title="Se déconnecter"
          className="rounded-lg p-2 text-muted hover:bg-mist hover:text-ink"
          onClick={async () => {
            await api("/auth/logout", { method: "POST" });
            await mutate(() => true, undefined, { revalidate: true });
            router.push("/");
          }}
        >
          <LogOut className="size-4" />
        </button>
      )}
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { data } = useMe();
  const isAdmin = !!data?.user?.is_admin;
  return (
    <div className="min-h-screen bg-paper lg:grid lg:grid-cols-[256px_1fr]">
      <aside className="sticky top-0 hidden h-screen flex-col gap-6 border-r border-line px-4 py-5 lg:flex">
        <Logo href="/app" className="px-2" />
        <NavLinks isAdmin={isAdmin} />
        <div className="mt-auto space-y-4">
          <CreditsCard />
          <UserRow />
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-paper/90 px-4 backdrop-blur lg:hidden">
        <Logo href="/app" />
        <button onClick={() => setOpen(true)} className="rounded-lg p-2 hover:bg-mist" aria-label="Menu">
          <Menu className="size-5" />
        </button>
      </header>
      {open && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button aria-label="Fermer" className="absolute inset-0 animate-fade-in bg-ink/30" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 right-0 flex w-72 animate-fade-in flex-col gap-6 bg-paper p-4 shadow-lift">
            <div className="flex items-center justify-between">
              <Logo href="/app" />
              <button onClick={() => setOpen(false)} className="rounded-lg p-2 hover:bg-mist" aria-label="Fermer">
                <X className="size-5" />
              </button>
            </div>
            <NavLinks onNavigate={() => setOpen(false)} isAdmin={isAdmin} />
            <div className="mt-auto space-y-4">
              <CreditsCard />
              <UserRow />
            </div>
          </div>
        </div>
      )}

      <main className="min-w-0">{children}</main>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 border-b border-line px-4 py-6 sm:flex-row sm:items-end sm:justify-between sm:px-8 sm:py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.03em] sm:text-3xl">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}
