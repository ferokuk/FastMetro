# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastMetro — web-app for calculating shortest paths in the Moscow metro. Backend fetches station data from HH API, builds a graph, and runs Dijkstra's algorithm. Frontend visualizes the metro graph and routes interactively.

## Tech Stack

- **Backend:** FastAPI 0.109.2, SQLAlchemy 2.0 (async), asyncpg, Pydantic 2, Python 3.12
- **Frontend:** Vue 3, TypeScript, Vite 6, Cytoscape.js (graph rendering)
- **Infra:** PostgreSQL 16, Nginx (reverse proxy), Docker Compose

## Commands

```bash
# Run everything (API :8000, frontend :8080/metro/)
docker-compose up --build

# Backend only (needs running Postgres)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend dev server (:5173)
cd frontend && npm install && npm run dev

# TypeScript type check
cd frontend && npm run type-check
```

No test suite exists yet.

## Architecture

**Backend (`app/`):**
- `main.py` — FastAPI app, all route handlers (`/stations`, `/path`, `/graph`, `/admin/refresh`, `/health`)
- `services/metro.py` — core logic: HH API data fetching, graph construction, Dijkstra pathfinding, extensive manual edge/station patches
- `models.py` — SQLAlchemy models: Station, Trip, EdgeType
- `schemas.py` — Pydantic response schemas
- `config.py` — settings via pydantic-settings
- `database.py` — async SQLAlchemy engine/session setup

**Frontend (`frontend/src/`):**
- `api/client.ts` — API client functions
- `components/RouteGraph.vue` — Cytoscape-based metro map visualization
- `components/StationSelect.vue` — searchable station dropdown

**Data flow:** On startup, DB is cleared and reloaded from HH API + manual patches. Pathfinding uses in-memory graph with time weights (3 min per segment, 6 min per transfer).

## Environment Variables

- `DATABASE_URL` — Postgres connection string (default: `postgresql+asyncpg://metro:metro@db:5432/metro`)
- `ADMIN_API_KEY` — required for `POST /admin/refresh`
- `TRANSFER_DISTANCE_THRESHOLD` — auto-transfer distance in degrees (default: 0.001)

## Key Details

- `services/metro.py` contains ~130 manual edge additions/removals (`EDGE_ADD`, `EDGE_REMOVE`) and station coordinate fixes (`STATION_FIXES`) to correct HH API data — do not remove these without understanding the impact
- Station IDs follow HH API format: `"<line_id>.<station_order>"` (e.g., `"1.148"`)
- Frontend Nginx proxies `/api/` to the backend container