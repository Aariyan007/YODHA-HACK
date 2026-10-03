# One container for single-service hosting (Render): builds the React app, then serves it from the API process.
# Build context is the repo root:  docker build -f deploy/render/Dockerfile .
FROM node:22-alpine AS web
WORKDIR /src
COPY Frontend/package.json Frontend/package-lock.json ./
RUN npm ci
COPY Frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 STATIC_DIR=/app/static
WORKDIR /app
COPY BackEnd/requirements.txt .
RUN pip install -r requirements.txt
COPY BackEnd/ .
COPY --from=web /src/dist /app/static
# DDInter drug-interaction data (downloaded once at build). If the download fails the app still works with its curated rules.
RUN python scripts/build_ddi.py || echo "DDInter build skipped: using curated interaction rules only"
RUN useradd --system --uid 10001 --no-create-home app \
 && mkdir -p /app/uploads /app/demo_cache /app/vault \
 && chown -R app:app /app
USER app
EXPOSE 8000
# ONE worker on purpose: this process also runs the reminder scheduler.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips '*'"]
