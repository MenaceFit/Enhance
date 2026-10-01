"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const KEY = "vai_consent_v1";

/** Only an essential session cookie is used by default. Optional measurement needs consent. */
export function ConsentBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(KEY)) {
        const t = setTimeout(() => setVisible(true), 800);
        return () => clearTimeout(t);
      }
    } catch {
      /* storage unavailable: stay silent, nothing optional is enabled */
    }
  }, []);

  const choose = (granted: boolean) => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ analytics: granted, at: new Date().toISOString() }));
    } catch {
      /* ignore */
    }
    setVisible(false);
    api("/account/consents", { method: "POST", json: { kind: "analytics", granted } }).catch(() => {});
  };

  if (!visible) return null;
  return (
    <div className="fixed inset-x-3 bottom-3 z-50 animate-fade-up rounded-2xl border border-line bg-paper/95 p-4 shadow-lift backdrop-blur sm:inset-x-auto sm:bottom-5 sm:left-5 sm:max-w-sm">
      <p className="text-[13px] leading-relaxed text-graphite">
        Nous utilisons uniquement un cookie de session indispensable. Avec ton accord, nous mesurons aussi l&apos;usage du
        service de façon anonyme pour l&apos;améliorer.{" "}
        <Link href="/privacy" className="underline underline-offset-4">En savoir plus</Link>
      </p>
      <div className="mt-3 flex gap-2">
        <button onClick={() => choose(false)} className="h-8 flex-1 rounded-full border border-line text-[13px] font-medium hover:bg-mist">
          Refuser
        </button>
        <button onClick={() => choose(true)} className="h-8 flex-1 rounded-full bg-ink text-[13px] font-medium text-paper hover:bg-ink-soft">
          Accepter
        </button>
      </div>
    </div>
  );
}
