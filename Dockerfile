FROM python:3.12-slim

# Install system dependencies: browser libs required by patchright's Chrome/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
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

WORKDIR /app

# Copy project metadata first for layer caching
COPY pyproject.toml ./
COPY src/ ./src/

# Install the package (requires root)
RUN pip install --no-cache-dir .

# Create non-root user after pip install (pip needs root), before browser install
RUN useradd -m -u 1000 appuser

# Create output directory writable by appuser (FLI-43)
RUN mkdir -p /app/output && chown -R appuser:appuser /app/output

USER appuser

# Patchright uses PATCHRIGHT_BROWSERS_PATH as its download root.
# Install chrome channel to match code's channel="chrome" (FLI-44).
ENV PATCHRIGHT_BROWSERS_PATH=/home/appuser/.cache/ms-playwright
RUN patchright install chrome

CMD ["sh", "-c", "alembic upgrade head && python -m flight_watcher"]
