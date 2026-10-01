.PHONY: install api web worker test lint e2e demo-assets benchmark migrate up

install:            ## install backend and frontend dependencies
	cd apps/api && uv venv .venv && uv pip install -e ".[dev,stripe,anthropic]"
	cd apps/web && npm ci

api:                ## run the API with the in-process job queue (http://localhost:8000/api/docs)
	cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8000

web:                ## run the Next.js dev server (http://localhost:3000)
	cd apps/web && npm run dev

worker:             ## run a Celery worker (JOB_BACKEND=celery)
	cd apps/api && .venv/bin/celery -A app.workers.celery_app worker --loglevel=INFO

migrate:            ## apply database migrations
	cd apps/api && .venv/bin/alembic upgrade head

test:               ## backend tests + frontend typecheck/lint
	cd apps/api && .venv/bin/python -m pytest
	cd apps/web && npx tsc --noEmit && npx eslint .

lint:
	cd apps/api && .venv/bin/ruff check app tests scripts
	cd apps/web && npx eslint .

e2e:                ## browser smoke test against a running stack (E2E_BASE_URL, default http://localhost:3000)
	cd apps/web && npx playwright test

demo-assets:        ## regenerate the landing-page before/after pairs with the real engine
	cd apps/api && .venv/bin/python scripts/generate_demo_assets.py ../web/public/demo

benchmark:          ## compare AI provider profiles on synthetic images
	cd apps/api && .venv/bin/python -m app.benchmark --profiles local --synthetic 10

up:                 ## full stack with Docker (Postgres, Redis, MinIO, API, workers, web)
	docker compose up --build
