# syntax=docker/dockerfile:1
# Pantheon COO OS — multi-stage image (Railway / Docker Hub)
# Stage 1: install Python deps + Playwright Chromium
FROM python:3.11-slim-bookworm AS builder

WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt \
    && /venv/bin/playwright install chromium --with-deps

# Stage 2: minimal runtime + non-root user
FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -r -u 10001 -m -d /home/coo -s /bin/bash coo

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:${PATH}"
ENV PLAYWRIGHT_BROWSERS_PATH=/home/coo/.cache/ms-playwright

COPY --from=builder /root/.cache/ms-playwright /home/coo/.cache/ms-playwright
RUN chown -R coo:coo /home/coo/.cache

WORKDIR /app
COPY --chown=coo:coo . .

RUN mkdir -p /tmp/pantheon_v2/screenshots tools/custom \
    && chown -R coo:coo /tmp/pantheon_v2 tools/custom

USER coo

EXPOSE 8002
ENV PORT=8002
ENV HOST=0.0.0.0

HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-8002}/health" || exit 1'

CMD ["sh", "-c", "uvicorn main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8002} --log-level info"]
