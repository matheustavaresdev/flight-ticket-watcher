# Implementation Plan: Dockerfile Fixes — Permissions, Chrome Channel, Stability

## Issues
- FLI-13: Scanner Dockerfile with Xvfb + Patchright
- FLI-43: fix(dockerfile): ensure appuser can write runtime artifacts in container
- FLI-44: fix(dockerfile): install patchright chrome channel to match code usage

## Research Context

### Current State
- **Dockerfile** (`python:3.12-slim` base): installs system Chromium libs, pip installs the project, creates `appuser` (UID 1000), runs `patchright install chromium` as appuser. Entry point: `python -m flight_watcher`.
- **docker-compose.yml**: scanner service with `build: .`, depends on postgres, mounts `./src:/app/src:ro`. No `init`, `ipc`, or `shm_size` configured.
- **latam_scraper.py**: launches browser with `channel="chrome"` in 3 places (lines 62, 116, 175). This requests Google Chrome, but the Dockerfile installs Chromium — mismatch causes launch failure.
- **save_response()** (latam_scraper.py:310-318): writes to `Path(__file__).parent.parent.parent / "output"` which resolves to `/app/output` in container. `appuser` cannot write there since `/app` is owned by root.

### Key Decisions

**Xvfb: NOT needed.** The scraper runs headless (`headless=True` default). Xvfb is only needed for headed mode. FLI-13's mention of Xvfb is unnecessary — skip it to keep the image smaller.

**Base image: Keep `python:3.12-slim`.** The `mcr.microsoft.com/playwright` image is ~2GB, includes Playwright browsers we'd replace, and adds unnecessary bloat. The current slim image with manual deps is more controlled and already works. The system deps are already correctly identified.

**Chrome channel: Install `chrome` in Dockerfile** (option 1 from FLI-44). Rationale:
- Code already uses `channel="chrome"` in 3 places — changing Dockerfile is 1 line vs 3 code changes
- Chrome channel is better for anti-detection against LATAM's Akamai Bot Manager
- Patchright handles the Chrome download via `patchright install chrome`
- `patchright install chrome` installs system deps it needs via its own dependency resolution

**Permissions fix:** Create `/app/output` with appuser ownership before `USER` switch.

**Compose stability settings:** Add `init: true`, `ipc: host`, `shm_size: 2gb` for Chrome stability in containers (prevents OOM crashes from shared memory exhaustion).

## Implementation Tasks

### Task 1: Fix Dockerfile — permissions + chrome channel
Affects: `Dockerfile`

Replace the current Dockerfile with:

```dockerfile
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

ENTRYPOINT ["python", "-m", "flight_watcher"]
```

Changes from current:
1. Added `mkdir -p /app/output && chown -R appuser:appuser /app/output` before `USER appuser` (FLI-43)
2. Changed `patchright install chromium` → `patchright install chrome` (FLI-44)
3. Updated comment to explain chrome channel choice

### Task 2: Add Chrome stability settings to docker-compose.yml
Affects: `docker-compose.yml`

Add to the `scanner` service:
```yaml
    init: true
    ipc: host
    shm_size: 2gb
```

These prevent Chrome from crashing due to shared memory exhaustion in containers.

### Task 3: Verify Dockerfile builds successfully
Run `docker compose config --quiet` to validate compose syntax. A full `docker build` is recommended but depends on Docker daemon availability.

## Acceptance Criteria
- Container runs as non-root (`appuser`) and can write to `/app/output` without PermissionError
- Output dir ownership correct for appuser
- Patchright successfully launches browser in container (chrome channel installed matches `channel="chrome"` in code)
- Browser channel in Dockerfile matches what the code requests
- docker-compose includes init, ipc, and shm_size for Chrome stability

## Verification
```bash
# Validate compose syntax
docker compose config --quiet && echo "Compose valid"

# Build the image (requires Docker daemon)
docker compose build scanner

# Verify appuser can write output (requires running container)
docker compose run --rm scanner sh -c "id && touch /app/output/test && echo 'Write OK' && rm /app/output/test"

# Verify chrome channel is installed
docker compose run --rm scanner patchright install --dry-run 2>&1 | grep chrome
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Dockerfile installs chrome channel (not chromium)
- [ ] /app/output owned by appuser
- [ ] docker-compose has init, ipc, shm_size
- [ ] Build passes (`docker compose build scanner`)
- [ ] PR created with `Closes FLI-13`, `Closes FLI-43`, `Closes FLI-44`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Switching base image to mcr.microsoft.com/playwright
- Adding Xvfb (not needed for headless mode)
- Changing `channel="chrome"` in latam_scraper.py (Dockerfile fix is sufficient)
