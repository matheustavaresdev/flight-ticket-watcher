# Implementation Plan: Next.js Project Scaffold + Dockerfile (FLI-115)

## Issues
- FLI-115: Next.js project scaffold + Dockerfile

## Research Context

### Existing Project Structure
- Python backend in `src/flight_watcher/`, tests in `tests/`
- Docker: single-stage `Dockerfile` (Python), `docker-compose.yml` with `db` (postgres:18-alpine) and `scanner` services
- `.dockerignore` already excludes `node_modules`, `.env*`, `docs/`, `research/`
- `.gitignore` already covers `node_modules/`
- No existing Node.js/frontend code

### Next.js 15 + Tailwind v4 + shadcn/ui
- Next.js 15 defaults: App Router, TypeScript, Tailwind CSS v4, Turbopack, ESLint
- Tailwind v4: CSS-first config via `@theme` in `globals.css` (no `tailwind.config.js`)
- shadcn/ui: CLI copies component source into `components/ui/`, requires `@tailwindcss/postcss`
- Standalone output: `output: 'standalone'` in `next.config.ts` — creates self-contained `server.js`

### Docker Best Practices
- Three-stage build: deps → builder → runner (node:20-alpine)
- Standalone output reduces image from ~900MB to ~230MB
- Must copy `.next/static` and `public/` separately into runner stage
- Non-root user for security

### Epic Context (FLI-103)
Parent epic has 7 sub-issues. FLI-115 is the foundation. Subsequent issues (FLI-116–FLI-121) add DB client, pages, and compose networking. This scaffold must set up the structure they'll build on.

## Decisions Made

- **Package manager:** npm — built into node:20-alpine, zero extra Docker setup, simplest for the team
- **Node version:** 20 (LTS, matches issue requirement)
- **Scaffold method:** `npx create-next-app@latest` with `--ts --tailwind --eslint --app --src-dir --import-alias "@/*"` flags to get deterministic output, then enable standalone output
- **shadcn/ui init:** Run after scaffold, adds `components/ui/`, `lib/utils.ts`, configures paths
- **Dockerfile location:** `web/Dockerfile` (keeps web concerns in `web/`, compose uses `build: context: ./web`)
- **Port:** 3000 (Next.js default)
- **Non-root user:** `nextjs` (UID 1001) — follows Next.js Docker convention
- **docker-compose addition:** `web` service with `depends_on: db`, shares same Postgres env vars, exposes port 3000
- **No `--src-dir`:** Actually, use default App Router structure without `src/` to avoid confusion with the Python `src/` at root. Files go directly in `web/app/`.

## Implementation Tasks

### Task 1: Scaffold Next.js app in `web/`
```bash
cd /path/to/worktree
npx create-next-app@latest web --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm
```
- Verify: `web/package.json`, `web/app/layout.tsx`, `web/app/page.tsx`, `web/tsconfig.json`, `web/postcss.config.mjs` exist
- Affects: `web/` (new directory)

### Task 2: Enable standalone output
- Edit `web/next.config.ts` to add `output: 'standalone'`
- Affects: `web/next.config.ts`

### Task 3: Initialize shadcn/ui
```bash
cd web
npx shadcn@latest init --defaults
```
- Verify: `web/components/ui/` dir created, `web/lib/utils.ts` exists, `web/components.json` exists
- Affects: `web/components.json`, `web/lib/utils.ts`, `web/app/globals.css` (may be modified)

### Task 4: Add a few starter shadcn components
```bash
cd web
npx shadcn@latest add button card
```
- These are needed by the dashboard pages in subsequent issues
- Affects: `web/components/ui/button.tsx`, `web/components/ui/card.tsx`

### Task 5: Create `web/Dockerfile` (multi-stage)
Three stages:
1. **deps** — `node:20-alpine`, copy `package.json` + `package-lock.json`, run `npm ci`
2. **builder** — copy all source, run `npm run build`
3. **runner** — `node:20-alpine`, copy standalone output + static + public, non-root user, `CMD ["node", "server.js"]`

```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
```

Affects: `web/Dockerfile` (new file)

### Task 6: Create `web/.dockerignore`
Exclude: `node_modules`, `.next`, `.env*`, `*.md`, `.git`
Affects: `web/.dockerignore` (new file)

### Task 7: Add `web` service to `docker-compose.yml`
```yaml
web:
  build:
    context: ./web
    dockerfile: Dockerfile
  depends_on:
    db:
      condition: service_healthy
  environment:
    POSTGRES_HOST: ${POSTGRES_HOST}
    POSTGRES_PORT: ${POSTGRES_PORT}
    POSTGRES_DB: ${POSTGRES_DB}
    POSTGRES_USER: ${POSTGRES_USER}
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  ports:
    - "3000:3000"
  healthcheck:
    test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 30s
```
Affects: `docker-compose.yml`

### Task 8: Update `.env.example` with web-related vars
Add a `# Web Dashboard` section. For now just a comment — actual DB connection string vars are shared with scanner. Future issues (FLI-116) will add `DATABASE_URL` or similar.
Affects: `.env.example`

### Task 9: Verify build
```bash
cd web && npm run build
```
Affects: nothing (verification only)

### Task 10: Clean up default Next.js boilerplate
- Replace default `app/page.tsx` with a minimal placeholder page (just a heading saying "Flight Ticket Watcher")
- Remove default Next.js SVG assets that won't be used
- Keep `app/globals.css` with Tailwind imports intact
Affects: `web/app/page.tsx`, `web/public/` (remove unused defaults)

## Acceptance Criteria
- `web/` directory contains a working Next.js 15 app with TypeScript, Tailwind CSS v4, and shadcn/ui
- `web/Dockerfile` builds a multi-stage image with node:20-alpine and standalone output
- `docker-compose.yml` includes a `web` service connecting to the same PostgreSQL
- `npm run build` succeeds in `web/`
- Docker build succeeds: `docker build -t flight-watcher-web ./web`

## Verification
```bash
# Next.js build
cd web && npm run build

# Docker build
docker build -t flight-watcher-web ./web

# Lint
cd web && npm run lint
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes (`npm run build` in `web/`)
- [ ] Docker build passes (`docker build -t flight-watcher-web ./web`)
- [ ] Lint passes (`npm run lint` in `web/`)
- [ ] PR created with `Closes FLI-115`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Database client or API routes (FLI-116)
- Dashboard, Route Manager, Price Explorer, or Alerts pages (FLI-117–FLI-120)
- Shared network configuration details (FLI-121)
- Tests for the web app (no test framework setup needed yet)
- CI/CD pipeline changes
- Refactoring adjacent code not mentioned in tasks
