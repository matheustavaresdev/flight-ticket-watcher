#!/bin/bash
set -euo pipefail

# Start Xvfb virtual display on :99
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!
export DISPLAY=:99

# Trap SIGTERM and SIGINT during the startup window (before exec).
# Steady-state signal handling after exec is managed by tini (init: true).
cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Give Xvfb a moment to initialize
sleep 0.5

if ! kill -0 "$XVFB_PID" 2>/dev/null; then
    echo "ERROR: Xvfb failed to start" >&2
    exit 1
fi

# If custom command provided, skip migrations and exec it directly
if [ $# -gt 0 ]; then
    exec "$@"
fi

# Run database migrations
alembic upgrade head

# Replace shell with app process (proper PID 1 signal forwarding)
exec python -m flight_watcher scheduler start
