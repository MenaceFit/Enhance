# Installer Vinted AI — tutoriel pas à pas

À la fin de ce tutoriel, le site tourne sur ton ordinateur :

- **le site** → http://localhost:3000
- **l'API** (documentation interactive) → http://localhost:8000/api/docs

Deux méthodes au choix :

| | Méthode A — Docker (recommandée) | Méthode B — Sans Docker |
|---|---|---|
| Pour qui | tout le monde, pas besoin de savoir coder | pour modifier le code |
| À installer | Docker Desktop | Node.js + uv |
| Contenu | stack complète : PostgreSQL, Redis, workers de traitement | base SQLite et fichiers locaux, tout dans un dossier |
| Durée | ~10 min (premier lancement) | ~10 min |

Les deux méthodes fonctionnent sur **Windows 10/11, macOS (Intel ou Apple Silicon) et Linux**. Il faut environ **4 Go de RAM libres** et **5 Go d'espace disque**.

---

## Windows : installation en un double-clic

1. **Décompresse** `vinted-ai.zip` : clic droit → **Extraire tout…**. Si Windows crée un dossier `vinted-ai` dans un autre dossier `vinted-ai`, ouvre celui qui contient `installer.bat`.
2. **Double-clique sur `installer.bat`**.
   - Si Windows affiche « Windows a protégé votre ordinateur », clique sur **Informations complémentaires** → **Exécuter quand même** (c'est l'avertissement habituel pour un fichier qui vient d'un zip téléchargé).
3. **Indique ton adresse e-mail** quand elle est demandée : le compte que tu créeras avec cette adresse aura accès à l'administration. Ensuite, laisse faire.

Le script :

- crée le fichier `.env` et y génère une clé secrète ;
- utilise **Docker Desktop s'il est installé** (méthode A, il le démarre si besoin) ;
- sinon, installe lui-même **uv** (qui fournit Python), **Node.js LTS** (via winget ; Windows peut demander une autorisation) puis l'application (méthode B) ;
- ouvre **http://localhost:3000** dans ton navigateur dès que le site est prêt.

Compte 5 à 10 minutes la première fois. Ensuite, utilise ces fichiers :

| Fichier | Rôle |
|---|---|
| `demarrer.bat` | relancer le site, sans réinstaller |
| `arreter.bat` | arrêter le site (comptes et photos conservés) |
| `installer.bat` | à relancer après une mise à jour du code |

Sans Docker, le site tourne dans la fenêtre ouverte par le script : **garde-la ouverte** pendant que tu l'utilises, la fermer arrête le site. Si Windows demande d'autoriser Node.js dans le pare-feu, tu peux accepter ou annuler : le site fonctionne dans les deux cas sur ton ordinateur.

Pour choisir la méthode toi-même, lance depuis un terminal ouvert dans le dossier : `installer.bat docker` ou `installer.bat local`.

La suite de ce tutoriel décrit l'installation manuelle (macOS, Linux, ou Windows si tu préfères tout contrôler).

---

## Étape commune : décompresser et ouvrir un terminal

1. **Décompresse** `vinted-ai.zip`. Tu obtiens un dossier `vinted-ai`.
2. **Ouvre un terminal dans ce dossier** :
   - **Windows** : ouvre le dossier `vinted-ai` dans l'Explorateur, clic droit dans le vide → **Ouvrir dans le Terminal**.
   - **macOS** : ouvre l'app **Terminal**, tape `cd ` (avec un espace), glisse le dossier `vinted-ai` dans la fenêtre, puis Entrée.
   - **Linux** : clic droit dans le dossier → **Ouvrir un terminal ici**.
3. **Crée ton fichier de configuration** en copiant le modèle :
   - Windows (PowerShell) : `Copy-Item .env.example .env`
   - macOS / Linux : `cp .env.example .env`
4. **Ouvre `.env`** avec un éditeur de texte (Bloc-notes, TextEdit, VS Code…) et modifie deux lignes :
   - `SECRET_KEY=` → remplace la valeur par une longue chaîne aléatoire. Pour en générer une :
     - Windows (PowerShell) : `-join ((1..64) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })`
     - macOS / Linux : `openssl rand -hex 32`
   - `ADMIN_EMAILS=` → mets **ton adresse e-mail**. Le compte que tu créeras avec cette adresse aura accès au tableau de bord d'administration.

   Enregistre le fichier.

> 💡 Sur macOS, les fichiers qui commencent par un point sont cachés dans le Finder : appuie sur `Cmd + Maj + .` pour les afficher.

---

## Méthode A — Docker (recommandée)

### A1. Installer Docker

- **Windows / macOS** : télécharge et installe **Docker Desktop** depuis https://www.docker.com/products/docker-desktop/, puis **lance-le** et attends que l'icône indique « Docker is running ». Sur Windows, accepte l'activation de WSL 2 si c'est proposé (un redémarrage peut être nécessaire).
- **Linux** : installe Docker Engine et le plugin Compose (https://docs.docker.com/engine/install/), puis ajoute ton utilisateur au groupe `docker`.

Vérifie dans le terminal :

```bash
docker compose version
```

Une ligne `Docker Compose version v2…` (ou plus récente) doit s'afficher.

### A2. Lancer le site

Dans le terminal ouvert dans le dossier `vinted-ai` :

```bash
docker compose up --build
```

Le premier lancement télécharge et construit tout : compte **5 à 10 minutes**. Les fois suivantes, c'est quelques secondes. C'est prêt quand les messages se calment et que tu vois une ligne du type `web-1 | ✓ Ready`.

> Garde ce terminal ouvert : il affiche les journaux. Pour arrêter, fais `Ctrl + C`.

### A3. Utiliser

1. Ouvre **http://localhost:3000**.
2. Clique sur **Améliorer ma première photo** et dépose une photo de vêtement : pas besoin de compte pour essayer (3 photos offertes en mode invité).
3. Clique sur **Créer un compte** avec l'adresse mise dans `ADMIN_EMAILS` : le menu **Administration** apparaît dans la barre latérale.

### A4. Au quotidien

| Action | Commande |
|---|---|
| Arrêter | `Ctrl + C`, ou `docker compose down` |
| Relancer | `docker compose up` |
| Lancer en arrière-plan | `docker compose up -d` (puis `docker compose logs -f` pour voir les journaux) |
| Après une mise à jour du code | `docker compose up --build` |
| **Tout effacer** (base, photos) | `docker compose down -v` |

Les données (comptes dans PostgreSQL, photos dans un volume Docker privé) sont conservées entre deux lancements.

---

## Méthode B — Sans Docker

### B1. Installer les outils

1. **Node.js 22 LTS** : https://nodejs.org (bouton « LTS »). Vérifie avec `node --version`, qui doit afficher v20.9 ou plus.
2. **uv**, le gestionnaire Python (il installe Python tout seul) :
   - Windows (PowerShell) : `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS / Linux : `curl -LsSf https://astral.sh/uv/install.sh | sh`

   **Ferme puis rouvre le terminal**, puis vérifie avec `uv --version`.

### B2. Lancer l'API (terminal n°1)

Depuis le dossier `vinted-ai` :

**Windows (PowerShell)**
```powershell
cd apps\api
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv\Scripts\uvicorn app.main:app --port 8000
```

**macOS / Linux**
```bash
cd apps/api
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8000
```

L'installation prend 1 à 3 minutes la première fois. C'est prêt quand `Application startup complete` s'affiche. Pour vérifier, http://localhost:8000/api/v1/health doit répondre `{"status":"ok"}`.

### B3. Lancer le site (terminal n°2)

Ouvre un **deuxième terminal** dans le dossier `vinted-ai`, puis :

```bash
cd apps/web
npm ci
npm run dev
```

Ouvre **http://localhost:3000**. Comme en méthode A : dépose une photo, puis crée ton compte avec l'adresse de `ADMIN_EMAILS`.

### B4. Au quotidien

- **Arrêter** : `Ctrl + C` dans chacun des deux terminaux.
- **Relancer** : dans `apps/api`, relance uniquement la dernière commande (`…uvicorn app.main:app --port 8000`) ; dans `apps/web`, `npm run dev`. Pas besoin de réinstaller.
- **Données** : tout est dans `apps/api/var/` (base SQLite et photos). Supprime ce dossier pour repartir de zéro.
- **macOS / Linux** : un raccourci existe avec `make install`, puis `make api` et `make web` dans deux terminaux.

---

## Ce que tu peux tester

- **Une photo** → analyse automatique, puis l'éditeur : fais glisser la barre avant/après, maintiens « Maintenir pour voir l'original », essaie **✨ Amélioration Vinted**, l'intensité **Studio** (fond propre) et les curseurs, puis **Télécharger** (`vinted_ai_01.jpg`).
- **Plusieurs photos d'un même article** (jusqu'à 12) → page « Annonce » : **Améliorer toutes les photos** avec cohérence des couleurs, puis **Tout télécharger** (.zip).
- **Paramètres** → durée de conservation, export de tes données, suppression du compte.
- **Abonnement** → sans Stripe configuré, les offres s'activent directement (mode démonstration).
- **Administration** → statistiques, coût IA par modèle, édition des offres et des crédits, **Comparer des modèles IA**.

---

## Options (facultatif)

Toutes les options se règlent dans `.env`. Redémarre ensuite : `docker compose up` (méthode A) ou l'API (méthode B).

| Option | Variables |
|---|---|
| Analyse fine par **Claude** (logos, poches, défauts visibles, rédaction d'annonce) | `ANTHROPIC_API_KEY=…` et `AI_ROUTING={"clothing_detection":"anthropic","defect_detection":"anthropic"}` |
| Paiement **Stripe** | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_IDS={"starter":"price_…","pro":"price_…","business":"price_…"}` |
| Nom affiché | `BRAND_NAME=…` (méthode A ; reconstruire avec `--build`) |
| Crédits invités, taille maximale, durée de conservation | `GUEST_CREDITS`, `MAX_UPLOAD_MB`, `DEFAULT_RETENTION_DAYS` |

Le moteur d'amélioration intégré fonctionne **sans aucune clé** et sans coût par photo.

---

## Mettre en ligne (résumé)

1. Un serveur (VPS) avec Docker, et un nom de domaine pointant dessus.
2. Dans `.env` : `ENVIRONMENT=production`, une vraie `SECRET_KEY`, `PUBLIC_APP_URL=https://ton-domaine.fr`, `CORS_ORIGINS=https://ton-domaine.fr` et `COOKIE_SECURE=true`.
3. Le stockage : par défaut, les photos restent dans le volume Docker du serveur (pense à le sauvegarder). Pour un bucket S3 / Cloudflare R2 privé, mets `STORAGE_BACKEND=s3` et les variables `S3_*`, avec une règle de cycle de vie qui supprime le préfixe `tmp/` après 1 jour.
4. Un reverse proxy HTTPS (Caddy, Nginx, Traefik) devant le port 3000.
5. `docker compose up -d --build`.

Plus de détails dans `README.md` et `docs/ARCHITECTURE.md`.

---

## Dépannage

| Problème | Solution |
|---|---|
| « Windows a protégé votre ordinateur » au lancement de `installer.bat` | Clique sur **Informations complémentaires** → **Exécuter quand même**. |
| `installer.bat` dit de décompresser le zip | Tu l'as lancé depuis l'intérieur du zip : fais clic droit sur le zip → **Extraire tout…**, puis lance `installer.bat` dans le dossier extrait. |
| `installer.bat` n'arrive pas à installer Node.js | Installe la version LTS depuis https://nodejs.org, puis relance `installer.bat`. |
| `Cannot connect to the Docker daemon` / `docker: command not found` | Docker Desktop n'est pas lancé, ou pas installé. Lance-le et attends « Docker is running ». |
| `set SECRET_KEY in .env` | Le fichier `.env` n'existe pas ou n'est pas dans le dossier `vinted-ai` (voir l'étape commune). |
| `port is already allocated` / `address already in use` | Un autre programme utilise le port 3000 ou 8000. Ferme-le, ou change le premier nombre de la ligne `ports` dans `docker-compose.yml` (par exemple `"3001:3000"`), puis ouvre le site sur ce nouveau port. |
| `uv` ou `npm` « n'est pas reconnu » | Ferme et rouvre le terminal après l'installation. Sur Windows, redémarre si besoin. |
| « Origine non autorisée » à l'envoi d'une photo | Ouvre le site via http://localhost:3000. Pour y accéder depuis un autre appareil avec la méthode A (par exemple ton téléphone sur le même Wi-Fi via `http://IP-de-ton-ordinateur:3000`), ajoute cette adresse à `CORS_ORIGINS` dans `.env` (séparée par une virgule), puis redémarre. |
| « Tu as utilisé tous tes crédits » | Crée un compte (5 photos par mois), choisis une offre dans **Abonnement**, ou ajoute des crédits depuis l'Administration. |
| Le premier lancement Docker est long | C'est normal : téléchargement des images et construction. Les lancements suivants sont rapides. |
| Repartir de zéro | Méthode A : `docker compose down -v`. Méthode B : arrête le site puis supprime `apps/api/var/`. |

### Pour les développeurs

```bash
cd apps/api && .venv/bin/python -m pytest      # tests backend (Windows : .venv\Scripts\python -m pytest)
cd apps/web && npx tsc --noEmit && npx eslint . # vérifications du frontend
```
