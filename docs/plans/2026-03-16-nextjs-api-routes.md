# Implementation Plan: Next.js API Routes + Cleanup

## Issues
- FLI-116: Database client + API routes for Next.js
- FLI-121: Update docker-compose with web service + shared network
- FLI-126: Remove premature sidebar CSS variables
- FLI-127: Move shadcn CLI to devDependencies
- FLI-128: Local Geist font instead of next/font/google

## Research Context

### Database Schema (from SQLAlchemy models in `src/flight_watcher/models.py`)
Four tables, all owned by Python/Alembic migrations:

**search_configs**: id (serial PK), origin (varchar 3), destination (varchar 3), must_arrive_by (date), must_stay_until (date), max_trip_days (int), min_trip_days (int nullable), active (bool default true), retry_count (int default 0), needs_attention (bool default false), created_at (timestamptz), updated_at (timestamptz). Index: `(origin, destination)`.

**scan_runs**: id (serial PK), search_config_id (FK → search_configs), started_at (timestamptz), completed_at (timestamptz nullable), status (varchar — 'running'/'completed'/'failed'), last_successful_date (date nullable), error_message (text nullable). Index: `(search_config_id, status)`.

**price_snapshots**: id (serial PK), scan_run_id (FK → scan_runs), origin (varchar 3), destination (varchar 3), flight_date (date), flight_code (varchar 20), departure_time (timestamptz), arrival_time (timestamptz), duration_min (int), stops (int), brand (varchar 30), price (numeric 10,2), currency (varchar 3), search_type (varchar — 'oneway'/'roundtrip'), fetched_at (timestamptz). Indexes: `(scan_run_id)`, `(origin, destination, flight_date)`, `(origin, destination, flight_date, brand)`, `(flight_date, fetched_at)`.

**price_alerts**: id (serial PK), search_config_id (FK → search_configs), origin (varchar 3), destination (varchar 3), flight_date (date), airline (varchar 30), brand (varchar 30), previous_low_price (numeric 10,2), new_price (numeric 10,2), price_drop_abs (numeric 10,2), alert_type (varchar — 'new_low'/'threshold'), sent_to (varchar 255 nullable), sent_at (timestamptz nullable), created_at (timestamptz).

### ORM Decision: Prisma
Using Prisma ORM with `prisma db pull` introspection. Rationale:
- Single-command introspection of existing SQLAlchemy tables
- First-class Next.js integration (Vercel ecosystem)
- Read-heavy dashboard use case fits Prisma's `.select()` / `.include()` patterns
- Well-documented singleton pattern prevents connection pool exhaustion in dev

Python/Alembic owns schema migrations. Next.js side is read-write via Prisma Client but never runs `prisma migrate`. After Python migrations, run `npx prisma db pull && npx prisma generate`.

### Docker-compose Status
The `web` service already exists in `docker-compose.yml` (added in FLI-115). It has `POSTGRES_*` env vars but no `DATABASE_URL`. Prisma requires `DATABASE_URL`, so we need to add it as a composed value. PostgreSQL 18-alpine is already pinned.

### Font Decision: `geist` npm package
The `geist` npm package (by Vercel) bundles font files locally. Using `next/font/local` with these files eliminates the build-time network dependency on fonts.googleapis.com. This is the approach recommended by Vercel's own Next.js template.

### Existing Patterns
- Next.js 16.1.6, React 19, TypeScript strict, standalone output
- shadcn/ui v4 with base-nova style, `@/` path alias
- No API routes exist yet — this is the first
- No test framework in web/ yet — tests are out of scope for this batch
- Tailwind CSS v4 with oklch color model

## Decisions Made

1. **Prisma over Drizzle** — better introspection DX, tighter Next.js integration, acceptable code-gen tradeoff for read-heavy dashboard
2. **DATABASE_URL in docker-compose** — composed from existing POSTGRES_* vars using string interpolation: `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:${POSTGRES_PORT}/${POSTGRES_DB}`
3. **Hand-write Prisma schema** — since we can't introspect without a running DB during CI/implementation, write `schema.prisma` manually from the known SQLAlchemy models. Document `prisma db pull` as the sync command.
4. **No string enums in Prisma** — SQLAlchemy uses `native_enum=False` (plain varchar), so Prisma schema uses `String` fields, not `enum` types. TypeScript union types provide type safety.
5. **`geist` npm package** — install `geist` and use `next/font/local` with the package's font files via `geist/font/sans` and `geist/font/mono` imports
6. **API route structure** — flat REST routes under `app/api/` with Next.js Route Handlers. JSON responses with `{ data }` wrapper for success, `{ error }` for failures.
7. **No pagination yet** — simple `.findMany()` with `orderBy` and reasonable `take` limits. Pagination will be added when the dashboard UI needs it.

## Implementation Tasks

### Batch 1: Cleanup (FLI-126, FLI-127, FLI-128) — independent, do first

**Task 1** (FLI-126): Remove sidebar CSS variables from `web/app/globals.css`
- Remove lines 12-19 from `@theme inline` block (sidebar color mappings)
- Remove lines 75-82 from `:root` (sidebar variable definitions)
- Remove lines 109-116 from `.dark` (sidebar dark mode definitions)

**Task 2** (FLI-127): Move shadcn to devDependencies in `web/package.json`
- Remove `"shadcn"` from `dependencies`
- Add `"shadcn"` with same version to `devDependencies`
- Run `npm install` to update lockfile

**Task 3** (FLI-128): Switch to local Geist font in `web/app/layout.tsx`
- Install `geist` package: `npm install geist`
- Replace `import { Geist, Geist_Mono } from "next/font/google"` with imports from `geist/font/sans` and `geist/font/mono`
- The `geist` package exports `GeistSans` and `GeistMono` which are already configured `next/font/local` instances with the `variable` property
- Update the `<body>` className to use the new variable names

