# Implementation Plan: Xvfb Entrypoint Script

## Issues
- FLI-14: Xvfb entrypoint script

## Research Context

**Current state:**
- Dockerfile uses `python:3.12-slim`, already installs X11 libs (libx11-6, libxcomposite1, etc.) but NOT Xvfb itself
- Current CMD: `["sh", "-c", "alembic upgrade head && python -m flight_watcher"]`
- docker-compose has `init: true` (PID 1 signal handling), `ipc: host`, `shm_size: 2gb`
- Runs as non-root `appuser` (UID 1000)
- Shell convention: `#!/bin/bash`, `set -euo pipefail`

**Why Xvfb:** The scraper uses Patchright (Playwright fork) with Chrome. While headless mode works for basic scraping, Xvfb provides a virtual display that enables headed mode in Docker — useful for anti-bot evasion (headed Chrome has different fingerprints than headless) and debugging. Chrome renders to virtual display :99, nothing opens on host.

## Decisions Made

- **Entrypoint location:** `scripts/entrypoint.sh` — the `scripts/` dir already exists and houses utility scripts
- **Xvfb runs as background process**, app process gets `exec` for proper PID 1 signal handling via `init: true`
- **SIGTERM trap** kills Xvfb child process before exit
- **Display number:** `:99` (standard convention)
- **Screen resolution:** `1920x1080x24` (standard for browser automation)
- **Xvfb installed as root** in Dockerfile before `USER appuser`
- **Dockerfile uses ENTRYPOINT** with the script, removing CMD — the script handles alembic + app launch

## Implementation Tasks

1. **Install Xvfb in Dockerfile** — add `xvfb` to `apt-get install` line
   - Affects: `Dockerfile`

2. **Create entrypoint script** — `scripts/entrypoint.sh`
   - `#!/bin/bash` + `set -euo pipefail`
   - Start `Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &`
   - Store Xvfb PID
   - `export DISPLAY=:99`
   - Wait briefly for Xvfb to initialize
   - Trap SIGTERM/SIGINT → kill Xvfb → exit
   - Run `alembic upgrade head`
   - `exec python -m flight_watcher` (replaces shell, becomes PID 1's child)

3. **Update Dockerfile to use entrypoint** — affects `Dockerfile`
   - `COPY scripts/entrypoint.sh /app/scripts/entrypoint.sh` (before USER switch, with chmod +x)
   - Replace CMD with `ENTRYPOINT ["/app/scripts/entrypoint.sh"]`

4. **Add DISPLAY env to docker-compose** — affects `docker-compose.yml`
   - Add `DISPLAY: :99` to scanner environment (documentation/override purposes)

## Acceptance Criteria
- Xvfb starts on :99 inside the container
- DISPLAY=:99 is exported for child processes
- SIGTERM to container gracefully stops Xvfb
- Alembic migrations run before the app
- App process gets exec'd (proper signal forwarding)
- Container builds and starts without errors

## Verification
```bash
# Build
docker compose build scanner

# Verify Xvfb is installed
docker compose run --rm scanner which Xvfb

# Verify entrypoint is executable
docker compose run --rm --entrypoint="" scanner ls -la /app/scripts/entrypoint.sh

# Verify DISPLAY is set (quick check)
docker compose run --rm --entrypoint="" scanner bash -c "DISPLAY=:99 echo \$DISPLAY"
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] `docker compose build scanner` succeeds
- [ ] Entrypoint script is executable and correct
- [ ] PR created with `Closes FLI-14`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Changing headless/headed mode in scraper code (separate issue)
