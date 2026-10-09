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
│ • OpenXR        │    │ • Ollama         │    │ • Pinia         │
│ • Voice / WS    │    │ • Stable Diff.   │    │ • Charts        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

- **Backend server:** `http://192.168.4.249:8000`
- **Dashboard dev server:** `http://localhost:3001`
- **WebSocket base:** `ws://192.168.4.249:8000/api/v1/ws`

## Voice-to-VR Pipeline

The implemented end-to-end flow in [ImmersiveActivity.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ImmersiveActivity.kt):

1. **Record** — Hold Button A to capture a voice prompt.
2. **Transcribe** — Audio is sent to `POST /api/v1/voice/transcribe` (Whisper).
3. **Confirm** — A WebView HTML panel shows the transcription; Button A confirms, Button B retries.
4. **Plan** — `POST /api/v1/planning/generate-project` returns a full AI project: phases, tasks, materials, cost, timeline, and a generated image prompt.
5. **Display plan** — Project info panel renders name, cost, timeline, phases, and materials.
6. **Watch image generation** — VR [ProgressBar.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ProgressBar.kt) connects to the image WebSocket and animates until the rendered house image is shown on a panel.
7. **Walk the house** — [HouseGenerator.kt](construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/HouseGenerator.kt) fetches geometry from `GET /api/v1/projects/{id}/generate-vr` on an IO thread, then builds Meta Spatial entities on the main thread.

## Components

### Backend Core (`backend-core/backend`)

FastAPI service that coordinates AI planning, image generation, voice transcription, and VR geometry.

- **Framework:** FastAPI, SQLAlchemy 2.0, Pydantic, Alembic
- **Database:** PostgreSQL
- **AI:** Ollama (Llama 3.1) for planning, Stable Diffusion for renderings, Whisper for speech-to-text
- **Realtime:** WebSockets for image-generation progress and room collaboration
- **Deployment:** Docker Compose with optional GPU profile

Key endpoints used by the VR app:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `POST` | `/api/v1/planning/generate-project` | Full AI project generation |
| `GET`  | `/api/v1/projects/{id}/generate-vr` | VR geometry JSON |
| `POST` | `/api/v1/voice/transcribe` | Whisper transcription |
| `WS`   | `/api/v1/ws/image-progress/{id}` | Image generation progress |
| `WS`   | `/api/v1/ws/room/{roomId}` | Real-time room collaboration |
| `GET`  | `/docs` | Interactive OpenAPI docs |

See [backend-core/backend/README.md](backend-core/backend/README.md) for setup details.

### Dashboard (`backend-core/dashboard`)

Vue 3 + Quasar + Pinia management UI for projects, materials, generated images, and run history. Runs on port **3001**.

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

### Backend

```bash
cd backend-core/backend
cp .env.example .env      # edit DB + AI settings
docker compose --profile dev up -d
open http://localhost:8000/docs
```

### Dashboard

```bash
cd backend-core/dashboard
npm install
npm run dev
open http://localhost:3001
```

### VR App

```bash
cd construction-quest
./gradlew assembleDebug
./gradlew installDebug     # with Quest connected via adb
```

Or open `construction-quest/` in Android Studio and Run.

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
# Backend
cd backend-core/backend && pytest

# Dashboard
cd backend-core/dashboard && npm run test

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
- **Ollama** for local Llama 3.1 hosting
- **Stability AI** for Stable Diffusion
- **OpenAI Whisper** for speech-to-text
- **FastAPI**, **Vue 3**, and **Quasar** communities
