"use client";

import { Dropzone } from "@/components/dropzone";
import { useMe } from "@/lib/hooks";

export default function EnhancePage() {
  const { data } = useMe();
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-8 sm:py-16">
      <h1 className="text-center text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Améliore ta photo Vinted en quelques secondes.</h1>
      <p className="mx-auto mt-3 max-w-md text-center text-muted">
        Nettoyage, lumière, couleurs et cadrage, sans jamais modifier ton article.
      </p>
      <div className="mt-10">
        <Dropzone />
      </div>
      <div className="mt-8 grid gap-3 text-sm text-muted sm:grid-cols-3">
        {[
          ["1 photo", "→ éditeur avant/après"],
          ["2 à 12 photos", "→ une annonce cohérente"],
          [data?.credits ? `${data.credits.remaining} crédit${data.credits.remaining > 1 ? "s" : ""}` : "3 photos offertes", "1 crédit par photo"],
        ].map(([a, b]) => (
          <div key={a} className="rounded-2xl bg-mist px-4 py-3">
            <span className="font-medium text-ink">{a}</span> <span>{b}</span>
          </div>
        ))}
      </div>
      <p className="mt-8 text-center text-xs text-subtle">
        🔒 Tes photos sont privées, jamais indexées, et supprimées automatiquement selon tes paramètres.
      </p>
    </div>
  );
}
