#!/bin/bash
set -euo pipefail

# Start Xvfb virtual display on :99
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
XVFB_PID=$!
export DISPLAY=:99

# Give Xvfb a moment to initialize
sleep 0.5

# Trap SIGTERM and SIGINT to kill Xvfb before exiting
cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
    exit 0
}
trap cleanup SIGTERM SIGINT

# Run database migrations
alembic upgrade head

# Replace shell with app process (proper PID 1 signal forwarding)
exec python -m flight_watcher
