# VR AI Construction Project

A professional-grade VR construction design platform that combines AI-powered planning with immersive virtual reality design tools. Design, plan, and visualize construction projects in VR using Meta Quest, powered by machine learning for intelligent assistance.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-green.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-orange.svg)](https://fastapi.tiangolo.com/)
[![Vue.js](https://img.shields.io/badge/Vue.js-3-green.svg)](https://vuejs.org/)
[![Android](https://img.shields.io/badge/Android-API%2034+-brightgreen.svg)](https://developer.android.com/)
[![C++](https://img.shields.io/badge/C++-17+-blue.svg)](https://isocpp.org/)

## 🎯 Active Project: The Tiny House

**Objective:** Design a 20sqm modern tiny house with AI-assisted planning
- **Base Materials:** Cedar Wood & Concrete
- **Key Features:** Floor-to-ceiling glass windows, lofted sleeping area, modular wall layout
- **AI Integration:** Materials list generation and cost estimation

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Meta Quest    │    │   Backend Core   │    │   Dashboard     │
│   (VR Design)   │◄──►│   (AI Services)  │◄──►│   (Management)  │
│                 │    │                  │    │                 │
│ • C++ Engine    │    │ • FastAPI        │    │ • Vue.js        │
│ • OpenXR        │    │ • PostgreSQL     │    │ • Quasar        │
│ • Voice Control │    │ • AI Models      │    │ • Charts        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 📦 Components

### Backend Core

A comprehensive FastAPI-based backend service providing AI-powered construction planning and management.

**Key Features:**
- **AI-Powered Generation**: Stable Diffusion for architectural visualization, Ollama for construction planning
- **Voice Integration**: Whisper STT for voice commands and design input
- **Database Management**: PostgreSQL with comprehensive project tracking (15+ tables)
- **Real-time Communication**: WebSocket support for live updates
- **Export Capabilities**: PDF reports, HTML viewers, and VR geometry generation

**Tech Stack:**
- **Backend**: FastAPI, SQLAlchemy 2.0, Pydantic
- **Database**: PostgreSQL with Alembic migrations
- **AI**: Stable Diffusion, Ollama (Llama 3.1), Whisper
- **Frontend**: Vue.js 3 with Quasar Framework
- **Containerization**: Docker with GPU support

**API Endpoints:**
- `POST /api/v1/voice/transcribe` - Voice transcription
- `POST /api/v1/projects/{id}/generate-vr` - VR geometry generation
- `POST /api/v1/ai/image/generate` - AI image generation
- `GET /api/v1/materials/` - Materials catalog
- `GET /docs` - Interactive API documentation

For detailed setup and usage, see [backend-core/backend/README.md](backend-core/backend/README.md)

### Construction Quest

A high-performance VR application for Meta Quest 2/3, built with a C++ core for maximum performance and low-latency interactions.

**Key Features:**
- **Immersive Design**: Place walls, floors, and architectural elements in VR
- **Voice Commands**: Natural language design input with AI processing
- **Real-time VR Generation**: Walk through procedurally generated houses
- **Precision Tools**: Grid snapping, measurement tools, teleportation
- **Network Integration**: Real-time sync with backend services

**Tech Stack:**
- **Core Engine**: C++17 with OpenXR and Meta XR SDK
- **Graphics**: OpenGL ES 3.2 / Vulkan
- **Platform**: Android (API 34+) with JNI bridge
- **Math**: GLM (OpenGL Mathematics)
- **Networking**: libcurl for backend communication
- **Build**: CMake with Gradle integration

**VR Capabilities:**
- ✅ Walkable house generation from database designs
- ✅ Voice-controlled design modifications
- ✅ Real-time material and texture changes
- ✅ Measurement and scaling tools
- ✅ Collision detection and navigation
- ✅ X-ray vision and room labeling

For technical details, see [construction-quest/documents/](construction-quest/documents/)

## ✨ Key Features

### 🤖 AI-Powered Design
- **Intelligent Planning**: AI generates construction phases, timelines, and cost estimates
- **Voice Interface**: Natural language design input and modifications
- **Image Generation**: Stable Diffusion creates realistic architectural visualizations
- **Material Intelligence**: AI-assisted material selection and supplier matching

### 🕶️ VR Immersion
- **Walkable Designs**: Experience your house before construction begins
- **Precision Placement**: Grid-based snapping with sub-centimeter accuracy
- **Real-time Feedback**: Instant visual updates during design sessions
- **Multi-scale Design**: From tiny houses to large commercial projects

### 📊 Project Management
- **Comprehensive Tracking**: Budget, timeline, resources, and compliance
- **Visual Dashboards**: Charts and Gantt charts for project oversight
- **Document Management**: Photos, receipts, blueprints, and permits
- **Export Tools**: PDF reports, 3D models, and construction documents

### 🔗 Seamless Integration
- **Real-time Sync**: Changes in VR instantly update the database
- **Cross-platform**: Design in VR, manage on web dashboard
- **Voice Commands**: "Add a window here" or "Show me the kitchen"
- **API-First**: RESTful APIs enable third-party integrations

## 🚀 Quick Start

### Prerequisites
- **Meta Quest 2/3** (for VR design)
- **Python 3.12+** (for backend)
- **Node.js 18+** (for dashboard)
- **Android Studio** (for VR app development)
- **Docker** (recommended for backend)
- **GPU** (optional, for faster AI generation)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/your-username/vr-ai-construction-project.git
cd vr-ai-construction-project/backend-core/backend

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your database and AI settings

# Run with Docker (recommended)
docker compose --profile dev up -d

# Access API documentation
open http://localhost:8000/docs
```

### VR App Setup

```bash
cd construction-quest

# Build with Gradle
./gradlew assembleDebug

# Install on connected Quest device
./gradlew installDebug

# Or build in Android Studio
# Open construction-quest/ in Android Studio
# Build → Make Project
# Run → Run 'app'
```

### Dashboard Setup

```bash
cd backend-core/dashboard

# Install dependencies
npm install

# Start development server
npm run dev

# Access dashboard
open http://localhost:5173
```

## 🎮 Usage Example

1. **Start the Backend**: Run the FastAPI server with database and AI models
2. **Launch VR App**: Open Construction Quest on Meta Quest
3. **Design in VR**: Use controllers to place walls, add windows, set dimensions
4. **Voice Commands**: Say "Make this room bigger" or "Add hardwood floors"
5. **AI Assistance**: Request material suggestions or cost estimates
6. **Generate VR House**: Walk through your design as a complete 3D environment
7. **Manage Projects**: Use the web dashboard to track progress and budgets

## 🛠️ Development

### Project Structure
```
vr-ai-construction-project/
├── backend-core/           # Backend services and dashboard
│   ├── backend/           # FastAPI application
│   └── dashboard/         # Vue.js management interface
├── construction-quest/    # VR Android application
│   ├── app/              # Android app with C++ engine
│   └── documents/        # Technical specifications
└── README.md             # This file
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Testing

```bash
# Backend tests
cd backend-core/backend
pytest

# Dashboard tests
cd backend-core/dashboard
npm run test

# VR app tests (Android)
cd construction-quest
./gradlew test
```

## 📚 Documentation

- [Backend API Documentation](backend-core/backend/README.md)
- [VR Technical Architecture](construction-quest/documents/cpp-technical-plan.md)
- [AI Integration Guide](backend-core/Documents/backend-plan.md)
- [VR House Generation Workflow](backend-core/Documents/vr-house-workflow.md)

## 🤝 Support

- **Issues**: [GitHub Issues](https://github.com/your-username/vr-ai-construction-project/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-username/vr-ai-construction-project/discussions)
- **Discord**: Join our community for real-time support

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Meta XR SDK and OpenXR for VR capabilities
- Stability AI for Stable Diffusion models
- Ollama for local AI model hosting
- FastAPI and Vue.js communities for excellent frameworks

---

**Experience the future of construction design - where AI meets virtual reality.** 🏠🤖🕶️