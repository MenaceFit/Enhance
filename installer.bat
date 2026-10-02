@echo off
rem ===========================================================================
rem  Vinted AI - installation et lancement en un double-clic (Windows 10/11)
rem
rem    installer.bat           installe puis lance le site
rem    installer.bat docker    force l'installation avec Docker Desktop
rem    installer.bat local     force l'installation sans Docker (Python + Node.js)
rem    demarrer.bat            relance le site sans reinstaller
rem    arreter.bat             arrete le site
rem
rem  Sans Docker, ce script installe lui-meme uv (qui fournit Python) et
rem  Node.js LTS (via winget) s'ils sont absents.
rem ===========================================================================
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0"
set "ROOT=%CD%\"
set "RC=0"
set "ACTION=install"
set "MODE="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="demarrer" set "ACTION=start"
if /i "%~1"=="arreter" set "ACTION=stop"
if /i "%~1"=="docker" set "MODE=docker"
if /i "%~1"=="local" set "MODE=local"
shift
goto parse_args
:args_done

echo.
echo   ============================================
echo     Vinted AI - Photo Enhancer
echo   ============================================
echo.

if not exist "apps\api\pyproject.toml" goto err_not_extracted
if not exist "docker-compose.yml" goto err_not_extracted

if "%ACTION%"=="stop" goto stop
if "%ACTION%"=="start" goto start

rem ===========================================================================
rem  Installation
rem ===========================================================================
title Vinted AI - Installation

echo   -- Configuration
if exist ".env" goto env_exists
copy /y ".env.example" ".env" >nul
if errorlevel 1 goto err_env
echo      Fichier de configuration .env créé.
:env_exists

findstr /b /c:"SECRET_KEY=change-me" ".env" >nul
if errorlevel 1 goto env_key_done
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=(Get-Location).ProviderPath+'\.env'; $b=New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); $k=-join ($b | ForEach-Object { $_.ToString('x2') }); $c=[IO.File]::ReadAllText($p) -replace '(?m)^SECRET_KEY=[^\r\n]*', ('SECRET_KEY='+$k); [IO.File]::WriteAllText($p, $c)"
if errorlevel 1 goto err_env
echo      Clé secrète générée.
:env_key_done

findstr /b /c:"ADMIN_EMAILS=admin@example.com" ".env" >nul
if errorlevel 1 goto env_email_done
echo.
echo      Quelle adresse e-mail utiliseras-tu pour créer ton compte ?
echo      Ce compte aura accès au tableau de bord d'administration.
echo      Laisse vide et appuie sur Entrée pour passer cette étape.
set "VAI_EMAIL="
set /p "VAI_EMAIL=E-mail : "
if not defined VAI_EMAIL goto env_email_done
powershell -NoProfile -ExecutionPolicy Bypass -Command "$e=([string]$env:VAI_EMAIL).Trim().ToLower(); if ($e -notmatch '^[a-z0-9._+-]+@[a-z0-9-]+(\.[a-z0-9-]+)+$') { exit 2 }; $p=(Get-Location).ProviderPath+'\.env'; $c=[IO.File]::ReadAllText($p) -replace '(?m)^ADMIN_EMAILS=[^\r\n]*', ('ADMIN_EMAILS='+$e); [IO.File]::WriteAllText($p, $c)"
if errorlevel 1 goto env_email_invalid
echo      Adresse administrateur enregistrée.
goto env_email_done
:env_email_invalid
echo      Adresse non reconnue : tu pourras la mettre plus tard dans .env, ligne ADMIN_EMAILS.
:env_email_done

rem Keep the mode of a previous installation (switching would lose its data).
if defined MODE goto mode_chosen
if exist ".install-mode" set /p MODE=<".install-mode"
if /i not "%MODE%"=="docker" if /i not "%MODE%"=="local" set "MODE="
if defined MODE goto mode_chosen
set "MODE=local"
call :find_docker
if not errorlevel 1 set "MODE=docker"
:mode_chosen
if /i "%MODE%"=="docker" goto docker_install
goto local_install

