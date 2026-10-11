# VR AI Construction Project

End-to-end pipeline that turns a spoken prompt into a walkable VR house on Meta Quest 2/3. Speak a design, watch an AI generate the plan and renderings, then step inside the generated 3D environment.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-orange.svg)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Vue.js-3-green.svg)](https://vuejs.org/)
[![Kotlin](https://img.shields.io/badge/Kotlin-Meta%20Spatial%20SDK-purple.svg)](https://developers.meta.com/horizon/develop/spatial-sdk/)
[![Android](https://img.shields.io/badge/Android-API%2034+-brightgreen.svg)](https://developer.android.com/)

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Meta Quest    │    │   Backend Core   │    │    Dashboard    │
│    (VR App)     │◄──►│  (AI Services)   │◄──►│   (Web UI)      │
│                 │    │                  │    │                 │
│ • Kotlin        │    │ • FastAPI        │    │ • Vue 3         │
│ • Meta Spatial  │    │ • PostgreSQL     │    │ • Quasar        │
│ • OpenXR        │    │ • Groq / Ollama  │    │ • Pinia         │
│ • Voice / WS    │    │ • Stable Diff.   │    │ • Charts        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

- **Backend server:** `http://192.168.4.249:8000`
- **Dashboard dev server:** `http://localhost:3001`
- **WebSocket base:** `ws://192.168.4.249:8000/api/v1/ws`

The headset reaches the backend by LAN IP. Set it once in `construction-quest/gradle.properties`
(`serverHost=…`, or `-PserverHost=…` on the command line); the app's `SERVER_URL`, `WS_URL` and
dashboard URL are generated from it into `BuildConfig`.

## Voice-to-VR Pipeline

The implemented end-to-end flow in [ImmersiveActivity.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ImmersiveActivity.kt):

The headset uses two voice prompts — **floor plan first, then the look of the house**. Each prompt is recorded by holding Button A, transcribed by Whisper (`POST /api/v1/voice/transcribe`), and shown on a WebView panel to confirm (Button A) or retry (Button B).

**Step 1 — Floor plan**

1. Describe the rooms, layout and size. The planner acts as a residential architect: it zones the house, draws the floor plan by dividing the house's footprint into zones and rooms (so hallways can run the length of the house and rooms keep their own sizes) and lists which rooms open into each other, and the backend cuts real doorways (and windows on outside walls) into the walls so you can walk through the house from the front door.
2. [HouseGenerator.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/HouseGenerator.kt) calls `POST /api/v1/planning/generate-vr-from-prompt` on an IO thread, then builds the Meta Spatial entities on the main thread.
3. You are placed inside the house with room labels on; the prompt panel moves with you.

**Step 2 — House look**

4. From inside the house, describe the style, materials and colours.
5. `POST /api/v1/image/generate` starts Stable Diffusion; [ProgressBar.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ProgressBar.kt) follows `WS /api/v1/ws/image-progress/{id}` until the image is ready.
6. Review the image on a large panel:
   - **Accept** (A) — the image moves to a small grabbable panel you can keep while walking.
   - **Edit Prompt** (B) — the image is deleted and you re-record step 2; the house stays.
   - **Start Over** — the image and the house are cleared and you return to step 1.

While walking: right trigger teleports, B clears the house, left X toggles x-ray, left Y toggles room labels.

Projects can also be sent to the headset from the dashboard panel in VR: **Load to VR** calls
`POST /api/v1/projects/{id}/load-to-vr`, which starts a rendering and returns its `generation_id`; the
dashboard hands both ids to the headset (`Android.loadProjectWithImage`), which replaces the current
house with `GET /api/v1/projects/{id}/generate-vr` and shows the rendering for review when it is ready.

## Components

### Backend Core (`backend-core/backend`)

FastAPI service that coordinates AI planning, image generation, voice transcription, and VR geometry.

- **Framework:** FastAPI, SQLAlchemy 2.0, Pydantic, Alembic
- **Database:** PostgreSQL
- **AI:** Groq (`openai/gpt-oss-120b` by default) for planning with Ollama (`llama3.1:8b`) and Gemini fallbacks, Stable Diffusion (Realistic Vision 5.1 + Compel for long prompts) for renderings, faster-whisper for speech-to-text
- **Realtime:** WebSockets for image-generation progress and room collaboration
- **Deployment:** runs natively for development (`start_all.sh`); Docker Compose provides PostgreSQL/pgAdmin (and `docker-compose.prod.yml` a production stack)

Key endpoints used by the VR app:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/voice/transcribe` | Whisper transcription |
| `POST` | `/api/v1/planning/generate-vr-from-prompt` | VR geometry from a floor-plan prompt (step 1) |
| `POST` | `/api/v1/image/generate` | Start 2D image generation (step 2) |
| `WS`   | `/api/v1/ws/image-progress/{id}` | Image generation progress |
| `GET`  | `/api/v1/projects/{id}/generate-vr` | VR geometry for a saved project (dashboard) |
| `POST` | `/api/v1/planning/generate-project` | Full AI project (phases, tasks, materials, cost) |
| `WS`   | `/api/v1/ws/room/{roomId}` | Real-time room collaboration |
| `GET`  | `/docs` | Interactive OpenAPI docs |

See [backend-core/backend/README.md](backend-core/backend/README.md) for setup details.

### Dashboard (`backend-core/dashboard`)

Vue 3 + Quasar + Pinia management UI for projects, materials, generated images, and run history, plus a 2D floor plan of the selected project's house. Runs on port **3001**.

### Construction Quest VR App (`construction-quest`)

Kotlin Android app for Meta Quest 2/3 built on the **Meta Spatial SDK** (OpenXR). No C++ core — all VR logic is Kotlin + Meta Spatial entities.

- **Platform:** Android API 34+, Meta Quest 2/3
- **VR framework:** Meta Spatial SDK / OpenXR
- **Networking:** OkHttp (HTTP + WebSocket)
- **Build:** Gradle

Core files:

- [ImmersiveActivity.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ImmersiveActivity.kt) — main VR activity, voice capture, WebSocket wiring, panels, generation orchestration
- [HouseGenerator.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/HouseGenerator.kt) — fetches VR geometry and creates 3D entities (IO fetch → main-thread build)
- [ProgressBar.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ProgressBar.kt) — VR progress bar (background + fill entities) driven by the image-progress WebSocket
- [PanelActivity.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/PanelActivity.kt) — WebView-backed confirmation and info panels

Technical notes live in [construction-quest/documents/](construction-quest/documents/).

## Quick Start

### Prerequisites

- Meta Quest 2/3
- Python 3.12+
- Node.js 18+
- Android Studio (Giraffe or newer)
- Docker (recommended for backend)
- NVIDIA GPU (recommended for Stable Diffusion)

### Backend + dashboard

```bash
cd backend-core/backend
cp .env.example .env                  # DB settings, GROQ_API_KEY (and optional GEMINI_API_KEY)
python3.12 -m venv venv && venv/bin/pip install -r requirements.txt
docker compose up -d postgres pgadmin # database only; the backend runs natively

cd ../..
./start_all.sh                        # uvicorn on :8000 + Vite on :3001; Ctrl+C stops both
```

`start_all.sh` frees ports 8000/3001, waits for the backend to answer, then starts the dashboard; the
backend log goes to `backend-core/backend/backend.log`. Use `./restart_backend.sh` to restart only the
backend. API docs: `http://localhost:8000/docs`; dashboard: `http://localhost:3001`.

### VR App

```bash
cd construction-quest
./gradlew assembleDebug
./gradlew installDebug     # with Quest connected via adb
```

Or open `construction-quest/` in Android Studio and Run. The `gradlew` script is not committed; generate it with `gradle wrapper` (Gradle 9.x) or build from Android Studio.

## Project Structure

```
vr-ai-construction-project/
├── backend-core/
│   ├── backend/          # FastAPI application
│   └── dashboard/        # Vue 3 + Quasar management UI
├── construction-quest/   # Kotlin VR app (Meta Spatial SDK)
│   ├── app/              # Android module
│   └── documents/        # Technical notes
└── README.md
```

## Testing

```bash
# Backend (venv active)
cd backend-core/backend && pytest

# Dashboard
cd backend-core/dashboard && npx vitest run && npx vue-tsc --noEmit && npm run lint

# VR app
cd construction-quest && ./gradlew test
```

## Roadmap

- AI furniture placement
- Real-time multi-user VR collaboration
- Advanced PBR textures
- Construction phase simulation
- CAD / PDF export

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- **Meta Spatial SDK** and **OpenXR** for the VR runtime
- **Groq** and **Ollama** for LLM planning
- **Stability AI** for Stable Diffusion
- **OpenAI Whisper** for speech-to-text
- **FastAPI**, **Vue 3**, and **Quasar** communities
