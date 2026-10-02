# Vinted AI — Photo Enhancer

SaaS qui transforme une photo de vêtement prise rapidement au téléphone en une photo **propre, lumineuse, bien cadrée et fidèle**, prête pour une annonce Vinted.

> **Améliorer la présentation, jamais falsifier l'article.**
> Aucune partie du vêtement n'est générée : chaque traitement est une correction mesurable des pixels d'origine, contrôlée par un score de fidélité couleur et une vérification structurelle anti-hallucination. Les imperfections (taches, trous) sont détectées, signalées et protégées, jamais effacées.

```
Upload → Analyse IA → Amélioration → Avant/Après → Réglages → Export
```

| | |
|---|---|
| **Frontend** | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 (`apps/web`) |
| **Backend** | Python 3.11 · FastAPI · SQLAlchemy 2 · Alembic (`apps/api`) |
| **Données** | PostgreSQL (SQLite possible en local) |
| **Stockage** | S3 / Cloudflare R2 / MinIO, ou disque local — privé, URLs signées |
| **File d'attente** | Redis + Celery (ou pool de threads intégré en développement) |
| **Moteur image** | OpenCV / NumPy, non génératif, derrière une abstraction `ImageEnhancementProvider` |

---

## Démarrage rapide

### Sans Docker (développement)

Prérequis : Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 20.9+. **Tutoriel détaillé pas à pas (Windows, macOS, Linux) : [`INSTALL.md`](INSTALL.md).**

```bash
make install            # dépendances API + web
make api                # http://localhost:8000/api/docs  (SQLite + file d'attente intégrée)
make web                # http://localhost:3000
```

Aucune base ni Redis n'est nécessaire : par défaut l'API utilise SQLite (`apps/api/var/dev.db`), le stockage local (`apps/api/var/storage`) et un pool de threads pour les traitements. Pour devenir administrateur, crée un compte avec un e-mail listé dans `ADMIN_EMAILS` (`admin@example.com` dans `.env.example`).

### Avec Docker (stack complète)

```bash
cp .env.example .env    # renseigne au minimum SECRET_KEY
docker compose up --build
```

Services : PostgreSQL, Redis, migration Alembic, API, worker Celery, Celery beat (purge RGPD), web ; photos dans un volume Docker privé (ou S3/R2 via `STORAGE_BACKEND=s3`). Ouvre http://localhost:3000.

### Commandes utiles

```bash
make test               # tests backend (moteur, API, fournisseurs, stockage) + typecheck/lint web
make e2e                # parcours navigateur (Playwright) contre une stack lancée
make benchmark          # compare des profils de modèles IA sur des images de test
make demo-assets        # régénère les avant/après de la landing avec le vrai moteur
```

---

## Ce qui est livré

