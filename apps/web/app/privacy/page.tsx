import type { Metadata } from "next";
import { LegalPage } from "@/components/marketing/legal-page";
import { BRAND } from "@/lib/brand";

export const metadata: Metadata = { title: "Confidentialité & RGPD" };

export default function Privacy() {
  return (
    <LegalPage title="Politique de confidentialité" updated="1er octobre 2026">
      <p>
        {BRAND.name} traite tes photos uniquement pour te fournir le service d&apos;amélioration. Ce document explique quelles
        données nous traitons, pourquoi, combien de temps, et comment exercer tes droits (RGPD).
      </p>
      <h2>Données traitées</h2>
      <ul>
        <li>Les photos que tu importes et les versions améliorées produites.</li>
        <li>Les résultats d&apos;analyse associés (type de vêtement, couleurs, imperfections détectées).</li>
        <li>Ton adresse e-mail et un mot de passe chiffré (argon2) si tu crées un compte.</li>
        <li>L&apos;historique de tes crédits et de ton abonnement.</li>
        <li>Les métadonnées des photos (dont la position GPS) sont supprimées de toutes les exportations.</li>
      </ul>
      <h2>Finalités et base légale</h2>
      <ul>
        <li>Fournir le service (exécution du contrat).</li>
        <li>Facturation et prévention des abus (obligation légale, intérêt légitime).</li>
        <li>Mesure d&apos;audience anonyme, uniquement avec ton consentement.</li>
      </ul>
      <p>Tes photos ne sont jamais utilisées pour entraîner des modèles, ni vendues, ni rendues publiques.</p>
      <h2>Conservation</h2>
      <ul>
        <li>Photos : supprimées automatiquement après la durée que tu choisis dans tes paramètres (30 jours par défaut, de 1 à 365 jours).</li>
        <li>Sessions invitées : 2 jours.</li>
        <li>Exports téléchargeables : 24 heures.</li>
      </ul>
      <h2>Sécurité</h2>
      <ul>
        <li>Stockage privé et chiffré, isolé par utilisateur ; accès uniquement par liens signés temporaires.</li>
        <li>Aucune indexation publique ; connexions chiffrées (HTTPS).</li>
        <li>Hébergement dans l&apos;Union européenne recommandé et configurable.</li>
      </ul>
      <h2>Sous-traitants</h2>
      <p>
        Selon la configuration, certaines analyses peuvent être confiées à des fournisseurs d&apos;IA sous contrat de
        sous-traitance (par exemple pour identifier le type de vêtement). La liste à jour est disponible sur demande.
      </p>
      <h2>Tes droits</h2>
      <ul>
        <li>Accès et portabilité : exporte toutes tes données depuis Paramètres → Confidentialité.</li>
        <li>Effacement : supprime ton compte et toutes tes photos en un clic, immédiatement.</li>
        <li>Opposition et retrait du consentement : à tout moment depuis tes paramètres.</li>
        <li>Réclamation : auprès de la CNIL (cnil.fr).</li>
      </ul>
      <p>Contact : {BRAND.supportEmail}</p>
    </LegalPage>
  );
}
