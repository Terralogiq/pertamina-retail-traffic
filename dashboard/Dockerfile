# Build context is dashboard/ (gcloud run deploy --source dashboard).
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npx vite build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ dashboard/api/
COPY --from=web /web/dist dashboard/web/dist
CMD exec uvicorn dashboard.api.main:app --host 0.0.0.0 --port ${PORT:-8080}
