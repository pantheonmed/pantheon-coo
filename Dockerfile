FROM python:3.11-slim

WORKDIR /app

# Install system deps (no playwright/chromium on Railway)
RUN apt-get update && apt-get install -y \
    curl gcc && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    --break-system-packages 2>/dev/null || \
    pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create workspace dirs
RUN mkdir -p /tmp/pantheon_v2/workspace \
    /tmp/pantheon_v2/logs \
    /tmp/pantheon_v2/screenshots

# Health check (same $PORT as the app)
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD sh -c "curl -f http://localhost:$$PORT/health || exit 1"

# Start with Railway PORT (shell expands $PORT at container runtime)
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port $PORT"
