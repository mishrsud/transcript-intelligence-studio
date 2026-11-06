FROM node:22-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir '.[audio]' && useradd --create-home app && mkdir /app/data && chown app:app /app/data
COPY --from=frontend /ui/dist ./frontend/dist
USER app
ENV TRANSCRIBER_DB=/app/data/transcripts.db TRANSCRIBER_MODEL_DIR=/app/data/models TRANSCRIBER_MODEL=tiny
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "youtube_transcriber.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
