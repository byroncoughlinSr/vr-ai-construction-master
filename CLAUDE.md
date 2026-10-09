# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

End-to-end pipeline that turns a spoken prompt into a walkable VR house on Meta Quest 2/3:
voice → Whisper transcription → LLM construction plan → Stable Diffusion rendering →
3D geometry → Meta Spatial entities the user walks through. Three deployable parts talk over
HTTP/WebSocket; there is no shared code between them — the contract is the JSON on the wire.

```
construction-quest (Kotlin/Quest)  ──HTTP/WS──►  backend-core/backend (FastAPI)  ◄──HTTP──  backend-core/dashboard (Vue 3)
```

- Backend server: `http://192.168.4.249:8000`  (LAN IP — the Quest must reach this, not localhost)
- Dashboard dev server: `http://localhost:3001` (Vite binds `0.0.0.0`; the Quest loads it by LAN IP)
- WebSocket base: `ws://192.168.4.249:8000/api/v1/ws`

## Commands

### Backend (`backend-core/backend`)
```bash
./restart_backend.sh              # from repo root: kills port 8000, activates venv, runs uvicorn --reload
source venv/bin/activate          # the venv lives in backend-core/backend/venv
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload   # manual run (must bind 0.0.0.0 so Quest can reach it)
pytest                            # all backend tests
pytest tests/test_api.py          # one file
pytest tests/test_api.py::test_name   # one test
alembic revision --autogenerate -m "msg"  # new migration
alembic upgrade head                      # apply migrations
docker compose up -d               # postgres + pgadmin + backend (no profiles here;
                                   # docker-compose.prod.yml is the one with profiles)
```
There is no `pytest.ini`/`conftest.py` — run `pytest` from `backend-core/backend` with the venv active.
Config comes from `.env` (copy `.env.example`); `app/config.py` is the Pydantic settings source of truth.

**LLM provider chain** (`ai_planning_service.py`, in priority order):
1. **Groq** — the primary planner. `GROQ_API_KEY` + `GROQ_MODEL` (default `llama-3.3-70b-versatile`),
   called with `response_format={'type':'json_object'}`.
2. **Ollama** — fallback. Runs **natively, not in Docker** (Docker Ollama was OOM-killed); model
   `llama3.1:8b` exactly, `OLLAMA_URL=http://172.17.0.1:11434` in `.env`.
   See `QUICK_START.md` / `NATIVE_OLLAMA_SETUP.md`.
3. **Gemini** — last-resort fallback, `GEMINI_API_KEY`.

Each provider is probed at service construction, so a missing key just silently demotes to the next one —
check the startup logs to know which planner actually ran.

### Dashboard (`backend-core/dashboard`)
```bash
npm run dev        # Vite dev server on :3001
npm run build      # vue-tsc typecheck + vite build
npm run lint       # eslint --fix
npm run test       # vitest (watch)
npx vitest run src/services/__tests__/imageProgress.spec.ts   # one test file
```
`vite.config.ts` proxies `/api` → `http://localhost:8000`, so the dev server expects uvicorn on the
same machine, and binds `0.0.0.0` so the in-headset WebView can load it over the LAN.

### VR app (`construction-quest`)
```bash
./gradlew assembleDebug      # build APK
./gradlew installDebug       # install to Quest over adb
./gradlew test               # unit tests
```
Targets Quest 2/3: `minSdk 29`, `targetSdk/compileSdk 34`, JVM 17. Includes a native C++ layer
(`app/src/main/cpp`, built via CMake/NDK, `arm64-v8a` only). `local.properties` (SDK/NDK paths,
not committed) must be present to build.

## Architecture

### Backend — FastAPI (`backend-core/backend/app`)
- `main.py` mounts all routers under `/api/v1/*` and wires middleware (rate limiting via slowapi,
  CORS, gzip, request-ID logging). Router prefixes: `image`, `planning`, `projects`, `designs`,
  `materials`, `voice`, `ws`.
- `api/v1/` = HTTP/WS surface; `services/` = the actual AI + geometry logic; `models/` SQLAlchemy,
  `schemas/` Pydantic. Routes stay thin and delegate to services.
- **AI services** (`services/`): `ai_planning_service.py` (Groq→Ollama→Gemini → phases, tasks,
  materials, cost, timeline, image prompt), `ai_image_service.py` (Stable Diffusion + compel,
  CUDA when available else CPU), and `vr_geometry_service.py` (rooms → floor/wall/ceiling/door/window
  vertices).
- **Never trust raw LLM output as JSON.** `ai_planning_service.py` runs everything through
  `_parse_structured_plan` → `_extract_and_repair_json` / `_clean_json_string`: it strips code fences,
  fixes trailing/missing commas and Python literals, and closes truncated objects/arrays. If you add a
  provider or change the plan schema, route it through that pipeline. Background in `JSON_PARSING_FIX.md`.
- DB is PostgreSQL via SQLAlchemy 2.0; migrations with Alembic (`alembic.ini`, `alembic/`).

