# Architecture

## Vue d'ensemble

```
                 ┌──────────── navigateur ────────────┐
                 │  Next.js (landing, app, admin)     │
                 └───────────────┬────────────────────┘
                                 │ même origine : /api/* réécrit vers l'API
                                 │ (cookie de session httpOnly, SameSite=Lax)
                 ┌───────────────▼────────────────────┐
                 │ FastAPI                             │
                 │  auth · photos · projets · exports  │
                 │  compte/RGPD · facturation · admin  │
                 └──────┬──────────────┬──────────────┘
                        │ jobs         │ URLs signées
          ┌─────────────▼───┐   ┌──────▼──────────────┐
          │ Redis → Celery  │   │ S3 / R2 / MinIO     │
          │ (ou pool local) │   │ users/{id}/...      │
          └────────┬────────┘   └─────────────────────┘
                   │ pipeline image
          ┌────────▼───────────────────────────────────┐
          │ ProviderRouter → local | anthropic | rembg │
          │                  | replicate | …           │
          └────────────────────────────────────────────┘
                   │
          ┌────────▼────────┐
          │ PostgreSQL      │
          └─────────────────┘
```

## Traitement d'une photo

```
UPLOAD ──► validation d'en-tête (format, dimensions) · vignette immédiate · crédit réservé
   │
CREATE JOB ──► QUEUE (Celery / pool) ──► worker
   │
   ├─ décodage (EXIF, ICC → sRGB, HEIC) · copie de travail ≤ 3072 px
   ├─ IMAGE QUALITY ANALYSIS
   ├─ SEGMENTATION                (capacité « segmentation »)
   ├─ COLOR ANALYSIS              illuminant estimé sur le fond
   ├─ CLOTHING DETECTION          (capacité « clothing_detection », vue redressée)
   ├─ DUST / ARTIFACT DETECTION   (capacité « dust_detection »)
   ├─ DEFECT DETECTION            (capacité « defect_detection »)
   ├─ LIGHTING ANALYSIS · COMPOSITION ANALYSIS
   ├─ NON-DESTRUCTIVE ENHANCEMENT (capacité « enhancement »)
   ├─ COLOR FIDELITY CHECK · STRUCTURE CHECK  → réduction automatique si échec
   ├─ FINAL QUALITY CHECK
   └─ STORE RESULT (version « ai ») ──► NOTIFY FRONTEND (polling /jobs, progression par étape)
```

Une photo standard est traitée en ~5 s sur un CPU (analyse ~1 s, rendu ~1 s, encodages et stockage). Les aperçus de l'éditeur sont rendus à 1280 px depuis une source mise en cache en mémoire, puis mis en cache dans le stockage par empreinte des réglages : revenir à un réglage déjà vu est instantané.

## Moteur d'image (`app/imaging`)

Le rendu est une **fonction pure** de (copie de travail, analyse, réglages) : chaque version de l'historique est reproductible à n'importe quelle résolution (aperçu, export Standard/Haute/Maximum). Ordre des opérations :

