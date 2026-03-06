# Timus — Autonomous Multi-Agent Desktop AI
# Python 3.11 (matching production environment)

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browser (optional — only needed for JavaScript-heavy sites)
RUN playwright install chromium --with-deps 2>/dev/null || true

# Copy source
COPY . .

# Create data directories
RUN mkdir -p data/qdrant_db

# Expose MCP server port
EXPOSE 5000

# Environment defaults (override via .env or -e flags)
ENV PORT=5000
ENV PYTHONUNBUFFERED=1

CMD ["python", "server/mcp_server.py"]
