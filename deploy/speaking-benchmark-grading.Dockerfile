# Separate CPU execution boundary; requires external PostgreSQL and shared S3/R2.
# No torch/pyannote/faster-whisper or GPU is installed in this image.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libasound2 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend /app/backend
COPY scripts /app/scripts
RUN uv sync --project backend --frozen --no-dev --extra azure-speech --extra speech-vad
# Mount the preverified persistent VAD model separately. Never download per job.
ENV SPEAKING_BENCHMARK_EXECUTION=remote
CMD ["uv", "run", "--no-sync", "--project", "backend", "python", "scripts/speaking_benchmark_grading_worker.py"]
