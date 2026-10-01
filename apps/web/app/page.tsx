import { ArrowRight, Eye, Lock, Palette, ScanSearch, ShieldCheck, Sparkles } from "lucide-react";
import { CompareSlider } from "@/components/compare-slider";
import { DemoGallery, type DemoItem } from "@/components/marketing/demo-gallery";
import { Pricing } from "@/components/marketing/pricing";
import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";
import { ButtonLink } from "@/components/ui/button";
import manifest from "@/public/demo/manifest.json";

const LABELS: Record<string, string> = { hoodie: "Hoodie", sneakers: "Sneakers", jean: "Jean", veste: "Veste" };
const demos: DemoItem[] = manifest.map((m) => ({ ...m, label: LABELS[m.name] ?? m.garment }));
const hero = demos[0];

const DOES = [
  "Nettoie les poussières, cheveux et fibres parasites",
  "Corrige la lumière, la balance des blancs et le contraste",
  "Redresse, recentre et recadre le vêtement",
  "Réduit légèrement les plis gênants",
  "Simplifie ou nettoie l'arrière-plan",
  "Améliore la netteté et la résolution",
];
const NEVER = [
  "Modifier le modèle, la coupe ou la taille",
  "Inventer ou changer un logo, une marque",
  "Changer volontairement la couleur réelle",
  "Effacer une tache, un trou ou une usure",
  "Recréer une manche hors cadre",
  "Transformer un vêtement usé en neuf",
];