### Batch 2: Prisma Setup (FLI-116 part 1)

**Task 4**: Install Prisma dependencies
- `cd web && npm install @prisma/client && npm install -D prisma`
- `npx prisma init --datasource-provider postgresql` (creates `prisma/` dir and updates `.env`)
- Delete the auto-generated `.env` if created (we use `.env.local` for local dev)

**Task 5**: Write `web/prisma/schema.prisma` manually based on SQLAlchemy models
- `datasource db` with `provider = "postgresql"` and `env("DATABASE_URL")`
- `generator client` with `provider = "prisma-client-js"`
- Model `SearchConfig` mapping to `search_configs` (use `@@map`)
- Model `ScanRun` mapping to `scan_runs`
- Model `PriceSnapshot` mapping to `price_snapshots`
- Model `PriceAlert` mapping to `price_alerts`
- All field names in camelCase with `@map("snake_case")` for column mapping
- Relations: SearchConfig → ScanRun[], PriceAlert[]; ScanRun → PriceSnapshot[]
- Indexes matching the SQLAlchemy indexes (use `@@index`)
- String fields for enum-like columns (status, search_type, alert_type) — no Prisma enums

**Task 6**: Create `web/lib/prisma.ts` — singleton Prisma Client
```typescript
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma: PrismaClient };

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["query", "error", "warn"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
```

**Task 7**: Add `DATABASE_URL` to `web/.env.example`
```
DATABASE_URL="postgresql://flight_watcher:changeme@localhost:5432/flight_watcher"
```

### Batch 3: API Routes (FLI-116 part 2)

**Task 8**: `web/app/api/configs/route.ts` — GET list, POST create
- GET: `prisma.searchConfig.findMany({ orderBy: { createdAt: "desc" } })` — return all configs
- POST: validate body (origin, destination, mustArriveBy, mustStayUntil, maxTripDays required), `prisma.searchConfig.create()`, return 201

**Task 9**: `web/app/api/configs/[id]/route.ts` — GET one, PUT update, DELETE
- GET: `findUnique` by id, 404 if not found, include scanRuns count and latest alert
- PUT: validate body, `prisma.searchConfig.update()`, return updated
- DELETE: `prisma.searchConfig.delete()`, return 204

**Task 10**: `web/app/api/snapshots/route.ts` — GET list with filters
- Query params: `configId`, `origin`, `destination`, `flightDate`, `brand`
- `prisma.priceSnapshot.findMany()` with dynamic where clause
- Order by `fetchedAt` desc, take 100

**Task 11**: `web/app/api/alerts/route.ts` — GET list
- Query params: `configId`, `origin`, `destination`
- `prisma.priceAlert.findMany()` with dynamic where
- Order by `createdAt` desc, take 50

**Task 12**: `web/app/api/runs/route.ts` — GET list
- Query params: `configId`, `status`
- `prisma.scanRun.findMany()` with dynamic where
- Include `_count: { select: { priceSnapshots: true } }` for snapshot count
- Order by `startedAt` desc, take 50

### Batch 4: Docker-compose (FLI-121)

**Task 13**: Update `docker-compose.yml` web service
- Add `DATABASE_URL` env var: `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:${POSTGRES_PORT:-5432}/${POSTGRES_DB}`
- Verify `POSTGRES_PORT` default is consistent (add `:-5432` fallback)

**Task 14**: Update root `.env.example`
- Add `# Web Dashboard` section with `DATABASE_URL` entry
- Document that DATABASE_URL is composed automatically in docker-compose

**Task 15**: Add `web/.env.local` to root `.gitignore` if not already present

### Batch 5: Prisma generation + build verification

**Task 16**: Run `npx prisma generate` in `web/` to verify schema compiles
**Task 17**: Run `npm run build` in `web/` to verify no TypeScript/build errors
**Task 18**: Run `npm run lint` in `web/` to verify no lint errors

## Acceptance Criteria

### FLI-116
- Prisma schema in `web/prisma/schema.prisma` matches all 4 SQLAlchemy tables
- Singleton Prisma client in `web/lib/prisma.ts`
- API routes: GET/POST `/api/configs`, GET/PUT/DELETE `/api/configs/[id]`, GET `/api/snapshots`, GET `/api/alerts`, GET `/api/runs`
- All routes return JSON with `{ data }` wrapper
- Error responses return `{ error }` with appropriate HTTP status codes
- `npm run build` passes

### FLI-121
- `DATABASE_URL` env var added to docker-compose web service
- `.env.example` updated with DATABASE_URL documentation
- PostgreSQL 18-alpine remains pinned (already is)

### FLI-126
- All `--sidebar-*` CSS variables removed from globals.css (@theme, :root, .dark)
- Build still passes

### FLI-127
- `shadcn` package listed in devDependencies, not dependencies
- `npm install` succeeds

### FLI-128
- `geist` package installed
- `layout.tsx` uses local font imports instead of `next/font/google`
- No network calls to fonts.googleapis.com at build time
- Build passes

## Verification

```bash
cd web
npm install          # Verify deps resolve
npx prisma generate  # Verify schema compiles
npm run build        # Verify no TS/build errors
npm run lint         # Verify no lint errors
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Lint passes
- [ ] Prisma generates successfully
- [ ] PR created with `Closes FLI-116`, `Closes FLI-121`, `Closes FLI-126`, `Closes FLI-127`, `Closes FLI-128`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests for API routes (no test framework in web/ yet)
- Adding authentication/authorization to API routes
- Adding pagination (cursor/offset) — simple take limits for now
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Running `prisma migrate` or `prisma db push` — Python/Alembic owns the schema
- Setting up a read-only PostgreSQL user
