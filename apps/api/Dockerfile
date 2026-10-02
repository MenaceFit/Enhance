# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN pip install uv
WORKDIR /app

FROM base AS deps
COPY pyproject.toml ./
# install dependencies only (layer cached until pyproject changes)
RUN uv pip install --system -r pyproject.toml --extra stripe --extra anthropic

FROM deps AS runtime
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts
RUN useradd --create-home --uid 10001 app && mkdir -p /app/var/storage && chown -R app /app/var
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health', timeout=2)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