rem ---------------------------------------------------------------------------
rem  Avec Docker
rem ---------------------------------------------------------------------------
:docker_install
echo.
echo   -- Docker
call :find_docker
if errorlevel 1 goto err_docker_missing
call :docker_running
if errorlevel 1 goto err_docker_down
echo      Docker est prêt.
echo.
echo   -- Construction et démarrage
echo      Compte 5 à 10 minutes la première fois, quelques secondes ensuite.
echo.
docker compose up --build -d
if errorlevel 1 goto err_docker_build
> ".install-mode" echo docker
goto docker_open

:docker_start
call :find_docker
if errorlevel 1 goto err_docker_missing
call :docker_running
if errorlevel 1 goto err_docker_down
docker compose up -d
if errorlevel 1 goto err_docker_build

:docker_open
echo.
echo      Attente du site
call :wait_url "http://127.0.0.1:3000/api/v1/health" 5
if errorlevel 1 goto err_docker_slow
start "" "http://localhost:3000"
echo.
echo   ============================================
echo     Le site est prêt : http://localhost:3000
echo   ============================================
echo.
echo   Il tourne en arrière-plan dans Docker : tu peux fermer cette fenêtre.
echo   Pour le relancer plus tard : demarrer.bat. Pour l'arrêter : arreter.bat.
echo   Crée ton compte avec ton adresse administrateur pour voir le menu Administration.
goto end_pause

rem ---------------------------------------------------------------------------
rem  Sans Docker
rem ---------------------------------------------------------------------------
:local_install
call :ports_free
if errorlevel 1 goto err_running
echo.
echo   -- Outils
call :ensure_uv
if errorlevel 1 goto err_uv
echo      uv (Python) : OK
call :ensure_node
if errorlevel 1 goto err_node
echo      Node.js : OK
echo.
echo   -- Installation de l'API (1 à 3 minutes la première fois)
pushd "apps\api"
if exist ".venv\Scripts\python.exe" goto api_venv_ok
uv venv --python 3.12
if errorlevel 1 goto err_api
:api_venv_ok
uv pip install -e ".[anthropic,stripe]"
if errorlevel 1 goto err_api
popd
echo.
echo   -- Installation du site (1 à 3 minutes)
pushd "apps\web"
call npm ci --no-audit --no-fund
if errorlevel 1 goto err_web
popd
> ".install-mode" echo local
echo.
echo   Installation terminée.
goto local_launch

:local_start
if not exist "apps\api\.venv\Scripts\uvicorn.exe" goto err_not_installed
if not exist "apps\web\node_modules\next\package.json" goto err_not_installed
call :find_node
if errorlevel 1 goto err_node
call :ports_free
if errorlevel 1 goto already_running

:local_launch
title Vinted AI - site en cours d'exécution (fermer cette fenêtre pour l'arrêter)
echo.
echo   ============================================
echo     Lancement du site : http://localhost:3000
echo   ============================================
echo.
echo   Le navigateur s'ouvrira tout seul dans quelques secondes.
echo   GARDE CETTE FENÊTRE OUVERTE pendant que tu utilises le site.
echo   Pour arrêter le site : ferme cette fenêtre.
echo   Si Windows demande d'autoriser Node.js dans le pare-feu, tu peux accepter
echo   ou annuler : le site fonctionne dans les deux cas sur cet ordinateur.
echo.
start "" /b /d "%ROOT%apps\api" "%ROOT%apps\api\.venv\Scripts\uvicorn.exe" app.main:app --host 127.0.0.1 --port 8000 --no-access-log
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -Command "$end=(Get-Date).AddMinutes(5); while ((Get-Date) -lt $end) { try { foreach ($u in 'http://127.0.0.1:8000/api/v1/health','http://127.0.0.1:3000/api/v1/health') { $q=[Net.WebRequest]::Create($u); $q.Proxy=$null; $q.Timeout=5000; $q.GetResponse().Close() }; try { $w=[Net.WebRequest]::Create('http://127.0.0.1:3000/'); $w.Proxy=$null; $w.Timeout=120000; $w.GetResponse().Close() } catch { }; Write-Host ''; Write-Host '  ==> Le site est prêt : http://localhost:3000'; Write-Host ''; Start-Process 'http://localhost:3000'; exit 0 } catch { }; Start-Sleep -Seconds 2 }"
set "API_URL=http://127.0.0.1:8000"
set "NEXT_TELEMETRY_DISABLED=1"
pushd "apps\web"
call npm run dev
popd
call :stop_local_processes
echo.
echo   Le site s'est arrêté.
goto end_pause