1. **Poussières** — inpainting local (Telea) des seules particules confirmées. Les zones ambiguës sont des « défauts » et ne sont jamais retouchées automatiquement.
2. **Balance des blancs** — gains von Kries en lumière linéaire, estimés sur le *fond* (le vêtement est exclu), pondérés par la plausibilité d'un illuminant (axe bleu-jaune), l'uniformité du fond et plafonnés.
3. **Exposition** — gain sur la luminance appliqué en ratio à tous les canaux (teinte et saturation préservées), épaule douce, très léger relèvement des ombres (les noirs restent noirs).
4. **Plis** — L* décomposé en détail fin / plis / base par filtres guidés ; seuls les plis (ombrages doux) sont atténués (62 % max), les bords forts (logos, coutures) restent dans la base ; les zones de défauts sont exclues.
5. **Contraste** — point noir, courbe en S légère, CLAHE mélangé, sur L* uniquement.
6. **Vibrance / teinte** — chroma des couleurs ternes légèrement renforcée ; rotation de teinte bornée (±3°).
7. **Fond** — *Nettoyer* : texture et plis du fond adoucis, éclairci, légèrement neutralisé. *Fond propre* : surface neutre (blanc cassé, gris clair, beige) avec **ombre d'origine transférée** + ombre de contact, contours décontaminés (pas de halo). Désactivé si le détourage est incertain.
8. **Géométrie** — redressement par recherche de la symétrie miroir, recadrage au ratio demandé. Le cadre ne coupe jamais le vêtement ; un côté où le vêtement touche le bord reste collé au bord (rien n'est inventé hors cadre) ; hors fond propre, le cadre reste dans la vraie photo.
9. **Upscaling** — Lanczos + récupération de détail (crochet fournisseur).
10. **Netteté** — masque flou sur L* avec seuil de bruit et limitation du dépassement (pas de halo).

### Garde-fous (`app/imaging/checks`)

- **Fidélité couleur** : référence = original corrigé en *lumière seulement* (balance des blancs + exposition), meilleure estimation de la vraie couleur. Score = 100 − 6·ΔE00 moyen (kL = 2) sur le vêtement, pénalité sur le 90ᵉ centile ; échec si score < 90, dérive de teinte > 6° ou ratio de chroma hors [0,8 ; 1,2].
- **Structure** : IoU des silhouettes, rappel des contours forts (logos, coutures, poches), corrélation de la texture fine, variation des proportions. Le moteur local passe par construction ; le contrôle s'applique à tout fournisseur futur, notamment génératif.
- **Boucle** : si un contrôle échoue, nouveau rendu à 50 % puis 25 % d'intensité (couleur/teinte, puis plis/netteté), sinon validation demandée à l'utilisateur.

### Générateur de scènes (`app/imaging/synthetic.py`)

Produit des photos « amateur » (lumière jaune, sous-exposition, inclinaison, poussières, cheveux, tache, trou, bruit, JPEG) avec la **vérité terrain** : masque, couleur réelle, positions des poussières, tache, trou, inclinaison. Sert aux tests, au benchmark et aux visuels de la landing (toujours traités par le vrai moteur).

## Fournisseurs IA (`app/providers`)

```python
class ImageEnhancementProvider:
    name, capabilities, generative, cost_cents
    def segment(image) -> (mask, Segmentation, holes)
    def detect_clothing(image, mask, gains) -> ClothingAttributes
    def detect_dust(image, mask) -> (labels, specks)
    def remove_dust(image, labels, ids) -> image
    def detect_defects(image, mask, specks, holes) -> list[Defect]
    def correct_colors(image, source, settings) -> image
    def enhance_image(source, settings, target_long_side) -> RenderResult
    def upscale_image(image, width, height) -> image
    def generate_listing(image, attributes) -> dict
```

**Ajouter un modèle** : écrire un adaptateur qui déclare ses capacités (et lesquelles sont génératives), l'enregistrer dans `registry.build_providers()`, puis le router avec `AI_ROUTING`. Le routeur :
- choisit le fournisseur par capacité (`"*"` pour le défaut) ;
- ignore un fournisseur non configuré ou **génératif quand « Préserver l'article » est actif** ;
- retombe sur `local` en cas d'erreur (appel en échec non facturé) ;
- enregistre durée, modèle, coût (réel pour Claude, d'après l'usage de tokens) dans `provider_calls` → tableau de bord admin.

**Comparer des modèles** : `POST /admin/benchmarks` ou `python -m app.benchmark --profiles local,rembg,claude --synthetic 20`. Chaque profil traite les mêmes images ; résumé par profil : gain de qualité, fidélité, structure, durée p50/p95, coût par image, taux d'erreur, rappel des poussières, défauts signalés, exactitude du type de vêtement, erreur de couleur par rapport à la vérité.

## Données (`app/models`)

| Table | Rôle |
|---|---|
| `users` | compte (ou invité), offre, préférences, durée de conservation, version de jeton |
| `consents` | consentements horodatés et versionnés |
| `plans` · `subscriptions` · `credit_transactions` | offres modifiables, abonnements, registre des crédits |
| `projects` · `photos` · `photo_versions` | annonce, photo (analyse JSON, état des défauts, expiration), historique des versions |
| `jobs` · `provider_calls` | file de traitements (progression, étape, coût) et appels aux modèles |
| `exports` · `benchmark_runs` | fichiers téléchargeables temporaires, comparaisons de modèles |

Stockage : `users/{user}/photos/{photo}/original.*`, `working.jpg`, `thumb.webp`, `preview.webp`, `analysis/mask.png`, `analysis/labels.png`, `versions/{version}/after|before|thumb.webp` ; `users/{user}/exports/…`, `users/{user}/gdpr/…` ; aperçus temporaires `tmp/renders/{user}/{photo}/…` (règle de cycle de vie 1 jour).

## API (préfixe `/api/v1`, documentation interactive sur `/api/docs` hors production)

| | |
|---|---|
| Auth | `GET /auth/me` · `POST /auth/guest` · `POST /auth/signup` · `POST /auth/login` · `POST /auth/logout` |
| Upload | `POST /uploads` (multipart, 1–12 fichiers, crée l'annonce et les jobs) |
| Projets | `GET/POST /projects` · `GET/PATCH/DELETE /projects/{id}` · `PUT /projects/{id}/order` · `POST /projects/{id}/enhance` · `POST /projects/{id}/exports` |
| Photos | `GET /photos` · `GET/PATCH/DELETE /photos/{id}` · `POST /photos/{id}/preview` · `POST /photos/{id}/versions` · `POST /photos/{id}/versions/{v}/restore` · `PATCH /photos/{id}/defects/{d}` · `POST /photos/{id}/exports` · `POST /photos/{id}/retry` · `GET /photos/{id}/listing` |
| Jobs | `GET /jobs/{id}` · `GET /jobs?ids=` · `GET /dashboard` |
| Facturation | `GET /billing/plans` · `GET /billing` · `POST /billing/checkout` · `POST /billing/webhook` |
| Compte / RGPD | `GET/PATCH /account` · `POST /account/consents` · `POST /account/export` · `POST /account/delete` |
| Admin | `GET /admin/metrics` · `GET /admin/providers` · `GET/PATCH /admin/plans` · `POST /admin/users/{id}/credits` · `GET/POST /admin/benchmarks` · `GET /admin/benchmarks/{id}` |
| Fichiers | `GET /files/{key}?exp&sig[&dl]` (stockage local uniquement ; S3 sert des URLs présignées) |

## Sécurité & RGPD

- Session : JWT HS256 dans un cookie httpOnly, SameSite=Lax, Secure en production ; révocation par `token_version`. Mots de passe argon2.
- CSRF : SameSite + contrôle de l'en-tête `Origin` sur toute requête modifiante. Limitation de débit sur l'authentification, l'upload et la création d'invités (en mémoire ; mettre un limiteur partagé devant plusieurs réplicas).
- Isolation : toutes les requêtes filtrent par `user_id` (404 sinon) ; clés de stockage préfixées par utilisateur ; URLs signées liées à la clé, au nom de téléchargement et à une expiration.
- Fichiers : bucket privé, chiffrement côté serveur, `X-Robots-Tag: noindex` partout, `robots.txt` excluant l'app et l'API, métadonnées EXIF/GPS jamais réécrites à l'export, protection contre les bombes de décompression.
- RGPD : export des données (.zip avec `donnees.json`, originaux, versions), effacement immédiat (base + préfixes de stockage), consentements versionnés, purge horaire des photos expirées, des invités et des exports temporaires.

## Performance & coûts

- Analyse à 1600 px, segmentation à 640 px, aperçus à 1280 px, exports à la taille demandée seulement.
- Source d'aperçu en cache mémoire (LRU), aperçus mis en cache par réglage, vignettes WebP, files d'attente avec `acks_late` et préchargement 1 (tâches CPU longues), workers parallèles pour les annonces multi-photos.
- Le moteur local coûte 0 € par image ; les fournisseurs externes sont optionnels et leur coût est suivi appel par appel.