### Parcours utilisateur
- **Sans inscription** : la première photo crée une session invitée (3 crédits, photos gardées 2 jours) ; l'inscription conserve les photos déjà améliorées, la connexion les rapatrie.
- **Upload** : glisser-déposer, clic, coller (⌘V), 1 à 12 photos, JPG/PNG/WEBP/HEIC, profils couleur convertis en sRGB, orientation EXIF appliquée.
- **Traitement asynchrone** avec progression réelle par étape (« 🔍 Analyse de votre photo… », « ✨ Votre photo est en cours d'amélioration… »), sans jamais bloquer l'interface.
- **Éditeur** : comparateur avant/après déplaçable (souris, tactile, clavier), « Maintenir pour voir l'original » (bouton ou barre espace), aperçu en direct (rendu serveur mis en cache par réglage), bouton **✨ Amélioration Vinted**, **🔒 Préserver l'article** (activé par défaut), intensité Original/Léger/Naturel/Premium/Studio, curseurs Nettoyage, Placement, Lumière, Couleur, Netteté, Plis (Off/Léger/Moyen/Fort), Arrière-plan (Conserver / Nettoyer / Fond propre + blanc cassé, gris clair, beige), Teinte limitée (−10…+10 → ±3°), cadrage 3:4/4:5/1:1, résolution.
- **🎨 Fidélité couleur : 98 %** affichée en permanence, avertissement et bouton « Réduire la correction » si la couleur bouge trop.
- **Imperfections** : marqueurs sur la photo (positionnés à travers la rotation et le recadrage), message de recommandation, possibilité de les marquer « conservées » ; les petites marques ambiguës peuvent être retirées comme poussière uniquement hors mode Préserver.
- **Historique** : Original → Version IA → Version modifiée → Version finale, retour à n'importe quelle version.
- **Export** JPG/PNG/WEBP, Standard (1600 px, Vinted) / Haute qualité (2400 px) / Maximum (3072 px), nom automatique `vinted_ai_01.jpg`, métadonnées (dont GPS) supprimées ; export de toute l'annonce en .zip.
- **Annonces multi-photos** : grille PHOTO 01…12 avec ✓ Nettoyée ✓ Couleurs ✓ Cadrage, « Améliorer toutes les photos » avec **cohérence** (balance des blancs et luminosité harmonisées).
- **Dashboard**, Mes photos, Mes projets, Favoris, Paramètres, Abonnement ; landing page, démonstration, pages légales, bannière de consentement.

### Moteur d'amélioration (non génératif)
Segmentation du vêtement (modèle du fond + GrabCut), balance des blancs estimée **sur le fond uniquement** (un t-shirt rouge n'est jamais « corrigé » vers le cyan), exposition préservant la teinte, détection des poussières/cheveux par hystérésis (rivets, imprimés et coutures épargnés), détection des imperfections (taches, décolorations, trous), réduction des plis par filtres guidés (texture, logos et coutures préservés), fond nettoyé ou neutre avec ombre naturelle et sans halo, redressement par symétrie, recadrage qui ne coupe ni ne prolonge jamais le vêtement, upscaling classique, netteté sans halo. Détails : [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

### Garde-fous
- **Color Fidelity Score** (CIEDE2000 sur le vêtement, par rapport à l'original corrigé en lumière seulement).
- **Contrôle structurel** : silhouette, contours forts (logos, coutures), texture, proportions. En cas d'échec, nouvel essai à intensité réduite puis signalement « ⚠️ Modification potentiellement excessive détectée ».
- **Préserver l'article** : plafonne couleur/plis/teinte, interdit la retouche de défauts et tout fournisseur **génératif**.

### Plateforme SaaS
- **Crédits** : allocation mensuelle par offre (Free 5, Starter 100, Pro 500, Business 2000), modifiable à chaud par l'admin, registre de transactions, remboursement automatique en cas d'échec ; Stripe Checkout + webhooks si configuré (activation directe en développement).
- **Sécurité** : stockage privé chiffré, URLs signées à durée limitée, isolation par utilisateur, cookie de session httpOnly SameSite, contrôle d'origine (CSRF), limitation de débit, en-têtes de sécurité, aucune indexation.
- **RGPD** : export complet des données (.zip), suppression immédiate du compte, consentements horodatés, durée de conservation configurable (1 à 365 jours) avec purge automatique, sous-traitants documentés.
- **Admin** : utilisateurs, photos/jour, coût IA par modèle, temps moyen, taux d'erreur, crédits consommés, conversion Free → Paid, MRR, fournisseurs et routage, édition des offres, **comparateur de modèles IA** (qualité, fidélité, vitesse, coût, taux d'erreur, avec vérité terrain).

### Abstraction des modèles IA
Chaque modèle est un `ImageEnhancementProvider` (`enhance_image`, `detect_clothing`, `detect_defects`, `remove_dust`, `correct_colors`, `upscale_image`…) qui déclare ses capacités, celles qui sont génératives et son coût. Le routeur choisit un fournisseur **par capacité** via `AI_ROUTING`, retombe sur le moteur local en cas d'échec et enregistre durée et coût de chaque appel.

Fournis : `local` (par défaut, gratuit), `anthropic` (Claude vision : attributs fins, défauts visibles, rédaction d'annonce), `rembg` (segmentation apprise), `replicate` (super-résolution, générative → bloquée en mode Préserver).

```bash
AI_ROUTING='{"segmentation":"rembg","clothing_detection":"anthropic","defect_detection":"anthropic"}'
```

---

## Structure

```
apps/
  api/                      FastAPI, workers, moteur image
    app/imaging/            analyse, opérations, garde-fous, rendu, pipeline, générateur de scènes de test
    app/providers/          abstraction des modèles IA + adaptateurs + routeur
    app/services/           crédits, photos, jobs, traitements, RGPD, analytics, facturation
    app/api/routes/         auth, photos/projets/exports, compte, facturation, admin, fichiers signés
    app/benchmark/          comparaison de profils de modèles (CLI + admin)
    alembic/                migrations
    tests/                  moteur (vérité terrain), API, fournisseurs, stockage
  web/                      Next.js (landing, app, admin), e2e Playwright
docs/ARCHITECTURE.md        conception détaillée
docker-compose.yml          stack complète
INSTALL.md                  tutoriel d'installation pas à pas
```

## Configuration

Toutes les variables sont documentées dans [`.env.example`](.env.example) (valeurs sûres par défaut en développement). En production : `ENVIRONMENT=production`, `SECRET_KEY` long et aléatoire, `COOKIE_SECURE=true`, `PUBLIC_APP_URL` exact (utilisé pour le contrôle d'origine), stockage S3/R2 avec règle de cycle de vie sur `tmp/` (1 jour), `JOB_BACKEND=celery`, hébergement UE recommandé.

## Tests

- **Moteur** (`tests/test_imaging.py`) : scènes synthétiques avec vérité terrain — poussières retirées mais rivets épargnés, tache conservée et signalée, trou réel détecté mais pas les contre-formes des lettres d'un imprimé, couleur réelle rétablie, vêtement redressé, fond neutre sans halo, vêtement coupé par le cadre jamais prolongé, garde-fous qui détectent une falsification.
- **API** (`tests/test_api.py`) : parcours invité complet jusqu'au téléchargement, crédits et remboursements, isolation entre utilisateurs, URLs signées infalsifiables, conversion invité → compte, cohérence multi-photos, export RGPD et effacement, admin, CSRF. Exécutés sur SQLite et PostgreSQL.
- **Fournisseurs** et **stockage** (S3 simulé) ; **e2e** Playwright du parcours réel.

## Limites connues

- Le moteur local est de la vision par ordinateur classique : excellent sur le cas le plus courant (un vêtement sur une surface assez uniforme), plus prudent sur les fonds chargés (fond propre désactivé si le détourage est incertain). La détection d'usure/bouloches est désactivée en local (trop de faux positifs sur le denim et les côtes) et confiée aux fournisseurs de vision.
- Les images avant/après de la landing sont des **scènes de test générées** (traitées par le vrai moteur) : à remplacer par de vraies photos de vendeurs, avec leur accord.
- Les adaptateurs Claude, rembg, Replicate et Stripe sont implémentés et testés avec des doublures, pas contre les services réels (clés non disponibles ici).

## Feuille de route (V2, architecture prête)

Générateur d'annonce (titre, description, mots-clés — déjà exposé en aperçu via `GET /photos/{id}/listing`), fonds IA, traitement par lots, Smart Crop, Image Quality Score (déjà calculé avant/après), aperçu d'annonce, autres marketplaces (profils Depop, Vestiaire Collective, eBay, Grailed, Leboncoin prêts dans `app/marketplaces.py`).

---

*Vinted est une marque de Vinted UAB. Ce projet est un service indépendant ; le nom affiché est configurable (`BRAND_NAME`).*