rem ===========================================================================
rem  Démarrer / arrêter
rem ===========================================================================
:start
title Vinted AI
call :read_mode
if /i "%MODE%"=="docker" goto docker_start
if /i "%MODE%"=="local" goto local_start
echo   Le site n'est pas encore installé : double-clique d'abord sur installer.bat.
goto fail

:stop
title Vinted AI
call :read_mode
if /i "%MODE%"=="docker" goto stop_docker
if /i "%MODE%"=="local" goto stop_local
echo   Rien à arrêter : le site n'a pas encore été installé avec installer.bat.
goto end_pause

:stop_docker
call :find_docker
if errorlevel 1 goto err_docker_missing
docker compose down
if errorlevel 1 goto fail
echo.
echo   Site arrêté. Tes comptes et tes photos sont conservés.
goto end_pause

:stop_local
call :stop_local_processes
echo   Site arrêté. Tes comptes et tes photos sont conservés.
goto end_pause

:already_running
echo   Le site semble déjà lancé (le port 3000 ou 8000 est occupé).
echo   Ouverture de http://localhost:3000 dans le navigateur.
echo   Si la page ne s'affiche pas : lance arreter.bat, puis demarrer.bat.
start "" "http://localhost:3000"
goto end_pause

rem ===========================================================================
rem  Erreurs
rem ===========================================================================
:err_not_extracted
echo   Ce fichier doit être lancé depuis le dossier décompressé.
echo   Fais un clic droit sur vinted-ai.zip, choisis « Extraire tout... »,
echo   puis double-clique sur installer.bat dans le dossier obtenu.
goto fail

:err_env
echo   Impossible de préparer le fichier .env.
echo   Vérifie que le dossier n'est pas en lecture seule, puis relance installer.bat.
goto fail

:err_docker_missing
echo   Docker n'est pas installé ou introuvable.
echo   Installe Docker Desktop : https://www.docker.com/products/docker-desktop/
echo   ou relance sans Docker depuis un terminal : installer.bat local
goto fail

:err_docker_down
echo.
echo   Docker Desktop ne répond pas.
echo   Ouvre Docker Desktop, accepte ses conditions si une fenêtre s'affiche,
echo   attends « Docker is running », puis relance ce fichier.
if not "%ACTION%"=="install" goto fail
if exist ".install-mode" goto fail
echo.
choice /c ON /m "Installer plutôt sans Docker (Python et Node.js sont installés automatiquement)"
if errorlevel 2 goto fail
set "MODE=local"
goto local_install

:err_docker_build
echo.
echo   Le démarrage avec Docker a échoué (messages ci-dessus).
echo   Vérifie ta connexion internet et l'espace disque, puis relance ce fichier.
echo   Voir aussi la section Dépannage de INSTALL.md.
goto fail

:err_docker_slow
echo.
echo   Le site ne répond pas encore après 5 minutes.
echo   Regarde les journaux avec : docker compose logs -f
echo   puis réessaie http://localhost:3000 dans ton navigateur.
goto fail

:err_running
echo   Le port 3000 ou 8000 est déjà utilisé : le site tourne peut-être déjà.
echo   Ferme sa fenêtre (ou lance arreter.bat), puis relance installer.bat.
goto fail

