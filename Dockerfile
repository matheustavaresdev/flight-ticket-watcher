FROM python:3.12-slim

# Install system dependencies: Chromium + required libs for headless browser
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
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

# Use system Chromium so patchright doesn't download its own
ENV PATCHRIGHT_BROWSERS_PATH=/usr/lib/chromium

WORKDIR /app

# Copy project metadata first for layer caching
COPY pyproject.toml ./
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir .

ENTRYPOINT ["python", "-m", "flight_watcher"]
