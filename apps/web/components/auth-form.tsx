"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSWRConfig } from "swr";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

function safeNext(next?: string) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/app";
}

export function AuthForm({ mode, next }: { mode: "login" | "signup"; next?: string }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [accept, setAccept] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (mode === "signup") {
        await api("/auth/signup", { method: "POST", json: { email, password, display_name: name || null, accept_privacy: accept } });
      } else {
        await api("/auth/login", { method: "POST", json: { email, password } });
      }
      await mutate(() => true, undefined, { revalidate: true });
      router.push(safeNext(next));
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const field = "h-11 w-full rounded-xl border border-line bg-paper px-3.5 text-[15px] outline-none transition focus:border-ink";
  return (
    <form onSubmit={submit} className="space-y-5">
      <div>
        <h1 className="text-3xl font-semibold tracking-[-0.03em]">{mode === "signup" ? "Crée ton compte" : "Bon retour 👋"}</h1>
        <p className="mt-2 text-sm text-muted">
          {mode === "signup"
            ? "Garde tes photos et profite de 5 améliorations gratuites chaque mois. Tes photos déjà améliorées sont conservées."
            : "Connecte-toi pour retrouver tes photos et tes annonces."}
        </p>
      </div>
      {mode === "signup" && (
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">Prénom <span className="font-normal text-muted">(optionnel)</span></span>
          <input className={field} value={name} onChange={(e) => setName(e.target.value)} autoComplete="given-name" maxLength={80} />
        </label>
      )}
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">E-mail</span>
        <input className={field} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
      </label>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">Mot de passe</span>
        <input
          className={field}
          type="password"
          required
          minLength={mode === "signup" ? 8 : 1}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete={mode === "signup" ? "new-password" : "current-password"}
        />
        {mode === "signup" && <span className="text-xs text-muted">8 caractères minimum.</span>}
      </label>
      {mode === "signup" && (
        <label className="flex items-start gap-2.5 text-sm text-graphite">
          <input type="checkbox" className="mt-0.5 size-4 accent-ink" checked={accept} onChange={(e) => setAccept(e.target.checked)} required />
          <span>
            J&apos;accepte les <Link href="/terms" className="underline underline-offset-4">conditions</Link> et la{" "}
            <Link href="/privacy" className="underline underline-offset-4">politique de confidentialité</Link>.
          </span>
        </label>
      )}
      {error && <p className="rounded-xl bg-[#fbf3f3] px-3.5 py-2.5 text-sm text-[#9b2c2c]">{error}</p>}
      <Button type="submit" size="lg" className="w-full" loading={loading}>
        {mode === "signup" ? "Créer mon compte" : "Se connecter"}
      </Button>
      <p className="text-center text-sm text-muted">
        {mode === "signup" ? (
          <>Déjà un compte ? <Link href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-ink">Se connecter</Link></>
        ) : (
          <>Pas encore de compte ? <Link href={`/signup${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-ink">Créer un compte</Link></>
        )}
      </p>
    </form>
  );
}