:err_uv
echo.
echo   L'installation de uv a échoué.
echo   Installe-le à la main : https://docs.astral.sh/uv/getting-started/installation/
echo   puis relance installer.bat.
goto fail

:err_node
echo.
echo   Node.js 20.9 ou plus récent est nécessaire et n'a pas pu être installé automatiquement.
echo   Installe la version LTS depuis https://nodejs.org (la page va s'ouvrir),
echo   puis relance installer.bat.
start "" "https://nodejs.org/fr/download"
goto fail

:err_api
popd
echo.
echo   L'installation de l'API a échoué (messages ci-dessus).
echo   Vérifie ta connexion internet, puis relance installer.bat.
goto fail

:err_web
popd
echo.
echo   L'installation du site a échoué (messages ci-dessus).
echo   Vérifie ta connexion internet, puis relance installer.bat.
goto fail

:err_not_installed
echo   L'installation sans Docker est incomplète : relance installer.bat.
goto fail

:fail
set "RC=1"
:end_pause
echo.
pause
popd
endlocal & exit /b %RC%

rem ===========================================================================
rem  Sous-programmes
rem ===========================================================================

:read_mode
if defined MODE exit /b 0
if exist ".install-mode" set /p MODE=<".install-mode"
if /i "%MODE%"=="docker" exit /b 0
if /i "%MODE%"=="local" exit /b 0
set "MODE="
if exist "apps\api\.venv\Scripts\uvicorn.exe" set "MODE=local"
exit /b 0

:find_docker
where docker >nul 2>&1
if errorlevel 1 if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
where docker >nul 2>&1 || exit /b 1
docker compose version >nul 2>&1 || exit /b 1
exit /b 0

:docker_running
docker info >nul 2>&1 && exit /b 0
echo      Démarrage de Docker Desktop (jusqu'à 3 minutes)...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a TRIES=0
:docker_running_wait
timeout /t 5 /nobreak >nul
docker info >nul 2>&1 && exit /b 0
set /a TRIES+=1
if %TRIES% lss 36 goto docker_running_wait
exit /b 1

:ensure_uv
where uv >nul 2>&1 && exit /b 0
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>&1 && exit /b 0
echo      Installation de uv, le gestionnaire Python...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
where uv >nul 2>&1 || exit /b 1
exit /b 0

:find_node
call :node_ok && exit /b 0
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
call :node_ok && exit /b 0
exit /b 1

:ensure_node
call :find_node && exit /b 0
where winget >nul 2>&1 || exit /b 1
echo      Installation de Node.js LTS (Windows peut demander une autorisation)...
winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
set "PATH=%ProgramFiles%\nodejs;%PATH%"
call :node_ok || exit /b 1
exit /b 0

:node_ok
where node >nul 2>&1 || exit /b 1
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit(a>20||(a===20&&b>=9)?0:1)" >nul 2>&1 || exit /b 1
exit /b 0

:ports_free
powershell -NoProfile -ExecutionPolicy Bypass -Command "if (Get-NetTCPConnection -State Listen -LocalPort 8000,3000 -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 exit /b 1
exit /b 0

:stop_local_processes
rem Only the API (python/uvicorn) and the site (node) listening on 8000/3000.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ids=Get-NetTCPConnection -State Listen -LocalPort 8000,3000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique; foreach ($i in $ids) { $p=Get-Process -Id $i -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -match '^(node|python|uvicorn)') { & taskkill.exe /PID $i /T /F | Out-Null } }"
exit /b 0

:wait_url
rem Arguments: URL, then the number of minutes to wait.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$end=(Get-Date).AddMinutes(%~2); while ((Get-Date) -lt $end) { try { $q=[Net.WebRequest]::Create('%~1'); $q.Proxy=$null; $q.Timeout=5000; $q.GetResponse().Close(); exit 0 } catch { Write-Host -NoNewline '.' }; Start-Sleep -Seconds 2 }; exit 1"
if errorlevel 1 exit /b 1
exit /b 0
