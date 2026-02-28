FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends     gcc     default-libmysqlclient-dev     pkg-config     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- Final stage ---
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     default-libmysqlclient-dev     curl     && rm -rf /var/lib/apt/lists/*     && groupadd -r appuser && useradd -r -g appuser appuser     && mkdir -p /app/data/exports && chown -R appuser:appuser /app

COPY --from=builder /install /usr/local

COPY --chown=appuser:appuser . .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3     CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