const FAQ = [
  {
    q: "Est-ce que l'IA modifie mon vêtement ?",
    a: "Non. Chaque traitement est une correction mesurable des pixels d'origine : lumière, couleurs, cadrage, poussières. Aucune partie du vêtement n'est générée. Un contrôle structurel compare chaque résultat à l'original et réduit automatiquement l'intensité si une modification semble excessive.",
  },
  {
    q: "Et si mon article a une tache ?",
    a: "Elle reste visible. L'outil détecte les imperfections possibles (taches, trous, décolorations), les signale et te recommande de les montrer dans ton annonce. Elles sont protégées de tous les traitements.",
  },
  {
    q: "Mes photos sont-elles privées ?",
    a: "Oui. Elles sont stockées de façon chiffrée, accessibles uniquement par des liens temporaires signés, jamais indexées, et supprimées automatiquement selon la durée de conservation que tu choisis. Tu peux tout exporter ou tout supprimer en un clic.",
  },
  {
    q: "Faut-il créer un compte ?",
    a: "Non pour essayer : dépose ta photo, c'est tout. Crée un compte gratuit pour garder tes photos plus longtemps et profiter de 5 améliorations par mois.",
  },
];

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        {/* Hero */}
        <section className="relative overflow-hidden">
          <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-12 sm:px-6 md:pt-20 lg:grid-cols-[1.15fr_1fr] lg:gap-14 lg:pb-28">
            <div className="animate-fade-up">
              <p className="mb-6 inline-flex items-center gap-2 rounded-full border border-line px-3 py-1 text-xs text-muted">
                <Sparkles className="size-3.5" /> IA d&apos;amélioration, pas de génération
              </p>
              <h1 className="text-[42px] font-semibold leading-[1.02] tracking-[-0.045em] sm:text-6xl lg:text-[62px]">
                Tes photos Vinted,
                <br />
                <span className="text-muted">mais en mieux.</span>
              </h1>
              <p className="mt-6 max-w-lg text-lg leading-relaxed text-graphite">
                Améliore automatiquement tes photos avec l&apos;IA. Nettoie, recadre, corrige la lumière et les couleurs tout en
                conservant l&apos;apparence réelle de ton article.
              </p>
              <div className="mt-9 flex flex-col gap-3 sm:flex-row">
                <ButtonLink href="/app/enhance" size="lg">
                  Améliorer ma première photo <ArrowRight className="size-4" />
                </ButtonLink>
                <ButtonLink href="/demo" variant="secondary" size="lg">
                  Voir une démonstration
                </ButtonLink>
              </div>
              <ul className="mt-10 flex flex-wrap gap-x-6 gap-y-2 text-[13px] text-muted">
                <li className="flex items-center gap-1.5"><Palette className="size-3.5" /> Fidélité couleur mesurée</li>
                <li className="flex items-center gap-1.5"><Eye className="size-3.5" /> Défauts jamais masqués</li>
                <li className="flex items-center gap-1.5"><Lock className="size-3.5" /> Photos privées</li>
              </ul>
            </div>
            {hero && (
              <div className="relative mx-auto w-full max-w-md animate-fade-up [animation-delay:120ms] lg:max-w-none">
                <CompareSlider
                  before={`/demo/${hero.name}-before.webp`}
                  after={`/demo/${hero.name}-after.webp`}
                  width={hero.width}
                  height={hero.height}
                  initial={42}
                  priority
                  className="shadow-lift"
                />
                <div className="absolute -bottom-5 left-1/2 flex -translate-x-1/2 items-center gap-3 whitespace-nowrap rounded-full border border-line bg-paper/95 px-4 py-2 text-xs shadow-soft backdrop-blur">
                  <span>🎨 Fidélité couleur : <b className="tabular-nums">{hero.fidelity} %</b></span>
                  <span className="h-3 w-px bg-line" />
                  <span>Qualité <b className="tabular-nums">{hero.quality_before} → {hero.quality_after}</b></span>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* How it works */}
        <section id="fonctionnement" className="border-t border-line bg-mist/60">
          <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
            <h2 className="max-w-2xl text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">
              Prends ta photo. Upload-la. L&apos;IA s&apos;occupe du reste.
            </h2>
            <div className="mt-14 grid gap-4 md:grid-cols-3">
              {[
                ["01", "Dépose ta photo", "Glisse, colle ou choisis jusqu'à 12 photos. JPG, PNG, WEBP ou HEIC, directement depuis ton téléphone."],
                ["02", "Analyse automatique", "Type de vêtement, contours, poussières, imperfections, lumière, couleurs et cadrage sont analysés en quelques secondes."],
                ["03", "Une photo propre et fidèle", "Compare avant/après, ajuste si tu veux, puis télécharge ta photo prête pour l'annonce."],
              ].map(([n, t, d]) => (
                <div key={n} className="rounded-2xl border border-line bg-paper p-7">
                  <p className="font-mono text-xs text-subtle">{n}</p>
                  <h3 className="mt-8 text-lg font-semibold tracking-tight">{t}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">{d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Before / after */}
        <section id="exemples" className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
            <div className="mb-14 max-w-2xl">
              <p className="text-sm text-muted">Avant / Après</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Fais glisser. Compare. Juge par toi-même.</h2>
            </div>
            <DemoGallery items={demos} />
          </div>
        </section>

        {/* Principles */}
        <section id="principes" className="border-t border-line bg-ink text-paper">
          <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
            <p className="text-sm text-paper/50">Notre principe</p>
            <h2 className="mt-2 max-w-3xl text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">
              Améliorer la présentation,
              <br />
              jamais falsifier l&apos;article.
            </h2>
            <div className="mt-14 grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-paper/10 bg-paper/[0.04] p-7">
                <p className="mb-5 text-sm font-medium">L&apos;IA fait</p>
                <ul className="space-y-3 text-[15px] text-paper/80">
                  {DOES.map((d) => (
                    <li key={d} className="flex gap-3"><span className="text-paper">✓</span>{d}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-2xl border border-paper/10 bg-paper/[0.04] p-7">
                <p className="mb-5 text-sm font-medium">L&apos;IA ne fait jamais</p>
                <ul className="space-y-3 text-[15px] text-paper/80">
                  {NEVER.map((d) => (
                    <li key={d} className="flex gap-3"><span className="text-paper/40">✕</span>{d}</li>
                  ))}
                </ul>
              </div>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              {[
                [Palette, "Fidélité couleur", "Chaque résultat reçoit un score de fidélité (CIEDE2000). Si la couleur bouge trop, la correction est réduite."],
                [ScanSearch, "Détection des imperfections", "Taches, trous, décolorations : signalés et protégés de tous les traitements. Nous recommandons de les montrer."],
                [ShieldCheck, "Préserver l'article", "Activé par défaut : aucune génération, aucune modification de forme, aucun changement important de couleur."],
              ].map(([Icon, t, d]) => {
                const I = Icon as typeof Palette;
                return (
                  <div key={t as string} className="rounded-2xl border border-paper/10 p-7">
                    <I className="size-5 text-paper/70" strokeWidth={1.6} />
                    <h3 className="mt-6 font-semibold">{t as string}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-paper/60">{d as string}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Pricing */}
        <section id="tarifs" className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
            <div className="mb-14 flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div>
                <p className="text-sm text-muted">Tarifs</p>
                <h2 className="mt-2 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Simple, sans engagement.</h2>
              </div>
              <p className="max-w-sm text-sm text-muted">1 crédit = 1 photo améliorée. Les retouches et exports d&apos;une photo déjà améliorée sont gratuits.</p>
            </div>
            <Pricing />
          </div>
        </section>

        {/* FAQ */}
        <section className="border-t border-line bg-mist/60">
          <div className="mx-auto grid max-w-6xl gap-12 px-4 py-24 sm:px-6 md:grid-cols-[1fr_1.4fr]">
            <h2 className="text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">Questions fréquentes</h2>
            <div className="divide-y divide-line border-y border-line">
              {FAQ.map((f) => (
                <details key={f.q} className="group py-5">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium">
                    {f.q}
                    <span className="text-muted transition-transform group-open:rotate-45">+</span>
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-muted">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-line">
          <div className="mx-auto flex max-w-6xl flex-col items-center px-4 py-24 text-center sm:px-6">
            <h2 className="text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">Ta prochaine annonce mérite mieux.</h2>
            <p className="mt-4 text-muted">Sans inscription. Résultat en quelques secondes.</p>
            <ButtonLink href="/app/enhance" size="lg" className="mt-8">
              Améliorer ma première photo <ArrowRight className="size-4" />
            </ButtonLink>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
