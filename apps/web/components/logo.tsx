import Link from "next/link";
import { BRAND } from "@/lib/brand";
import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="9" fill="currentColor" />
      <path d="M9 11.5 14.2 22h1.6L23 9.5" stroke="var(--color-paper)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <circle cx="23.2" cy="20.8" r="1.7" fill="var(--color-paper)" />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2.5 text-ink", className)}>
      <LogoMark />
      <span className="text-[15px] font-semibold tracking-[-0.02em]">{BRAND.name}</span>
    </Link>
  );
}