### VR geometry — the cross-language contract that breaks silently
`vr_geometry_service.py` builds the JSON that `HouseGenerator.kt` turns into 3D boxes. Three
constants **must** stay in sync across the language boundary or the house develops visible seams:
- `WALL_T = 0.1` (half wall thickness) must equal `Box(..., 0.1f)` in `HouseGenerator.kt`.
- `FT_TO_M = 0.3048` — the AI returns dimensions in **feet**; the VR world is **metres** (1 unit = 1 m).
  Conversion happens backend-side; Kotlin consumes metres directly.
- `SCALE = 2.0f` in `HouseGenerator.kt` — **every** position, dimension and spawn point from the JSON is
  multiplied by it on the Kotlin side. Anything you add to the geometry JSON must be scaled too, or it
  lands at half size / half distance relative to the rest of the house.

Rooms pack edge-to-edge in rows (`compute_packed_positions`, default 3 columns); rooms in a row
share the row's max width so north/south walls flush without gaps. Rotation values are sent in
**degrees** in the JSON — `HouseGenerator.kt` must `Math.toDegrees(atan2(...))` because
`Quaternion(...)` expects degrees, and must apply each element's `rotation` field. The history of
seam/rotation bugs and the exact fixes is documented in `claude.md` (despite the name, it is a
fix-notes doc, not guidance) and `LOAD_TO_VR_FIX.md` — read these before touching geometry.

### VR app — Kotlin + Meta Spatial SDK (`construction-quest/app/src/main/java/.../`)
- `ImmersiveActivity.kt` — main activity; orchestrates the whole pipeline: voice capture, the
  transcribe/confirm/plan/image/build sequence, WebSocket wiring, and panel display.
- `HouseGenerator.kt` — fetches geometry and builds entities. **Thread rule:**
  `fetchVRGeometry(projectId)` does the HTTP call on an **IO thread**; `buildFromGeometry(...)`
  calls `Entity.create()` and **must run on the main/UI thread** (`runOnUiThread { ... }`).
  `buildFromGeometry` calls `clearAllEntities()` first, so rebuilding replaces the house rather than
  stacking a second one; entity handles live in `roomEntities`/`doorEntities`/`windowEntities` and
  anything you create must be tracked there or it leaks across rebuilds.
- `ProgressBar.kt` — two-entity (background + fill) VR progress bar driven by the image-progress WS.
- `PanelActivity.kt` — WebView-backed confirmation/info panels (HTML rendered in VR).
- Networking is OkHttp (HTTP + WebSocket).

### Dashboard — Vue 3 + Quasar + Pinia (`backend-core/dashboard`)
Management UI for projects, materials, generated images, and run history. Vite + TypeScript
(`npm run build` runs `vue-tsc` first, so type errors fail the build).

## Pipeline (the path through the code)
1. Hold Button A → record → `POST /api/v1/voice/transcribe` (Whisper).
2. WebView confirm panel → Button A confirm / Button B retry.
3. `POST /api/v1/planning/generate-project` → full AI project (phases, tasks, materials, cost,
   timeline, image prompt).
4. Project info panel renders the plan.
5. Connect `WS /api/v1/ws/image-progress/{id}` → ProgressBar animates until the rendered image shows.
6. `GET /api/v1/projects/{id}/generate-vr` on IO thread → `runOnUiThread { buildFromGeometry(...) }`.

**Second entry point — dashboard-driven:** the dashboard calls
`POST /api/v1/projects/{id}/load-to-vr` (generates the image in the background and prepares geometry,
returning a `generation_id` for the progress WS); the headset side is `loadProjectById(projectId)` in
`ImmersiveActivity.kt`, which **early-returns when `locomotionEnabled` is true** — i.e. a house is
already loaded. `ImmersiveActivity` also opens the dashboard itself in a VR WebView at
`http://192.168.4.249:3001`.

Key endpoints: `POST /api/v1/planning/generate-project`, `GET /api/v1/projects/{id}/generate-vr`,
`POST /api/v1/voice/transcribe`, `WS /api/v1/ws/image-progress/{id}`, `WS /api/v1/ws/room/{roomId}`.
Interactive docs at `/docs`. There is also `POST /api/v1/planning/generate-vr-from-prompt` and
`POST /api/v1/designs/{id}/generate-vr`, which share `vr_geometry_service.py` with the project route.

## Gotchas
- The Quest reaches the backend by **LAN IP**, never `localhost`. If geometry/voice calls fail from
  the headset, check the hard-coded server IP in the Kotlin source matches the machine running uvicorn.
- Uvicorn must bind `0.0.0.0` (the restart script does); binding `127.0.0.1` makes it invisible to the headset.
- Use `llama3.1:8b` exactly on the Ollama path — `llama3.1:latest` was getting OOM-killed.
- `SERVER_URL` / `WS_URL` and the dashboard URL are hard-coded near the top of `ImmersiveActivity.kt`
  (`192.168.4.249`); all three must be changed together when the host machine's IP changes.
- Provider fallback hides failures: a plan that looks wrong may have come from Ollama or Gemini rather
  than Groq. Check the log line naming the planner before debugging prompt/schema issues.
- The repo root holds many one-off `*.md` fix logs and `test_*.py` scratch scripts from past debugging
  sessions; they are history/notes, not the canonical test suite (which is `backend-core/backend/tests/`).
