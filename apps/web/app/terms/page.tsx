import type { Metadata } from "next";
import { LegalPage } from "@/components/marketing/legal-page";
import { BRAND } from "@/lib/brand";

export const metadata: Metadata = { title: "Conditions d'utilisation" };

export default function Terms() {
  return (
    <LegalPage title="Conditions d'utilisation" updated="1er octobre 2026">
      <p>{BRAND.name} est un outil d&apos;amélioration de photos pour vendeurs de seconde main.</p>
      <h2>Usage loyal</h2>
      <p>
        Le service améliore la présentation des photos sans modifier l&apos;article. Tu t&apos;engages à ne pas l&apos;utiliser pour
        tromper un acheteur : les imperfections signalées doivent rester visibles dans ton annonce lorsque c&apos;est
        pertinent. Tu restes seul responsable du contenu de tes annonces.
      </p>
      <h2>Tes contenus</h2>
      <p>Tu conserves tous les droits sur tes photos. Tu nous accordes uniquement le droit de les traiter pour fournir le service.</p>
      <h2>Crédits et abonnements</h2>
      <p>
        Un crédit correspond à une photo améliorée. Les crédits mensuels sont renouvelés à chaque période et ne sont pas
        reportés. Les abonnements sont sans engagement et résiliables à tout moment ; une photo dont le traitement échoue
        est automatiquement recréditée.
      </p>
      <h2>Disponibilité</h2>
      <p>Nous faisons notre maximum pour assurer la disponibilité du service, sans garantie d&apos;absence d&apos;interruption.</p>
      <h2>Marques</h2>
      <p>{BRAND.name} est un service indépendant, non affilié à Vinted. Vinted est une marque de Vinted UAB.</p>
    </LegalPage>
  );
}
