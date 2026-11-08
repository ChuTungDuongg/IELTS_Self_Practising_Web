# Isolated CPU worker: external PostgreSQL + shared private S3/R2 required.
# Optional local Whisper belongs in an operator-managed, memory-limited runtime.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libasound2 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend /app/backend
COPY scripts /app/scripts
RUN uv sync --project backend --frozen --no-dev --extra azure-speech
ENV SPEAKING_BENCHMARK_EXECUTION=remote
CMD ["uv", "run", "--no-sync", "--project", "backend", "python", "scripts/speaking_benchmark_research_worker.py"]
