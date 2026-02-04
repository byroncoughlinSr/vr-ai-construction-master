# VR Construction Design Platform - Complete Project Plan

## Executive Summary

**Project Name:** VR Construction Design Platform (Prototype)

**Vision:** A professional VR-based design tool enabling users to create detailed construction projects in Quest 2 VR, leveraging AI to generate photorealistic renderings and comprehensive construction plans including materials lists, timelines, and cost estimates. **Features natural voice commands** for hands-free VR interaction.

**Phase:** Prototype (Proof of Concept)
**Timeline:** 6-12 months
**Target:** Single-user development environment, minimal cost, maximum learning

---

## System Architecture

### High-Level Architecture
```
┌─────────────────────────┐   Local WiFi   ┌──────────────────┐
│      Quest 2 VR         │◄──────────────►│   GPU PC (Host)  │
│                         │  REST API/WS   │                  │
│  ┌──────────────────┐   │                │  Python Backend  │
│  │ Voice Recording  │   │                │   PostgreSQL     │
│  │ (MediaRecorder)  │   │                │   AI Models      │
│  └────────┬─────────┘   │                │                  │
│           │ Audio       │                │  ┌────────────┐  │
│           ▼             │   Send WAV     │  │  Whisper   │  │
│  ┌──────────────────┐   │───────────────►│  │   (STT)    │  │
│  │ Text Display     │◄──┼────────────────┤  └────────────┘  │
│  │ (Editable in VR) │   │  Return Text   │                  │
│  └────────┬─────────┘   │                │  ┌────────────┐  │
│           │             │                │  │  Ollama    │  │
│  User can edit/confirm  │  Send Text     │  │ Stable Dif │  │
│           │             │  as Prompt     │  │  (AI Gen)  │  │
│           ▼             │───────────────►│  └────────────┘  │
│  ┌──────────────────┐   │                └──────────────────┘
│  │ Send to AI       │   │
│  │ (User confirms)  │   │
│  └──────────────────┘   │
└─────────────────────────┘

Updated Voice-to-Text Flow:
1. User holds button and speaks
2. Quest 2 records audio
3. Audio sent to backend → Whisper transcribes
4. **Text returned to Quest 2 and displayed in VR**
5. **User sees text, can edit if needed**
6. **User confirms → Text sent as AI prompt**
7. Backend uses text for image generation, planning, etc.
8. Results shown in VR
```

### System Components

**1. Quest 2 VR Frontend**
- Language: C++ with Android NDK
- IDE: Android Studio
- SDK: Oculus SDK / Meta XR SDK
- Rendering: OpenGL ES / Vulkan
- UI: VR-native 3D interface

**2. PC Backend**
- OS: Ubuntu 24.04
- Language: Python 3.11+
- Framework: FastAPI (async, modern, fast)
- Database: PostgreSQL 16
- ORM: SQLAlchemy

**3. AI Services**
- **Image Generation:** Stable Diffusion (local via ROCm)
- **LLM Processing:** Ollama (Llama 3.1 8B quantized)
- **Speech-to-Text:** Whisper (OpenAI - base model)
- **Voice Command Parsing:** Ollama (natural language understanding)
- **Backup/Supplementary:** Gemini API (free tier)
- **Additional Models:** Hugging Face Inference API

**4. Communication**
- Protocol: REST API + WebSockets
- Format: JSON for data exchange
- Binary: Base64 encoded for images/3D data
- Local Network: Quest 2 and PC on same WiFi

---

## Technology Stack Details

### Quest 2 Frontend Stack

**Core Technologies:**
- Android API Level 29+ (Android 10+)
- Oculus SDK 57.0+
- C++17
- CMake 3.18+
- Gradle 8.0+

**Libraries:**
- GLM (OpenGL Mathematics)
- JSON for Modern C++ (nlohmann/json)
- libcurl or httplib for HTTP requests
- WebSocket++ for real-time communication

**VR Interactions:**
- Hand tracking
- Controller input
- Spatial anchors
- Passthrough API (optional)

### Backend Stack

**Python Environment:**
- Python 3.11+
- Virtual environment (venv)
- FastAPI 0.109+
- Uvicorn (ASGI server)
- SQLAlchemy 2.0+
- Pydantic for data validation

**AI/ML Libraries:**
- PyTorch 2.0+ (ROCm build for AMD)
- Transformers (Hugging Face)
- Diffusers (Stable Diffusion)
- Ollama Python client
- Google GenerativeAI (Gemini)

**Database:**
- PostgreSQL 16
- psycopg2 or asyncpg
- Alembic for migrations

**Additional Python Packages:**
- Pillow (image processing)
- NumPy (numerical operations)
- python-dotenv (environment variables)
- python-multipart (file uploads)
- aiofiles (async file operations)

### Hardware Requirements

**Development PC (Your Setup):**
- CPU: AMD Ryzen 5000 series ✓
- RAM: 11GB ✓
- GPU: AMD Lucienne (11GB VRAM) ✓
- OS: Ubuntu 24.04 ✓
- Storage: 50GB+ free (for models and data)

**Quest 2:**
- Firmware: Latest
- Storage: 128GB+ recommended
- WiFi: 5GHz network (802.11ac)

---

## Development Phases

### Phase 1: Environment Setup (Weeks 1-2)

**PC Environment Setup:**

1. **Install Development Tools**
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install build essentials
sudo apt install -y build-essential git curl wget

# Install Python 3.11+
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install Docker and Docker Compose
sudo apt install -y ca-certificates gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group (to run docker without sudo)
sudo usermod -aG docker $USER

# Log out and back in, or run:
newgrp docker

# Verify Docker installation
docker --version
docker compose version

# Install ROCm for AMD GPU (if not installed)
# Follow: https://rocm.docs.amd.com/en/latest/deploy/linux/quick_start.html

# Install Android Studio
# Download from: https://developer.android.com/studio
```

2. **Setup PostgreSQL with Docker**
```bash
# PostgreSQL will be set up via Docker Compose in Phase 2
# No manual installation needed!
```

3. **Install AI Models (On Host - Needs GPU Access)**
```bash
# Install Ollama (runs on host, not in Docker)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
systemctl --user start ollama
systemctl --user enable ollama

# Pull Llama model
ollama pull llama3.1:8b-instruct-q4_K_M

# Create Python virtual environment for AI tools (on host)
python3.11 -m venv ~/ai-venv
source ~/ai-venv/bin/activate

# Install Stable Diffusion dependencies (with ROCm support)
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm5.7
pip install diffusers transformers accelerate safetensors

# Install Whisper for Speech-to-Text
pip install openai-whisper
# Or use faster-whisper (optimized, recommended)
pip install faster-whisper

# Test Stable Diffusion
python3 << EOF
from diffusers import StableDiffusionPipeline
import torch
model = StableDiffusionPipeline.from_pretrained("stabilityai/stable-diffusion-2-1")
print("Stable Diffusion model downloaded successfully")
EOF

# Download Whisper model (first run will download automatically)
# Models: tiny, base, small, medium, large
# For prototype, use 'base' (good balance of speed/accuracy)
python3 << EOF
import whisper
model = whisper.load_model("base")
print("Whisper model downloaded successfully")
EOF

# Note: AI models run on HOST, not in Docker, to access GPU
```

4. **Setup Python Backend Project Structure**
```bash
# Create project directory
mkdir -p ~/vr-construction-platform
cd ~/vr-construction-platform

# Create backend directory
mkdir backend
cd backend

# Create directory structure
mkdir -p app/{api/v1,models,schemas,services,utils}
mkdir -p alembic/versions
mkdir -p generated_images exports uploads

# Create requirements.txt
cat > requirements.txt << EOF
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
alembic==1.13.1
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0
python-multipart==0.0.6
aiofiles==23.2.1
pillow==10.2.0
numpy==1.26.3
ollama==0.1.6
google-generativeai==0.3.2
torch==2.1.2
torchvision==0.16.2
diffusers==0.25.0
transformers==4.37.0
accelerate==0.26.1
safetensors==0.4.1
reportlab==4.0.9
websockets==12.0
openai-whisper==20231117
faster-whisper==1.0.0
pydub==0.25.1
EOF

# Create .env file
cat > .env << EOF
DATABASE_URL=postgresql://vr_admin:SecurePassword123!@postgres:5432/vr_construction
OLLAMA_URL=http://host.docker.internal:11434
GEMINI_API_KEY=your_key_here_optional
ENVIRONMENT=development
HOST=0.0.0.0
PORT=8000
EOF

# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p generated_images exports uploads

# Expose port
EXPOSE 8000

# Run migrations and start server
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
EOF

# Create .dockerignore
cat > .dockerignore << EOF
__pycache__
*.pyc
*.pyo
*.pyd
.Python
venv/
env/
.env.local
.git/
.gitignore
*.log
.pytest_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
EOF

# Create docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # PostgreSQL Database
  postgres:
    image: postgres:16
    container_name: vr_postgres
    environment:
      POSTGRES_DB: vr_construction
      POSTGRES_USER: vr_admin
      POSTGRES_PASSWORD: SecurePassword123!
      POSTGRES_INITDB_ARGS: "--encoding=UTF8"
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U vr_admin -d vr_construction"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - vr_network
    restart: unless-stopped

  # Python Backend API
  backend:
    build: .
    container_name: vr_backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://vr_admin:SecurePassword123!@postgres:5432/vr_construction
      OLLAMA_URL: http://host.docker.internal:11434
      ENVIRONMENT: development
    volumes:
      - ./app:/app/app  # Hot reload during development
      - ./alembic:/app/alembic
      - ./alembic.ini:/app/alembic.ini
      - generated_images:/app/generated_images
      - exports:/app/exports
      - uploads:/app/uploads
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - vr_network
    extra_hosts:
      - "host.docker.internal:host-gateway"  # Access host services (Ollama)
    restart: unless-stopped

  # pgAdmin (Optional - Database GUI)
  pgadmin:
    image: dpage/pgadmin4
    container_name: vr_pgadmin
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@vrconstruction.local
      PGADMIN_DEFAULT_PASSWORD: admin
      PGADMIN_LISTEN_PORT: 80
    ports:
      - "5050:80"
    depends_on:
      - postgres
    networks:
      - vr_network
    restart: unless-stopped

volumes:
  postgres_data:
  generated_images:
  exports:
  uploads:

networks:
  vr_network:
    driver: bridge
EOF

# Initialize Alembic (will be done after first docker-compose up)
# alembic init alembic will be run inside the container
```

**Deliverables:**
- ✓ All development tools installed
- ✓ Docker and Docker Compose installed
- ✓ AI models downloaded and running on host
- ✓ Backend project structure created
- ✓ Docker configuration files created
- ✓ Quest 2 in developer mode
- ✓ ADB wireless connection working

**Quest 2 Setup:**

1. **Enable Developer Mode**
   - Install Meta Quest mobile app
   - Enable developer mode on Quest 2
   - Accept developer terms

2. **Install Android Studio**
   - Download and install Android Studio
   - Install Android SDK and NDK
   - Configure Oculus/Meta XR SDK

3. **Setup ADB Connection**
```bash
# Install ADB
sudo apt install -y android-tools-adb

# Connect Quest 2 via USB
adb devices

# Enable WiFi debugging (Quest 2 IP: find in settings)
adb tcpip 5555
adb connect <QUEST_IP>:5555
```

**Deliverables:**
- ✓ All development tools installed
- ✓ Database created and accessible
- ✓ AI models downloaded and tested
- ✓ Quest 2 in developer mode
- ✓ ADB wireless connection working

---

### Phase 2: Backend Foundation (Weeks 3-5)

**Note:** PostgreSQL is now running in Docker. All database operations use `docker compose exec postgres` or connect via `localhost:5432`.

**Project Structure:**
```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app entry
│   ├── config.py               # Configuration
│   ├── database.py             # Database connection
│   ├── models/                 # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── project.py
│   │   ├── design.py
│   │   ├── material.py
│   │   └── ai_generation.py
│   ├── schemas/                # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── project.py
│   │   ├── design.py
│   │   └── material.py
│   ├── api/                    # API routes
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── projects.py
│   │   │   ├── designs.py
│   │   │   ├── materials.py
│   │   │   ├── ai_image.py
│   │   │   ├── ai_planning.py
│   │   │   └── voice.py        # NEW: Voice commands
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   ├── design_service.py
│   │   ├── ai_image_service.py
│   │   ├── ai_planning_service.py
│   │   ├── speech_service.py   # NEW: Speech-to-text
│   │   └── material_service.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── alembic/                    # Database migrations
│   ├── versions/
│   └── env.py
├── tests/
│   ├── __init__.py
│   └── test_api.py
├── .env                        # Environment variables
├── requirements.txt
└── alembic.ini
```

**Database Schema:**

## **Comprehensive Project Management Database Design**

### **Philosophy: Store Base Data + Generate Dynamically**

**Best Approach:**
- ✅ **Store** foundational timeline/schedule in database
- ✅ **Generate/Update** dynamically when project changes
- ✅ **Cache** last generated timeline for quick display
- ✅ **Track history** of timeline changes

**Why this hybrid approach?**
1. **Fast display** - Show cached timeline immediately
2. **Accurate** - Regenerate when design/materials change
3. **Historical** - Track how timeline evolved
4. **Flexible** - AI can optimize timeline on demand

---

### **Complete Database Schema:**

**Create schema using Alembic migrations:**

```bash
# Create initial migration inside Docker container
docker compose exec backend alembic revision --autogenerate -m "comprehensive project schema"

# Apply migration
docker compose exec backend alembic upgrade head

# Or apply SQL directly
docker compose exec -T postgres psql -U vr_admin -d vr_construction << 'EOF'

-- ============================================================================
-- CORE PROJECT TABLES
-- ============================================================================

-- Projects - Main project information
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    project_type VARCHAR(50),  -- 'house', 'building', 'dog_house', 'garage', 'addition'
    
    -- Project metadata
    location VARCHAR(255),
    address TEXT,
    lot_size FLOAT,  -- square feet
    climate_zone VARCHAR(50),
    
    -- Dimensions
    total_square_footage FLOAT,
    number_of_floors INTEGER DEFAULT 1,
    building_height FLOAT,  -- in feet
    
    -- Budget & Timeline
    target_budget DECIMAL(12, 2),
    target_completion_days INTEGER,
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'draft',  -- 'draft', 'planning', 'in_progress', 'completed', 'on_hold'
    progress_percentage DECIMAL(5, 2) DEFAULT 0.00,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Additional data
    metadata JSONB  -- Flexible field for custom data
);

-- Design elements (walls, rooms, components)
CREATE TABLE design_elements (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Element identification
    element_type VARCHAR(50),  -- 'wall', 'room', 'door', 'window', 'floor', 'roof', 'foundation'
    element_name VARCHAR(255),
    
    -- 3D Position & Orientation
    position_x FLOAT,
    position_y FLOAT,
    position_z FLOAT,
    rotation_x FLOAT DEFAULT 0,
    rotation_y FLOAT DEFAULT 0,
    rotation_z FLOAT DEFAULT 0,
    scale_x FLOAT DEFAULT 1,
    scale_y FLOAT DEFAULT 1,
    scale_z FLOAT DEFAULT 1,
    
    -- Dimensions
    length FLOAT,
    width FLOAT,
    height FLOAT,
    
    -- Properties
    properties JSONB,  -- {color, texture, structural_properties, etc}
    
    -- Relationships
    parent_element_id INTEGER REFERENCES design_elements(id) ON DELETE CASCADE,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- MATERIALS & RESOURCES
-- ============================================================================

-- Materials catalog (master list of available materials)
CREATE TABLE materials (
    id SERIAL PRIMARY KEY,
    
    -- Basic info
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),  -- 'lumber', 'concrete', 'drywall', 'roofing', 'electrical', 'plumbing'
    subcategory VARCHAR(100),  -- 'tongue_and_groove', '2x4', 'shingles'
    
    -- Specifications
    description TEXT,
    specifications JSONB,  -- {dimensions, weight, R-value, grade, etc}
    
    -- Pricing
    unit VARCHAR(50),  -- 'sqft', 'linear_ft', 'piece', 'cubic_yard', 'board_foot'
    unit_cost DECIMAL(10, 2),
    bulk_discount_threshold INTEGER,  -- quantity for bulk discount
    bulk_unit_cost DECIMAL(10, 2),
    
    -- Supplier info
    supplier VARCHAR(255),
    supplier_sku VARCHAR(100),
    supplier_url TEXT,
    lead_time_days INTEGER,  -- how long to get this material
    
    -- Availability
    in_stock BOOLEAN DEFAULT true,
    discontinued BOOLEAN DEFAULT false,
    
    -- Sustainability
    eco_rating VARCHAR(20),  -- 'excellent', 'good', 'fair', 'poor'
    recycled_content_percentage DECIMAL(5, 2),
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Project materials (materials assigned to specific project with quantities)
CREATE TABLE project_materials (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    material_id INTEGER REFERENCES materials(id),
    
    -- Quantities
    quantity_needed FLOAT NOT NULL,
    quantity_ordered FLOAT DEFAULT 0,
    quantity_delivered FLOAT DEFAULT 0,
    quantity_used FLOAT DEFAULT 0,
    
    -- Waste factor
    waste_factor DECIMAL(5, 2) DEFAULT 10.00,  -- percentage (e.g., 10% extra)
    quantity_with_waste FLOAT GENERATED ALWAYS AS (quantity_needed * (1 + waste_factor/100)) STORED,
    
    -- Costs
    unit_cost_at_time DECIMAL(10, 2),  -- cost when added (price may change)
    total_cost DECIMAL(12, 2) GENERATED ALWAYS AS (quantity_with_waste * unit_cost_at_time) STORED,
    
    -- Assignment
    assigned_to_phase VARCHAR(100),  -- which construction phase needs this
    
    -- Status
    status VARCHAR(50) DEFAULT 'planned',  -- 'planned', 'ordered', 'delivered', 'in_use', 'depleted'
    
    -- Notes
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Element materials (link materials to specific design elements)
CREATE TABLE element_materials (
    id SERIAL PRIMARY KEY,
    design_element_id INTEGER REFERENCES design_elements(id) ON DELETE CASCADE,
    material_id INTEGER REFERENCES materials(id),
    project_material_id INTEGER REFERENCES project_materials(id),
    
    quantity FLOAT,
    notes TEXT
);

-- Labor resources (workers, contractors)
CREATE TABLE labor_resources (
    id SERIAL PRIMARY KEY,
    
    -- Resource info
    resource_type VARCHAR(50),  -- 'general_contractor', 'electrician', 'plumber', 'carpenter', 'laborer'
    name VARCHAR(255),
    company VARCHAR(255),
    
    -- Contact
    phone VARCHAR(20),
    email VARCHAR(255),
    
    -- Rates
    hourly_rate DECIMAL(10, 2),
    daily_rate DECIMAL(10, 2),
    
    -- Availability
    available BOOLEAN DEFAULT true,
    
    -- Skills
    skills JSONB,  -- ['framing', 'finish_carpentry', 'concrete']
    certifications JSONB,  -- ['licensed', 'insured', 'OSHA_certified']
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Equipment resources (tools, machinery)
CREATE TABLE equipment_resources (
    id SERIAL PRIMARY KEY,
    
    -- Equipment info
    equipment_type VARCHAR(100),  -- 'excavator', 'crane', 'scaffolding', 'concrete_mixer'
    name VARCHAR(255),
    
    -- Rental or owned
    ownership VARCHAR(50),  -- 'owned', 'rented', 'contractor_provides'
    
    -- Costs
    daily_rental_cost DECIMAL(10, 2),
    delivery_cost DECIMAL(10, 2),
    
    -- Availability
    available BOOLEAN DEFAULT true,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TIMELINE & SCHEDULING (Stored + Dynamically Generated)
-- ============================================================================

-- Construction phases (high-level phases of construction)
CREATE TABLE construction_phases (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Phase info
    phase_name VARCHAR(100) NOT NULL,  -- 'Site Prep', 'Foundation', 'Framing', 'Rough-In', 'Finish'
    phase_order INTEGER NOT NULL,
    description TEXT,
    
    -- Timeline
    planned_start_date DATE,
    planned_end_date DATE,
    actual_start_date DATE,
    actual_end_date DATE,
    
    -- Duration
    estimated_duration_days INTEGER,
    actual_duration_days INTEGER,
    
    -- Status
    status VARCHAR(50) DEFAULT 'not_started',  -- 'not_started', 'in_progress', 'completed', 'delayed'
    progress_percentage DECIMAL(5, 2) DEFAULT 0.00,
    
    -- Costs
    estimated_cost DECIMAL(12, 2),
    actual_cost DECIMAL(12, 2) DEFAULT 0.00,
    
    -- Dependencies
    depends_on_phase_ids JSONB,  -- array of phase IDs that must complete first
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Build tasks (detailed tasks within each phase)
CREATE TABLE build_tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES construction_phases(id) ON DELETE CASCADE,
    
    -- Task info
    task_name VARCHAR(255) NOT NULL,
    description TEXT,
    task_type VARCHAR(100),  -- 'inspection', 'construction', 'delivery', 'permit'
    
    -- Timeline
    planned_start_date DATE,
    planned_end_date DATE,
    actual_start_date DATE,
    actual_end_date DATE,
    
    -- Duration
    estimated_duration_days INTEGER,
    estimated_labor_hours DECIMAL(8, 2),
    actual_duration_days INTEGER,
    actual_labor_hours DECIMAL(8, 2),
    
    -- Ordering
    sort_order INTEGER,
    
    -- Dependencies
    depends_on_task_ids JSONB,  -- array of task IDs that must complete first
    blocking_tasks JSONB,  -- tasks that can't start until this completes
    
    -- Status
    status VARCHAR(50) DEFAULT 'not_started',  -- 'not_started', 'in_progress', 'completed', 'blocked', 'delayed'
    progress_percentage DECIMAL(5, 2) DEFAULT 0.00,
    
    -- Resources required
    required_labor_resources JSONB,  -- [{resource_id: 1, hours: 8}, ...]
    required_equipment JSONB,  -- [{equipment_id: 1, days: 2}, ...]
    
    -- Costs
    estimated_cost DECIMAL(12, 2),
    actual_cost DECIMAL(12, 2) DEFAULT 0.00,
    
    -- Critical path
    is_critical_path BOOLEAN DEFAULT false,
    float_days INTEGER DEFAULT 0,  -- scheduling flexibility
    
    -- Notes
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Task assignments (assign labor to tasks)
CREATE TABLE task_assignments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES build_tasks(id) ON DELETE CASCADE,
    labor_resource_id INTEGER REFERENCES labor_resources(id),
    
    hours_assigned DECIMAL(8, 2),
    hours_completed DECIMAL(8, 2) DEFAULT 0.00,
    cost DECIMAL(10, 2),
    
    assigned_date DATE,
    completed_date DATE
);

-- ============================================================================
-- AI GENERATED CONTENT
-- ============================================================================

-- AI-generated images
CREATE TABLE ai_images (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Image info
    image_type VARCHAR(50),  -- 'rendering', 'blueprint', 'perspective', 'voice_generated'
    view_type VARCHAR(50),  -- 'exterior', 'interior', 'aerial', 'detail'
    
    -- Generation
    prompt TEXT,
    enhanced_prompt TEXT,  -- prompt after AI enhancement
    image_path VARCHAR(500),
    
    -- AI model used
    ai_model VARCHAR(100),  -- 'stable-diffusion-2.1', 'dalle-3', etc.
    generation_params JSONB,  -- {steps, guidance_scale, etc}
    
    -- Metadata
    width INTEGER,
    height INTEGER,
    file_size_bytes INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- AI-generated construction plans (cached plans)
CREATE TABLE construction_plans (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Plan info
    plan_version INTEGER DEFAULT 1,
    plan_type VARCHAR(50),  -- 'full_plan', 'materials_list', 'timeline', 'cost_estimate'
    
    -- Content (structured JSON)
    content JSONB,  -- Complete plan data
    
    -- Generation
    ai_model VARCHAR(100),
    generation_params JSONB,
    prompt_used TEXT,
    
    -- Status
    is_current BOOLEAN DEFAULT true,  -- most recent plan
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- BUDGET & COSTS
-- ============================================================================

-- Budget tracking
CREATE TABLE project_budget (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Budget categories
    category VARCHAR(100),  -- 'materials', 'labor', 'equipment', 'permits', 'contingency'
    subcategory VARCHAR(100),
    
    -- Amounts
    budgeted_amount DECIMAL(12, 2),
    spent_amount DECIMAL(12, 2) DEFAULT 0.00,
    remaining_amount DECIMAL(12, 2) GENERATED ALWAYS AS (budgeted_amount - spent_amount) STORED,
    
    -- Percentage
    percentage_of_total DECIMAL(5, 2),
    percentage_spent DECIMAL(5, 2) GENERATED ALWAYS AS 
        (CASE WHEN budgeted_amount > 0 THEN (spent_amount / budgeted_amount * 100) ELSE 0 END) STORED,
    
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Expenses (actual costs incurred)
CREATE TABLE expenses (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Expense details
    expense_type VARCHAR(100),  -- 'material_purchase', 'labor_payment', 'equipment_rental', 'permit_fee'
    description TEXT,
    
    -- Related to
    project_material_id INTEGER REFERENCES project_materials(id),
    task_id INTEGER REFERENCES build_tasks(id),
    
    -- Amount
    amount DECIMAL(12, 2) NOT NULL,
    
    -- Payment
    payment_method VARCHAR(50),  -- 'cash', 'check', 'credit_card', 'ACH'
    payment_date DATE,
    
    -- Receipt
    receipt_path VARCHAR(500),
    
    -- Vendor
    vendor_name VARCHAR(255),
    
    expense_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- PERMITS & INSPECTIONS
-- ============================================================================

-- Permits required
CREATE TABLE permits (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Permit info
    permit_type VARCHAR(100),  -- 'building', 'electrical', 'plumbing', 'mechanical', 'demolition'
    permit_number VARCHAR(100),
    
    -- Dates
    application_date DATE,
    approval_date DATE,
    expiration_date DATE,
    
    -- Cost
    fee DECIMAL(10, 2),
    
    -- Status
    status VARCHAR(50),  -- 'pending', 'approved', 'rejected', 'expired'
    
    -- Documents
    document_path VARCHAR(500),
    
    notes TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inspections
CREATE TABLE inspections (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    phase_id INTEGER REFERENCES construction_phases(id),
    
    -- Inspection info
    inspection_type VARCHAR(100),  -- 'foundation', 'framing', 'electrical', 'plumbing', 'final'
    inspector_name VARCHAR(255),
    
    -- Dates
    scheduled_date DATE,
    actual_date DATE,
    
    -- Result
    result VARCHAR(50),  -- 'passed', 'failed', 'conditional_pass', 'pending'
    notes TEXT,
    corrections_needed TEXT,
    
    -- Follow-up
    reinspection_required BOOLEAN DEFAULT false,
    reinspection_date DATE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- DOCUMENTS & FILES
-- ============================================================================

-- Project documents
CREATE TABLE project_documents (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    
    -- Document info
    document_type VARCHAR(100),  -- 'blueprint', 'contract', 'invoice', 'receipt', 'photo', 'report'
    title VARCHAR(255),
    description TEXT,
    
    -- File
    file_path VARCHAR(500),
    file_name VARCHAR(255),
    file_size_bytes INTEGER,
    mime_type VARCHAR(100),
    
    -- Metadata
    uploaded_by VARCHAR(255),
    tags JSONB,  -- ['foundation', 'electrical', 'final']
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX idx_design_elements_project ON design_elements(project_id);
CREATE INDEX idx_design_elements_type ON design_elements(element_type);
CREATE INDEX idx_element_materials_element ON element_materials(design_element_id);
CREATE INDEX idx_element_materials_material ON element_materials(material_id);

CREATE INDEX idx_project_materials_project ON project_materials(project_id);
CREATE INDEX idx_project_materials_material ON project_materials(material_id);
CREATE INDEX idx_project_materials_status ON project_materials(status);

CREATE INDEX idx_construction_phases_project ON construction_phases(project_id);
CREATE INDEX idx_construction_phases_status ON construction_phases(status);
CREATE INDEX idx_construction_phases_order ON construction_phases(project_id, phase_order);

CREATE INDEX idx_build_tasks_project ON build_tasks(project_id);
CREATE INDEX idx_build_tasks_phase ON build_tasks(phase_id);
CREATE INDEX idx_build_tasks_status ON build_tasks(status);
CREATE INDEX idx_build_tasks_critical ON build_tasks(is_critical_path);

CREATE INDEX idx_ai_images_project ON ai_images(project_id);
CREATE INDEX idx_construction_plans_project ON construction_plans(project_id);
CREATE INDEX idx_construction_plans_current ON construction_plans(project_id, is_current);

CREATE INDEX idx_expenses_project ON expenses(project_id);
CREATE INDEX idx_expenses_date ON expenses(expense_date);
CREATE INDEX idx_permits_project ON permits(project_id);
CREATE INDEX idx_inspections_project ON inspections(project_id);

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- Project summary view
CREATE VIEW project_summary AS
SELECT 
    p.id,
    p.name,
    p.status,
    p.progress_percentage,
    p.target_budget,
    COALESCE(SUM(e.amount), 0) as total_spent,
    (p.target_budget - COALESCE(SUM(e.amount), 0)) as budget_remaining,
    COUNT(DISTINCT pm.id) as material_count,
    COUNT(DISTINCT bt.id) as task_count,
    COUNT(DISTINCT CASE WHEN bt.status = 'completed' THEN bt.id END) as completed_tasks
FROM projects p
LEFT JOIN expenses e ON p.id = e.project_id
LEFT JOIN project_materials pm ON p.id = pm.project_id
LEFT JOIN build_tasks bt ON p.id = bt.project_id
GROUP BY p.id;

-- Materials needed view
CREATE VIEW materials_needed_view AS
SELECT 
    pm.project_id,
    m.name as material_name,
    m.category,
    pm.quantity_with_waste,
    m.unit,
    pm.total_cost,
    pm.status,
    pm.assigned_to_phase
FROM project_materials pm
JOIN materials m ON pm.material_id = m.id
WHERE pm.status != 'depleted'
ORDER BY pm.assigned_to_phase, m.category;

-- Timeline view
CREATE VIEW timeline_view AS
SELECT 
    bt.project_id,
    cp.phase_name,
    cp.phase_order,
    bt.task_name,
    bt.sort_order,
    bt.planned_start_date,
    bt.planned_end_date,
    bt.estimated_duration_days,
    bt.status,
    bt.is_critical_path,
    bt.depends_on_task_ids
FROM build_tasks bt
JOIN construction_phases cp ON bt.phase_id = cp.id
ORDER BY cp.phase_order, bt.sort_order;

EOF
```

**Verify schema creation:**
```bash
# List all tables
docker compose exec postgres psql -U vr_admin -d vr_construction -c "\dt"

# Describe a table
docker compose exec postgres psql -U vr_admin -d vr_construction -c "\d projects"

# Check views
docker compose exec postgres psql -U vr_admin -d vr_construction -c "\dv"
```

---

## **Database Design Decisions Explained**

### **Q: Should Timeline be Stored or Generated Dynamically?**

**Answer: HYBRID APPROACH** ✅

**What to Store:**
- ✅ Base timeline structure (phases, tasks, dependencies)
- ✅ Planned dates and durations
- ✅ Actual progress and completion dates
- ✅ Resource assignments
- ✅ Historical versions

**What to Generate Dynamically:**
- 🔄 Optimized schedule based on current state
- 🔄 Critical path analysis
- 🔄 Updated material delivery dates
- 🔄 Cost projections
- 🔄 "What-if" scenarios

**Implementation Strategy:**

```python
# app/services/timeline_service.py

class TimelineService:
    
    async def get_project_timeline(self, project_id: int, regenerate: bool = False):
        """
        Get timeline - use cached or regenerate
        """
        if not regenerate:
            # Try to get cached timeline
            cached = await self.get_cached_timeline(project_id)
            if cached and self.is_timeline_fresh(cached):
                return cached
        
        # Generate new timeline
        timeline = await self.generate_timeline(project_id)
        
        # Cache it
        await self.cache_timeline(project_id, timeline)
        
        return timeline
    
    async def generate_timeline(self, project_id: int):
        """
        Dynamically generate optimized timeline using AI
        """
        # Get project data
        project = get_project(project_id)
        materials = get_project_materials(project_id)
        tasks = get_build_tasks(project_id)
        
        # Use AI to optimize schedule
        prompt = f"""
        Create an optimized construction timeline for this project:
        
        Project: {project.name}
        Materials: {len(materials)} items
        Tasks: {len(tasks)} tasks
        
        Consider:
        - Task dependencies
        - Material delivery lead times
        - Weather constraints
        - Labor availability
        - Critical path optimization
        
        Return optimized schedule with dates.
        """
        
        timeline = await llm_service.generate_timeline(prompt, tasks)
        
        # Update database with new dates
        await self.update_task_dates(tasks, timeline)
        
        return timeline
    
    def is_timeline_fresh(self, cached_timeline):
        """
        Check if cached timeline is still valid
        Timeline is stale if:
        - Design changed
        - Materials changed
        - More than 24 hours old
        """
        if cached_timeline.created_at < datetime.now() - timedelta(days=1):
            return False
        
        if project_modified_since(cached_timeline.created_at):
            return False
        
        return True
```

---

## **Key Database Tables Explained**

### **1. Projects Table**
**Purpose:** Core project information  
**When to Create:** User starts new project in VR  
**What to Store:**
- Basic info (name, description, type)
- Dimensions and specifications
- Budget and timeline targets
- Status and progress

**Example:**
```sql
INSERT INTO projects (name, project_type, target_budget, total_square_footage)
VALUES ('Cedar Dog House', 'dog_house', 500.00, 16.0);
```

### **2. Construction Phases**
**Purpose:** High-level phases of construction  
**Stored vs Generated:**
- ✅ **Stored:** Phase structure, dependencies, planned dates
- 🔄 **Generated:** Optimized dates based on current progress

**Standard Phases:**
1. Site Preparation
2. Foundation
3. Framing
4. Rough-In (electrical, plumbing)
5. Insulation
6. Drywall
7. Finish Work
8. Final Inspection

**Example:**
```sql
INSERT INTO construction_phases (project_id, phase_name, phase_order, estimated_duration_days)
VALUES 
    (1, 'Foundation', 1, 3),
    (1, 'Framing', 2, 5),
    (1, 'Roofing', 3, 2),
    (1, 'Siding', 4, 3),
    (1, 'Finish', 5, 2);
```

### **3. Build Tasks**
**Purpose:** Detailed tasks within each phase  
**Stored vs Generated:**
- ✅ **Stored:** Task definitions, dependencies, durations, assignments
- 🔄 **Generated:** Optimized start/end dates, resource allocation

**Example:**
```sql
INSERT INTO build_tasks (project_id, phase_id, task_name, estimated_duration_days, depends_on_task_ids)
VALUES 
    (1, 1, 'Dig foundation holes', 1, '[]'),
    (1, 1, 'Pour concrete footings', 1, '[1]'),
    (1, 1, 'Install foundation posts', 1, '[2]'),
    (1, 2, 'Install floor joists', 1, '[3]'),
    (1, 2, 'Install wall frames', 2, '[4]');
```

### **4. Project Materials**
**Purpose:** Track all materials needed and their status  
**Auto-calculated Fields:**
- `quantity_with_waste` = automatically adds waste factor
- `total_cost` = automatically calculated from quantity × cost

**Example:**
```sql
INSERT INTO project_materials (project_id, material_id, quantity_needed, waste_factor, unit_cost_at_time)
VALUES 
    (1, 15, 100, 10.0, 3.50),  -- Cedar tongue and groove: 100 sq ft + 10% waste
    (1, 23, 50, 5.0, 2.25);    -- 2x4 lumber: 50 linear ft + 5% waste
```

### **5. Materials Catalog**
**Purpose:** Master list of all available materials  
**Pre-populated:** Yes - seed with common construction materials  
**User-expandable:** Yes - can add custom materials

**Seed Data Example:**
```sql
-- Pre-populate common materials
INSERT INTO materials (name, category, subcategory, unit, unit_cost, supplier)
VALUES 
    ('Cedar Tongue and Groove Siding', 'lumber', 'siding', 'sqft', 3.50, 'Home Depot'),
    ('2x4 Pressure Treated Lumber', 'lumber', 'framing', 'linear_ft', 2.25, 'Lowes'),
    ('Concrete Mix 80lb', 'concrete', 'foundation', 'bag', 4.50, 'Home Depot'),
    ('Asphalt Shingles', 'roofing', 'shingles', 'bundle', 28.00, 'Lowes');
```

---

## **API Endpoints for Database Access**

```python
# app/api/v1/projects.py

@router.get("/projects/{project_id}/summary")
async def get_project_summary(project_id: int):
    """Get complete project overview"""
    return {
        "project": get_project(project_id),
        "progress": calculate_progress(project_id),
        "budget": get_budget_summary(project_id),
        "timeline": get_timeline_summary(project_id),
        "materials_status": get_materials_status(project_id)
    }

@router.get("/projects/{project_id}/timeline")
async def get_project_timeline(project_id: int, regenerate: bool = False):
    """
    Get project timeline
    Query params:
        regenerate=true - force AI to regenerate timeline
        regenerate=false - use cached timeline (default)
    """
    timeline = await timeline_service.get_project_timeline(project_id, regenerate)
    return timeline

@router.get("/projects/{project_id}/materials")
async def get_project_materials(project_id: int, status: str = None):
    """
    Get materials list
    Query params:
        status=planned - only planned materials
        status=ordered - only ordered materials
        status=delivered - only delivered materials
    """
    query = db.query(ProjectMaterial).filter(ProjectMaterial.project_id == project_id)
    
    if status:
        query = query.filter(ProjectMaterial.status == status)
    
    materials = query.all()
    
    return {
        "materials": materials,
        "total_cost": sum(m.total_cost for m in materials),
        "summary_by_category": group_by_category(materials)
    }

@router.get("/projects/{project_id}/resources")
async def get_required_resources(project_id: int):
    """Get all resources needed for project"""
    return {
        "labor": get_labor_requirements(project_id),
        "equipment": get_equipment_requirements(project_id),
        "total_labor_hours": calculate_total_labor_hours(project_id),
        "total_labor_cost": calculate_total_labor_cost(project_id)
    }

@router.post("/projects/{project_id}/timeline/regenerate")
async def regenerate_timeline(project_id: int):
    """Force regeneration of timeline using AI"""
    new_timeline = await timeline_service.generate_timeline(project_id)
    return {
        "message": "Timeline regenerated",
        "timeline": new_timeline,
        "changes": compare_with_previous(project_id, new_timeline)
    }
```

---

## **Example Database Queries**

### **Get Complete Project Overview:**
```sql
SELECT 
    p.*,
    COUNT(DISTINCT de.id) as design_element_count,
    COUNT(DISTINCT pm.id) as material_count,
    COUNT(DISTINCT bt.id) as total_tasks,
    COUNT(DISTINCT CASE WHEN bt.status = 'completed' THEN bt.id END) as completed_tasks,
    COALESCE(SUM(pm.total_cost), 0) as total_material_cost,
    COALESCE(SUM(e.amount), 0) as total_spent
FROM projects p
LEFT JOIN design_elements de ON p.id = de.project_id
LEFT JOIN project_materials pm ON p.id = pm.project_id
LEFT JOIN build_tasks bt ON p.id = bt.project_id
LEFT JOIN expenses e ON p.id = e.project_id
WHERE p.id = 1
GROUP BY p.id;
```

### **Get Materials Needed for Next Phase:**
```sql
SELECT 
    m.name,
    m.category,
    pm.quantity_with_waste,
    m.unit,
    pm.total_cost,
    pm.status,
    m.supplier,
    m.lead_time_days
FROM project_materials pm
JOIN materials m ON pm.material_id = m.id
JOIN construction_phases cp ON pm.assigned_to_phase = cp.phase_name
WHERE pm.project_id = 1
  AND cp.status = 'not_started'
  AND pm.status IN ('planned', 'ordered')
ORDER BY cp.phase_order, m.category;
```

### **Get Critical Path Tasks:**
```sql
SELECT 
    bt.task_name,
    bt.planned_start_date,
    bt.planned_end_date,
    bt.estimated_duration_days,
    bt.status,
    cp.phase_name
FROM build_tasks bt
JOIN construction_phases cp ON bt.phase_id = cp.id
WHERE bt.project_id = 1
  AND bt.is_critical_path = true
ORDER BY bt.planned_start_date;
```

### **Get Budget vs Actual:**
```sql
SELECT 
    pb.category,
    pb.budgeted_amount,
    pb.spent_amount,
    pb.remaining_amount,
    pb.percentage_spent,
    CASE 
        WHEN pb.percentage_spent > 90 THEN 'OVER_BUDGET'
        WHEN pb.percentage_spent > 75 THEN 'WARNING'
        ELSE 'ON_TRACK'
    END as budget_status
FROM project_budget pb
WHERE pb.project_id = 1
ORDER BY pb.percentage_spent DESC;
```

---

## **What Else Should Be in the Database?**

Based on comprehensive project management needs, the database now includes:

### ✅ **Already Included:**
1. **Core Project Data** - Projects, design elements
2. **Materials Management** - Catalog, assignments, quantities, costs
3. **Timeline & Scheduling** - Phases, tasks, dependencies, critical path
4. **Resources** - Labor, equipment
5. **Budget & Costs** - Budget tracking, expenses, cost analysis
6. **AI Generated Content** - Images, plans
7. **Permits & Inspections** - Regulatory compliance
8. **Documents** - Files, photos, receipts

### 🎯 **Additional Considerations:**

**Weather Integration (Future):**
```sql
CREATE TABLE weather_constraints (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES build_tasks(id),
    weather_requirement VARCHAR(100),  -- 'no_rain', 'temp_above_32', 'wind_below_25mph'
    cannot_work_if TEXT
);
```

**Change Orders:**
```sql
CREATE TABLE change_orders (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    description TEXT,
    cost_impact DECIMAL(12, 2),
    time_impact_days INTEGER,
    approved BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Project Photos (Progress Documentation):**
```sql
CREATE TABLE project_photos (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id),
    phase_id INTEGER REFERENCES construction_phases(id),
    task_id INTEGER REFERENCES build_tasks(id),
    photo_path VARCHAR(500),
    caption TEXT,
    taken_at TIMESTAMP,
    location_on_site VARCHAR(255)
);
```

---

## **Best Practices**

### **1. When to Regenerate Timeline:**
- ✅ Design changes significantly
- ✅ Materials delayed
- ✅ Tasks taking longer than expected
- ✅ User requests optimization
- ❌ Every small change (use cached)

### **2. Caching Strategy:**
```python
# Cache timeline for 24 hours or until project changes
CACHE_DURATION = timedelta(hours=24)

def should_regenerate_timeline(project_id):
    last_generated = get_last_timeline_generation(project_id)
    last_modified = get_last_project_modification(project_id)
    
    if last_generated < last_modified:
        return True  # Project changed, regenerate
    
    if datetime.now() - last_generated > CACHE_DURATION:
        return True  # Cache expired
    
    return False
```

### **3. Data Integrity:**
- Use foreign keys with CASCADE delete
- Use GENERATED columns for calculations
- Use views for complex queries
- Use indexes on frequently queried fields

### **4. Version Control:**
```python
# Keep history of timeline changes
@router.post("/projects/{project_id}/timeline/save-version")
async def save_timeline_version(project_id: int):
    """Save current timeline as historical version"""
    current_timeline = get_current_timeline(project_id)
    
    # Archive it
    archive_timeline(project_id, current_timeline)
    
    # Generate new one
    new_timeline = await generate_timeline(project_id)
    
    return {
        "previous_version": current_timeline,
        "new_version": new_timeline,
        "changes": diff_timelines(current_timeline, new_timeline)
    }
```

This database design gives you everything needed to manage complete construction projects with AI-powered optimization! 🏗️📊

**Verify schema creation:**
```bash
# List all tables
docker compose exec postgres psql -U vr_admin -d vr_construction -c "\dt"

# Describe a table
docker compose exec postgres psql -U vr_admin -d vr_construction -c "\d projects"
```

**Core API Endpoints:**

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1 import projects, designs, materials, ai_image, ai_planning

app = FastAPI(title="VR Construction API", version="1.0.0")

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Quest 2 local IP
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(designs.router, prefix="/api/v1/designs", tags=["designs"])
app.include_router(materials.router, prefix="/api/v1/materials", tags=["materials"])
app.include_router(ai_image.router, prefix="/api/v1/ai/images", tags=["ai-images"])
app.include_router(ai_planning.router, prefix="/api/v1/ai/planning", tags=["ai-planning"])

@app.get("/")
def root():
    return {"message": "VR Construction API", "status": "running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
```

**Start/Restart Backend:**
```bash
# Rebuild after code changes
docker compose up -d --build backend

# View logs
docker compose logs -f backend

# Restart all services
docker compose restart

# Stop all services
docker compose down

# Stop and remove volumes (WARNING: deletes database data)
docker compose down -v
```

**Key Endpoints:**

```
POST   /api/v1/projects                    # Create new project
GET    /api/v1/projects/{id}               # Get project details
PUT    /api/v1/projects/{id}               # Update project
DELETE /api/v1/projects/{id}               # Delete project

POST   /api/v1/designs/elements            # Add design element
PUT    /api/v1/designs/elements/{id}       # Update design element
DELETE /api/v1/designs/elements/{id}       # Delete design element
GET    /api/v1/designs/project/{id}        # Get all elements for project

GET    /api/v1/materials                   # List available materials
GET    /api/v1/materials/{id}              # Get material details
POST   /api/v1/materials/assign            # Assign material to element

POST   /api/v1/ai/images/generate          # Generate image from design
GET    /api/v1/ai/images/project/{id}      # Get all images for project

POST   /api/v1/ai/planning/generate        # Generate construction plan
GET    /api/v1/ai/planning/project/{id}    # Get plan for project
```

**Deliverables:**
- ✓ Backend project structure created
- ✓ Database schema implemented in Docker
- ✓ Core API endpoints functional
- ✓ Basic CRUD operations working
- ✓ API documentation (Swagger UI at http://localhost:8000/docs)
- ✓ Docker containers running smoothly
- ✓ Hot reload working for development

---

### Phase 3: AI Integration (Weeks 6-8)

**AI Service Architecture:**

**1. Speech-to-Text Service (New!)**

Speech-to-text allows users to give voice commands in VR instead of using controllers for every action.

**Voice Command Examples:**
- "Add a wall here"
- "Create a window"
- "Generate exterior rendering"
- "Show me the material list"
- "Make this room bigger"
- "Delete that door"
- "Save my design"

**Implementation using Whisper:**

```python
# app/services/speech_service.py
import whisper
import torch
from faster_whisper import WhisperModel
import tempfile
import os
from pathlib import Path

class SpeechToTextService:
    def __init__(self, model_size="base", use_faster=True):
        """
        Initialize Whisper model
        model_size: tiny, base, small, medium, large
        use_faster: Use faster-whisper (optimized) if True
        """
        self.use_faster = use_faster
        
        if use_faster:
            # Faster-whisper (recommended for production)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type
            )
        else:
            # Standard Whisper
            self.model = whisper.load_model(model_size)
    
    async def transcribe_audio(self, audio_file_path: str) -> dict:
        """
        Transcribe audio file to text
        Returns: {
            "text": "transcribed text",
            "language": "en",
            "confidence": 0.95
        }
        """
        try:
            if self.use_faster:
                segments, info = self.model.transcribe(
                    audio_file_path,
                    language="en",
                    beam_size=5
                )
                
                # Combine all segments
                text = " ".join([segment.text for segment in segments])
                
                return {
                    "text": text.strip(),
                    "language": info.language,
                    "confidence": info.language_probability
                }
            else:
                result = self.model.transcribe(audio_file_path)
                return {
                    "text": result["text"].strip(),
                    "language": result["language"],
                    "confidence": 1.0  # Whisper doesn't provide confidence
                }
                
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")
    
    async def transcribe_audio_bytes(self, audio_data: bytes) -> dict:
        """
        Transcribe audio bytes and return just the text
        Quest 2 will display this text for user confirmation
        """
        # Save audio to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_data)
            temp_path = temp_audio.name
        
        try:
            # Transcribe
            result = await self.transcribe_audio(temp_path)
            return result
        finally:
            # Clean up temp file
            os.unlink(temp_path)


# Initialize global instance
speech_service = SpeechToTextService(model_size="base", use_faster=True)
```

**API Endpoints for Voice:**

```python
# app/api/v1/voice.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from app.services.speech_service import speech_service
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """
    Transcribe audio file to text and return it to Quest 2
    Quest will display the text for user to see/edit before sending as prompt
    Accepts: WAV, MP3, OGG, M4A
    """
    try:
        # Read audio data
        audio_data = await audio.read()
        
        # Process transcription
        result = await speech_service.transcribe_audio_bytes(audio_data)
        
        return JSONResponse(content={
            "success": True,
            "text": result["text"],
            "language": result["language"],
            "confidence": result["confidence"]
        })
        
    except Exception as e:
        logger.error(f"Transcription error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/prompt")
async def process_ai_prompt(request: dict):
    """
    Process text prompt from Quest 2 for AI operations
    Text can be used for:
    - Image generation prompts
    - Design descriptions
    - Material searches
    - Question answering
    """
    try:
        prompt_text = request.get("text", "")
        prompt_type = request.get("type", "general")  # 'image', 'design', 'question'
        context = request.get("context", {})  # Additional context like project_id
        
        logger.info(f"Processing AI prompt: '{prompt_text}' (type: {prompt_type})")
        
        if prompt_type == "image":
            # Use text as image generation prompt
            return await generate_image_from_prompt(prompt_text, context)
        
        elif prompt_type == "design":
            # Use text to modify design
            return await process_design_prompt(prompt_text, context)
        
        elif prompt_type == "question":
            # Answer user questions about project
            return await answer_question(prompt_text, context)
        
        elif prompt_type == "materials":
            # Search or suggest materials
            return await process_material_prompt(prompt_text, context)
        
        else:
            # General purpose - let LLM decide what to do
            return await process_general_prompt(prompt_text, context)
        
    except Exception as e:
        logger.error(f"Prompt processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def generate_image_from_prompt(prompt: str, context: dict):
    """Generate image using user's text prompt"""
    from app.services.ai_image_service import ai_image_service
    
    project_id = context.get("project_id")
    
    # Enhance prompt with architectural context
    enhanced_prompt = f"architectural rendering: {prompt}, photorealistic, professional"
    
    # Generate image
    image_path = await ai_image_service.generate_from_text_prompt(
        prompt=enhanced_prompt,
        project_id=project_id
    )
    
    return {
        "success": True,
        "type": "image_generated",
        "image_url": f"/images/{image_path}",
        "message": f"Generated image from: {prompt}"
    }


async def process_design_prompt(prompt: str, context: dict):
    """Modify design based on text prompt"""
    import ollama
    
    # Use LLM to parse design intent
    response = ollama.generate(
        model='llama3.1:8b-instruct-q4_K_M',
        prompt=f"""Parse this design instruction into actions:
        "{prompt}"
        
        Return JSON with suggested design modifications.
        Examples:
        - "make the room 20 feet wide" -> {{"action": "resize_room", "dimension": "width", "value": 20, "unit": "feet"}}
        - "add three windows on the south wall" -> {{"action": "add_elements", "type": "window", "count": 3, "location": "south_wall"}}
        """,
        format='json'
    )
    
    import json
    design_action = json.loads(response['response'])
    
    return {
        "success": True,
        "type": "design_modification",
        "action": design_action,
        "message": f"Interpreted: {prompt}"
    }


async def answer_question(prompt: str, context: dict):
    """Answer questions about the project"""
    import ollama
    
    project_id = context.get("project_id")
    # Get project data
    project_info = get_project_info(project_id)
    
    response = ollama.generate(
        model='llama3.1:8b-instruct-q4_K_M',
        prompt=f"""You are a construction expert assistant.
        
        Project context:
        {json.dumps(project_info, indent=2)}
        
        User question: "{prompt}"
        
        Provide a helpful, concise answer."""
    )
    
    return {
        "success": True,
        "type": "answer",
        "answer": response['response'],
        "question": prompt
    }


async def process_material_prompt(prompt: str, context: dict):
    """Search or suggest materials based on text"""
    # Search materials database or suggest based on prompt
    # "I need drywall" -> search for drywall materials
    # "what should I use for exterior walls" -> suggest materials
    
    return {
        "success": True,
        "type": "materials",
        "suggestions": [...],  # Material suggestions
        "message": f"Found materials matching: {prompt}"
    }


async def process_general_prompt(prompt: str, context: dict):
    """General purpose prompt processing"""
    import ollama
    
    response = ollama.generate(
        model='llama3.1:8b-instruct-q4_K_M',
        prompt=f"""You are assisting with a VR construction design project.
        
        User request: "{prompt}"
        
        Determine what the user wants to do and provide guidance or execute the action.
        Be helpful and concise."""
    )
    
    return {
        "success": True,
        "type": "general",
        "response": response['response'],
        "prompt": prompt
    }


@router.get("/test")
async def test_voice_service():
    """Test if voice service is available"""
    return {"status": "available", "model": "whisper-base"}
```

**Add to main.py:**

```python
# app/main.py
from app.api.v1 import voice
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Add voice router
app.include_router(voice.router, prefix="/api/v1/voice", tags=["voice"])

# Serve generated images
app.mount("/images", StaticFiles(directory="generated_images"), name="images")

# Alternative: Serve images with custom endpoint for more control
@app.get("/images/{filename}")
async def get_image(filename: str):
    """Serve generated images to Quest 2"""
    image_path = f"generated_images/{filename}"
    
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image not found")
    
    return FileResponse(
        image_path,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*"
        }
    )
```

**2. Image Generation Service**
```python
# app/services/ai_image_service.py
from diffusers import StableDiffusionPipeline
import torch
import ollama
import time
import os

class AIImageService:
    def __init__(self):
        # Load Stable Diffusion model (one-time at startup)
        self.sd_pipe = None
        self.sd_loaded = False
        
    def load_stable_diffusion(self):
        """Lazy load Stable Diffusion model"""
        if not self.sd_loaded:
            self.sd_pipe = StableDiffusionPipeline.from_pretrained(
                "stabilityai/stable-diffusion-2-1",
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
            )
            if torch.cuda.is_available():
                self.sd_pipe = self.sd_pipe.to("cuda")
            self.sd_loaded = True
    
    async def generate_from_text_prompt(self, prompt: str, project_id: int = None):
        """
        Generate image directly from text prompt
        This is used for voice-to-image generation
        """
        # Load model if needed
        if not self.sd_loaded:
            self.load_stable_diffusion()
        
        # Generate image
        image = self.sd_pipe(
            prompt,
            num_inference_steps=50,  # Higher quality for final renders
            guidance_scale=7.5,
            height=768,
            width=768,
            negative_prompt="blurry, low quality, distorted, unrealistic"
        ).images[0]
        
        # Save image
        timestamp = int(time.time())
        filename = f"ai_gen_{timestamp}.png"
        
        # Ensure directory exists
        os.makedirs("generated_images", exist_ok=True)
        
        image_path = f"generated_images/{filename}"
        image.save(image_path)
        
        # Optionally save to database
        if project_id:
            # Save to ai_images table
            from app.database import get_db
            db = next(get_db())
            from app.models.ai_generation import AIImage
            
            ai_image = AIImage(
                project_id=project_id,
                image_type='voice_generated',
                prompt=prompt,
                image_path=filename,
                ai_model='stable-diffusion-2.1'
            )
            db.add(ai_image)
            db.commit()
        
        return filename
    
    async def generate_rendering(self, design_data: dict, view_type: str):
        """
        Generate photorealistic rendering from design data
        view_type: 'exterior', 'interior', 'aerial', 'blueprint'
        """
        # Convert design data to descriptive prompt
        prompt = self._create_prompt_from_design(design_data, view_type)
        
        # Generate image
        return await self.generate_from_text_prompt(prompt, design_data.get('project_id'))
    
    def _create_prompt_from_design(self, design_data: dict, view_type: str):
        """Convert design structure to text prompt for image generation"""
        # Use Ollama to create detailed prompt
        design_description = f"""
        Project type: {design_data['project_type']}
        Number of rooms: {len([e for e in design_data['elements'] if e['type'] == 'room'])}
        Floors: {design_data.get('floors', 1)}
        Style: {design_data.get('style', 'modern')}
        Elements: {', '.join([e['type'] for e in design_data['elements']])}
        """
        
        response = ollama.generate(
            model='llama3.1:8b-instruct-q4_K_M',
            prompt=f"""Create a detailed image generation prompt for a {view_type} view of this building:
            {design_description}
            
            Make it photorealistic, architectural, professional quality."""
        )
        
        return response['response']


# Initialize global instance
ai_image_service = AIImageService()
```

**2. Construction Planning Service**
```python
# app/services/ai_planning_service.py
import ollama
import json

class AIPlanningService:
    
    async def generate_construction_plan(self, project_data: dict):
        """Generate comprehensive construction plan using LLM"""
        
        # Prepare design summary
        design_summary = self._summarize_design(project_data)
        
        # Generate plan using Ollama
        plan_prompt = f"""
You are a construction planning expert. Based on this building design, create a detailed construction plan.

Design Summary:
{design_summary}

Provide a JSON response with:
1. phases: Array of construction phases (foundation, framing, roofing, etc.)
2. materials_list: Detailed list with quantities and costs
3. timeline: Estimated timeline with dependencies
4. cost_estimate: Total and breakdown
5. considerations: Important notes and recommendations

Format as valid JSON only, no markdown.
"""
        
        response = ollama.generate(
            model='llama3.1:8b-instruct-q4_K_M',
            prompt=plan_prompt,
            format='json'
        )
        
        plan_data = json.loads(response['response'])
        
        return plan_data
    
    def _summarize_design(self, project_data: dict):
        """Create human-readable design summary"""
        summary = {
            'project_name': project_data['name'],
            'type': project_data['project_type'],
            'total_elements': len(project_data['design_elements']),
            'dimensions': self._calculate_dimensions(project_data['design_elements']),
            'materials_used': self._list_materials(project_data['design_elements'])
        }
        return json.dumps(summary, indent=2)
    
    async def calculate_material_quantities(self, design_elements: list):
        """Calculate exact material quantities needed"""
        material_calc = {}
        
        for element in design_elements:
            element_type = element['element_type']
            dimensions = element['properties'].get('dimensions', {})
            
            if element_type == 'wall':
                # Calculate wall materials
                area = dimensions.get('height', 8) * dimensions.get('length', 10)
                material_calc['drywall_sqft'] = material_calc.get('drywall_sqft', 0) + area * 2
                material_calc['studs'] = material_calc.get('studs', 0) + int(dimensions.get('length', 10) / 1.33)
            
            elif element_type == 'floor':
                area = dimensions.get('length', 10) * dimensions.get('width', 10)
                material_calc['flooring_sqft'] = material_calc.get('flooring_sqft', 0) + area
        
        return material_calc
```

**3. AI Model Management**
```python
# app/services/ai_manager.py
import threading
import torch

class AIModelManager:
    """Manages loading/unloading AI models to optimize memory"""
    
    def __init__(self):
        self.sd_loaded = False
        self.llm_loaded = False
        self.lock = threading.Lock()
        self._sd_pipe = None
    
    def load_stable_diffusion(self):
        """Load SD only when needed"""
        with self.lock:
            if not self.sd_loaded:
                from diffusers import StableDiffusionPipeline
                self._sd_pipe = StableDiffusionPipeline.from_pretrained(
                    "stabilityai/stable-diffusion-2-1"
                )
                if torch.cuda.is_available():
                    self._sd_pipe = self._sd_pipe.to("cuda")
                self.sd_loaded = True
    
    def unload_stable_diffusion(self):
        """Free up memory"""
        with self.lock:
            if self.sd_loaded:
                del self._sd_pipe
                torch.cuda.empty_cache() if torch.cuda.is_available() else None
                self.sd_loaded = False
    
    def get_sd_pipeline(self):
        if not self.sd_loaded:
            self.load_stable_diffusion()
        return self._sd_pipe
```

**Testing AI Integration:**

```bash
# Test Ollama
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.1:8b-instruct-q4_K_M",
  "prompt": "Create a construction timeline for a 2000 sqft house",
  "stream": false
}'

# Test image generation endpoint
curl -X POST http://localhost:8000/api/v1/ai/images/generate \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "view_type": "exterior",
    "design_data": {...}
  }'
```

**Deliverables:**
- ✓ Stable Diffusion integrated and tested
- ✓ Ollama LLM integrated for planning
- ✓ **Whisper speech-to-text integrated**
- ✓ **Voice command parsing with LLM**
- ✓ Prompt engineering for design → images
- ✓ Construction plan generation working
- ✓ Material calculation logic implemented
- ✓ Memory management for models
- ✓ **Natural language command processing**

**Running AI Services (Host Machine):**

All AI models run on the host machine for GPU access. The Docker backend connects to them via `host.docker.internal`.

```bash
# Start Ollama (if not auto-started)
systemctl --user start ollama

# Verify Ollama is running
curl http://localhost:11434/api/version

# Test Whisper from Python (on host)
source ~/ai-venv/bin/activate
python3 << EOF
import whisper
model = whisper.load_model("base")
result = model.transcribe("test_audio.wav")
print(result["text"])
EOF

# Monitor GPU usage while AI is running
watch -n 1 rocm-smi

# Backend (in Docker) will access these services via:
# - Ollama: http://host.docker.internal:11434
# - Whisper: Runs in backend process (imports model)
# - Stable Diffusion: Runs in backend process (imports model)
```

**Note on Whisper in Docker:**

Since Whisper needs GPU access, you have two options:

**Option 1: Run Whisper on Host (Recommended for prototype)**
- Keep speech service code on host
- Backend makes HTTP call to host service
- Simpler setup, no GPU passthrough needed

**Option 2: Run Whisper in Docker with GPU**
- Requires Docker GPU support (nvidia-docker or ROCm)
- More complex setup
- Better for production deployment

For the prototype, Option 1 is simpler. If you want Option 2:

```yaml
# docker-compose.yml - Add GPU support
services:
  backend:
    # ... existing config
    deploy:
      resources:
        reservations:
          devices:
            - driver: rocm
              count: 1
              capabilities: [gpu]
```

---

### Phase 4: Quest 2 Frontend Development (Weeks 9-14)

### Phase 4: Quest 2 Frontend Development (Weeks 9-14)

**New Feature: Auto-Generate VR House from Database** 🏠

The system can automatically convert database project data into a fully navigable 3D VR house in Quest 2.

**Workflow:**
```
User says: "Show me what this house looks like in VR"
        ↓
Backend fetches all design_elements from database
        ↓
Backend converts to 3D geometry data (JSON)
        ↓
Quest 2 receives geometry
        ↓
Quest 2 generates 3D meshes procedurally
        ↓
User can walk through complete VR house!
```

---

**Backend: 3D Generation Service**

```python
# app/services/vr_generation_service.py

from typing import List, Dict
import math

class VRGenerationService:
    """
    Convert database design elements into 3D geometry for Quest 2
    """
    
    async def generate_vr_house(self, project_id: int) -> dict:
        """
        Generate complete 3D house from database
        Returns JSON with all geometry data
        """
        # Get all design elements
        elements = db.query(DesignElement).filter(
            DesignElement.project_id == project_id
        ).all()
        
        # Convert to 3D geometry
        geometry = {
            "project_id": project_id,
            "rooms": [],
            "walls": [],
            "doors": [],
            "windows": [],
            "roof": None,
            "foundation": None,
            "materials": {},
            "metadata": {}
        }
        
        for element in elements:
            if element.element_type == 'room':
                geometry["rooms"].append(self._generate_room_geometry(element))
            elif element.element_type == 'wall':
                geometry["walls"].append(self._generate_wall_geometry(element))
            elif element.element_type == 'door':
                geometry["doors"].append(self._generate_door_geometry(element))
            elif element.element_type == 'window':
                geometry["windows"].append(self._generate_window_geometry(element))
            elif element.element_type == 'roof':
                geometry["roof"] = self._generate_roof_geometry(element)
            elif element.element_type == 'foundation':
                geometry["foundation"] = self._generate_foundation_geometry(element)
        
        # Auto-generate walls from rooms if not explicit
        if not geometry["walls"] and geometry["rooms"]:
            geometry["walls"] = self._generate_walls_from_rooms(geometry["rooms"])
        
        # Get material textures
        geometry["materials"] = await self._get_material_textures(project_id)
        
        return geometry
    
    def _generate_room_geometry(self, element: DesignElement) -> dict:
        """
        Convert room database record to 3D geometry
        """
        return {
            "id": element.id,
            "name": element.element_name,
            "type": "room",
            
            # Position (center of room)
            "position": {
                "x": element.position_x,
                "y": element.position_y,
                "z": element.position_z
            },
            
            # Dimensions
            "dimensions": {
                "length": element.length,  # X axis
                "width": element.width,    # Y axis
                "height": element.height   # Z axis (ceiling height)
            },
            
            # Bounds (for collision detection)
            "bounds": {
                "min": {
                    "x": element.position_x - element.length / 2,
                    "y": element.position_y - element.width / 2,
                    "z": element.position_z
                },
                "max": {
                    "x": element.position_x + element.length / 2,
                    "y": element.position_y + element.width / 2,
                    "z": element.position_z + element.height
                }
            },
            
            # Walls for this room (4 walls)
            "walls": [
                # North wall
                {
                    "start": {"x": element.position_x - element.length/2, "y": element.position_y + element.width/2, "z": 0},
                    "end": {"x": element.position_x + element.length/2, "y": element.position_y + element.width/2, "z": 0},
                    "height": element.height
                },
                # South wall
                {
                    "start": {"x": element.position_x - element.length/2, "y": element.position_y - element.width/2, "z": 0},
                    "end": {"x": element.position_x + element.length/2, "y": element.position_y - element.width/2, "z": 0},
                    "height": element.height
                },
                # East wall
                {
                    "start": {"x": element.position_x + element.length/2, "y": element.position_y - element.width/2, "z": 0},
                    "end": {"x": element.position_x + element.length/2, "y": element.position_y + element.width/2, "z": 0},
                    "height": element.height
                },
                # West wall
                {
                    "start": {"x": element.position_x - element.length/2, "y": element.position_y - element.width/2, "z": 0},
                    "end": {"x": element.position_x - element.length/2, "y": element.position_y + element.width/2, "z": 0},
                    "height": element.height
                }
            ],
            
            # Floor
            "floor": {
                "vertices": [
                    {"x": element.position_x - element.length/2, "y": element.position_y - element.width/2, "z": 0},
                    {"x": element.position_x + element.length/2, "y": element.position_y - element.width/2, "z": 0},
                    {"x": element.position_x + element.length/2, "y": element.position_y + element.width/2, "z": 0},
                    {"x": element.position_x - element.length/2, "y": element.position_y + element.width/2, "z": 0}
                ],
                "material": element.properties.get("floor_material", "carpet")
            },
            
            # Ceiling
            "ceiling": {
                "vertices": [
                    {"x": element.position_x - element.length/2, "y": element.position_y - element.width/2, "z": element.height},
                    {"x": element.position_x + element.length/2, "y": element.position_y - element.width/2, "z": element.height},
                    {"x": element.position_x + element.length/2, "y": element.position_y + element.width/2, "z": element.height},
                    {"x": element.position_x - element.length/2, "y": element.position_y + element.width/2, "z": element.height}
                ],
                "material": "drywall"
            },
            
            # Properties
            "properties": element.properties
        }
    
    def _generate_wall_geometry(self, element: DesignElement) -> dict:
        """Generate standalone wall"""
        return {
            "id": element.id,
            "type": "wall",
            "start": {
                "x": element.position_x,
                "y": element.position_y,
                "z": element.position_z
            },
            "end": {
                "x": element.position_x + element.length,
                "y": element.position_y,
                "z": element.position_z
            },
            "height": element.height,
            "thickness": element.properties.get("thickness", 0.5),  # feet
            "material": element.properties.get("material", "drywall")
        }
    
    def _generate_door_geometry(self, element: DesignElement) -> dict:
        """Generate door opening in wall"""
        return {
            "id": element.id,
            "type": "door",
            "position": {
                "x": element.position_x,
                "y": element.position_y,
                "z": element.position_z
            },
            "width": element.properties.get("width", 3.0),  # 3 feet standard
            "height": element.properties.get("height", 6.67),  # 6'8" standard
            "rotation": element.rotation_z,
            "door_type": element.properties.get("door_type", "interior"),
            "material": element.properties.get("material", "wood")
        }
    
    def _generate_window_geometry(self, element: DesignElement) -> dict:
        """Generate window opening"""
        return {
            "id": element.id,
            "type": "window",
            "position": {
                "x": element.position_x,
                "y": element.position_y,
                "z": element.position_z + element.properties.get("sill_height", 3.0)  # 3ft above floor
            },
            "width": element.properties.get("width", 4.0),  # 4 feet
            "height": element.properties.get("height", 5.0),  # 5 feet
            "rotation": element.rotation_z,
            "glass_type": element.properties.get("glass_type", "double_pane")
        }
    
    def _generate_roof_geometry(self, element: DesignElement) -> dict:
        """Generate sloped or flat roof"""
        roof_type = element.properties.get("roof_type", "gable")
        pitch = element.properties.get("pitch", "4_12")  # 4:12 pitch
        
        # Calculate pitch angle
        if pitch == "4_12":
            pitch_angle = math.atan(4/12)  # ~18.4 degrees
        
        return {
            "id": element.id,
            "type": "roof",
            "roof_type": roof_type,
            "pitch": pitch,
            "pitch_angle": pitch_angle,
            "bounds": {
                "x": element.position_x,
                "y": element.position_y,
                "length": element.length,
                "width": element.width
            },
            "peak_height": element.height,
            "material": element.properties.get("material", "spanish_tile"),
            "color": element.properties.get("color", "terracotta")
        }
    
    def _generate_foundation_geometry(self, element: DesignElement) -> dict:
        """Generate foundation slab"""
        return {
            "id": element.id,
            "type": "foundation",
            "position": {
                "x": element.position_x,
                "y": element.position_y,
                "z": element.position_z
            },
            "dimensions": {
                "length": element.length,
                "width": element.width,
                "thickness": element.height
            },
            "material": "concrete"
        }
    
    async def _get_material_textures(self, project_id: int) -> dict:
        """
        Get material textures/colors for rendering
        """
        materials = db.query(ProjectMaterial).filter(
            ProjectMaterial.project_id == project_id
        ).join(Material).all()
        
        texture_map = {}
        for pm in materials:
            material_name = pm.material.category
            texture_map[material_name] = {
                "name": pm.material.name,
                "color": self._get_material_color(pm.material.category),
                "texture": self._get_material_texture(pm.material.category)
            }
        
        return texture_map
    
    def _get_material_color(self, category: str) -> dict:
        """Default colors for materials"""
        colors = {
            "drywall": {"r": 0.95, "g": 0.95, "b": 0.95},
            "carpet": {"r": 0.7, "g": 0.6, "b": 0.5},
            "tile": {"r": 0.9, "g": 0.85, "b": 0.8},
            "wood": {"r": 0.6, "g": 0.4, "b": 0.2},
            "concrete": {"r": 0.5, "g": 0.5, "b": 0.5},
            "spanish_tile": {"r": 0.8, "g": 0.3, "b": 0.2},
            "stucco": {"r": 0.9, "g": 0.85, "b": 0.75}
        }
        return colors.get(category, {"r": 0.8, "g": 0.8, "b": 0.8})
    
    def _get_material_texture(self, category: str) -> str:
        """Texture names (could be actual texture files)"""
        return f"{category}_texture"


# Add API endpoint
@router.get("/projects/{project_id}/generate-vr")
async def generate_vr_house(project_id: int):
    """
    Generate 3D VR house from database design
    Returns geometry data for Quest 2 to render
    """
    vr_service = VRGenerationService()
    geometry = await vr_service.generate_vr_house(project_id)
    
    return {
        "success": True,
        "geometry": geometry,
        "ready_for_vr": True
    }
```

---

**Quest 2: Procedural Geometry Generation**

```cpp
// vr_house_generator.h
#pragma once
#include <vector>
#include <glm/glm.hpp>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

struct Room3D {
    int id;
    std::string name;
    glm::vec3 position;
    glm::vec3 dimensions;  // length, width, height
    std::vector<glm::vec3> floorVertices;
    std::vector<glm::vec3> ceilingVertices;
    std::vector<Wall3D> walls;
    std::string floorMaterial;
};

struct Wall3D {
    glm::vec3 start;
    glm::vec3 end;
    float height;
    float thickness;
    std::string material;
};

struct Window3D {
    int id;
    glm::vec3 position;
    float width;
    float height;
    float rotation;
};

struct Door3D {
    int id;
    glm::vec3 position;
    float width;
    float height;
    float rotation;
    std::string doorType;
};

class VRHouseGenerator {
public:
    VRHouseGenerator();
    ~VRHouseGenerator();
    
    // Generate house from JSON data
    bool generateFromJSON(const json& geometryData);
    
    // Render the house
    void render();
    
    // Get spawn position (where user starts)
    glm::vec3 getPlayerSpawnPosition();
    
    // Collision detection
    bool checkCollision(glm::vec3 position, float radius);
    
private:
    std::vector<Room3D> rooms;
    std::vector<Wall3D> walls;
    std::vector<Window3D> windows;
    std::vector<Door3D> doors;
    
    GLuint floorMeshVAO;
    GLuint wallMeshVAO;
    GLuint roofMeshVAO;
    
    // Generate meshes
    void generateRoomMeshes(const Room3D& room);
    void generateWallMesh(const Wall3D& wall);
    void generateDoorMesh(const Door3D& door);
    void generateWindowMesh(const Window3D& window);
    
    // Rendering
    void renderRoom(const Room3D& room);
    void renderWall(const Wall3D& wall);
    void renderDoor(const Door3D& door);
    void renderWindow(const Window3D& window);
    
    // Collision
    bool pointInRoom(glm::vec3 point, const Room3D& room);
};
```

```cpp
// vr_house_generator.cpp
#include "vr_house_generator.h"
#include <android/log.h>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "VRHouseGen", __VA_ARGS__)

VRHouseGenerator::VRHouseGenerator() {
    LOGI("VR House Generator initialized");
}

bool VRHouseGenerator::generateFromJSON(const json& geometryData) {
    LOGI("Generating VR house from JSON data...");
    
    try {
        // Parse rooms
        if (geometryData.contains("rooms")) {
            for (const auto& roomData : geometryData["rooms"]) {
                Room3D room;
                room.id = roomData["id"];
                room.name = roomData["name"];
                
                // Position
                room.position = glm::vec3(
                    roomData["position"]["x"],
                    roomData["position"]["y"],
                    roomData["position"]["z"]
                );
                
                // Dimensions
                room.dimensions = glm::vec3(
                    roomData["dimensions"]["length"],
                    roomData["dimensions"]["width"],
                    roomData["dimensions"]["height"]
                );
                
                // Floor vertices
                for (const auto& v : roomData["floor"]["vertices"]) {
                    room.floorVertices.push_back(glm::vec3(
                        v["x"], v["y"], v["z"]
                    ));
                }
                
                // Walls
                for (const auto& wallData : roomData["walls"]) {
                    Wall3D wall;
                    wall.start = glm::vec3(
                        wallData["start"]["x"],
                        wallData["start"]["y"],
                        wallData["start"]["z"]
                    );
                    wall.end = glm::vec3(
                        wallData["end"]["x"],
                        wallData["end"]["y"],
                        wallData["end"]["z"]
                    );
                    wall.height = wallData["height"];
                    wall.thickness = 0.5f;  // 6 inches
                    room.walls.push_back(wall);
                }
                
                room.floorMaterial = roomData["floor"]["material"];
                
                rooms.push_back(room);
                
                // Generate OpenGL meshes for this room
                generateRoomMeshes(room);
            }
        }
        
        // Parse doors
        if (geometryData.contains("doors")) {
            for (const auto& doorData : geometryData["doors"]) {
                Door3D door;
                door.id = doorData["id"];
                door.position = glm::vec3(
                    doorData["position"]["x"],
                    doorData["position"]["y"],
                    doorData["position"]["z"]
                );
                door.width = doorData["width"];
                door.height = doorData["height"];
                door.rotation = doorData["rotation"];
                door.doorType = doorData["door_type"];
                
                doors.push_back(door);
                generateDoorMesh(door);
            }
        }
        
        // Parse windows
        if (geometryData.contains("windows")) {
            for (const auto& windowData : geometryData["windows"]) {
                Window3D window;
                window.id = windowData["id"];
                window.position = glm::vec3(
                    windowData["position"]["x"],
                    windowData["position"]["y"],
                    windowData["position"]["z"]
                );
                window.width = windowData["width"];
                window.height = windowData["height"];
                window.rotation = windowData["rotation"];
                
                windows.push_back(window);
                generateWindowMesh(window);
            }
        }
        
        LOGI("Generated %zu rooms, %zu doors, %zu windows", 
             rooms.size(), doors.size(), windows.size());
        
        return true;
        
    } catch (const std::exception& e) {
        LOGI("Error generating house: %s", e.what());
        return false;
    }
}

void VRHouseGenerator::generateRoomMeshes(const Room3D& room) {
    // Generate floor mesh
    std::vector<float> floorVertices;
    std::vector<unsigned int> floorIndices;
    
    // Floor is a simple quad
    // Bottom-left
    floorVertices.push_back(room.position.x - room.dimensions.x/2);
    floorVertices.push_back(room.position.y - room.dimensions.y/2);
    floorVertices.push_back(0.0f);
    // UV coordinates
    floorVertices.push_back(0.0f);
    floorVertices.push_back(0.0f);
    
    // Bottom-right
    floorVertices.push_back(room.position.x + room.dimensions.x/2);
    floorVertices.push_back(room.position.y - room.dimensions.y/2);
    floorVertices.push_back(0.0f);
    floorVertices.push_back(1.0f);
    floorVertices.push_back(0.0f);
    
    // Top-right
    floorVertices.push_back(room.position.x + room.dimensions.x/2);
    floorVertices.push_back(room.position.y + room.dimensions.y/2);
    floorVertices.push_back(0.0f);
    floorVertices.push_back(1.0f);
    floorVertices.push_back(1.0f);
    
    // Top-left
    floorVertices.push_back(room.position.x - room.dimensions.x/2);
    floorVertices.push_back(room.position.y + room.dimensions.y/2);
    floorVertices.push_back(0.0f);
    floorVertices.push_back(0.0f);
    floorVertices.push_back(1.0f);
    
    // Indices for two triangles
    floorIndices = {0, 1, 2, 2, 3, 0};
    
    // Create VAO/VBO for floor
    GLuint VAO, VBO, EBO;
    glGenVertexArrays(1, &VAO);
    glGenBuffers(1, &VBO);
    glGenBuffers(1, &EBO);
    
    glBindVertexArray(VAO);
    
    glBindBuffer(GL_ARRAY_BUFFER, VBO);
    glBufferData(GL_ARRAY_BUFFER, floorVertices.size() * sizeof(float), 
                 floorVertices.data(), GL_STATIC_DRAW);
    
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, floorIndices.size() * sizeof(unsigned int),
                 floorIndices.data(), GL_STATIC_DRAW);
    
    // Position attribute
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 5 * sizeof(float), (void*)0);
    glEnableVertexAttribArray(0);
    
    // UV attribute
    glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, 5 * sizeof(float), 
                         (void*)(3 * sizeof(float)));
    glEnableVertexAttribArray(1);
    
    // Generate wall meshes similarly...
}

void VRHouseGenerator::render() {
    // Render all rooms
    for (const auto& room : rooms) {
        renderRoom(room);
    }
    
    // Render doors
    for (const auto& door : doors) {
        renderDoor(door);
    }
    
    // Render windows
    for (const auto& window : windows) {
        renderWindow(window);
    }
}

void VRHouseGenerator::renderRoom(const Room3D& room) {
    // Set material/color based on room.floorMaterial
    if (room.floorMaterial == "carpet") {
        glm::vec3 carpetColor(0.7f, 0.6f, 0.5f);
        // Set shader color uniform
    } else if (room.floorMaterial == "tile") {
        glm::vec3 tileColor(0.9f, 0.85f, 0.8f);
    }
    
    // Render floor mesh
    // Render wall meshes
    // Render ceiling mesh
}

glm::vec3 VRHouseGenerator::getPlayerSpawnPosition() {
    // Spawn player in first room (or entry)
    if (rooms.empty()) {
        return glm::vec3(0, 0, 1.7f);  // 1.7m = eye height
    }
    
    // Spawn in center of first room
    return glm::vec3(
        rooms[0].position.x,
        rooms[0].position.y,
        1.7f  // Eye height
    );
}

bool VRHouseGenerator::checkCollision(glm::vec3 position, float radius) {
    // Simple collision: check if player is inside any room
    bool insideAnyRoom = false;
    
    for (const auto& room : rooms) {
        if (pointInRoom(position, room)) {
            insideAnyRoom = true;
            break;
        }
    }
    
    return !insideAnyRoom;  // Collision if outside all rooms
}

bool VRHouseGenerator::pointInRoom(glm::vec3 point, const Room3D& room) {
    float minX = room.position.x - room.dimensions.x / 2;
    float maxX = room.position.x + room.dimensions.x / 2;
    float minY = room.position.y - room.dimensions.y / 2;
    float maxY = room.position.y + room.dimensions.y / 2;
    
    return (point.x >= minX && point.x <= maxX &&
            point.y >= minY && point.y <= maxY &&
            point.z >= 0 && point.z <= room.dimensions.z);
}
```

---

**Using VR House Generator:**

```cpp
// main.cpp - Initialize and use

VRHouseGenerator* g_houseGenerator = nullptr;

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeLoadVRHouse(
    JNIEnv* env, jobject obj, jstring jsonData) {
    
    const char* jsonStr = env->GetStringUTFChars(jsonData, nullptr);
    LOGI("Loading VR house from JSON...");
    
    // Parse JSON
    json geometryData = json::parse(jsonStr);
    
    // Create house generator if not exists
    if (!g_houseGenerator) {
        g_houseGenerator = new VRHouseGenerator();
    }
    
    // Generate house meshes
    if (g_houseGenerator->generateFromJSON(geometryData)) {
        LOGI("VR house generated successfully!");
        
        // Move player to spawn position
        g_vrScene->setPlayerPosition(g_houseGenerator->getPlayerSpawnPosition());
    } else {
        LOGI("Failed to generate VR house");
    }
    
    env->ReleaseStringUTFChars(jsonData, jsonStr);
}

// In render loop
extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeFrame(
    JNIEnv* env, jobject obj) {
    
    if (g_vrScene) {
        g_vrScene->update();
        
        // Render generated house
        if (g_houseGenerator) {
            g_houseGenerator->render();
        }
        
        g_vrScene->render();
    }
}
```

**Android Project Structure:**
```
VRConstructionApp/
├── app/
│   ├── src/
│   │   ├── main/
│   │   │   ├── AndroidManifest.xml
│   │   │   ├── java/com/yourcompany/vrconstruction/
│   │   │   │   └── MainActivity.java
│   │   │   ├── cpp/
│   │   │   │   ├── CMakeLists.txt
│   │   │   │   ├── main.cpp
│   │   │   │   ├── vr_scene.cpp
│   │   │   │   ├── vr_scene.h
│   │   │   │   ├── design_manager.cpp
│   │   │   │   ├── design_manager.h
│   │   │   │   ├── network_client.cpp
│   │   │   │   ├── network_client.h
│   │   │   │   ├── ui_manager.cpp
│   │   │   │   ├── ui_manager.h
│   │   │   │   └── utils/
│   │   │   │       ├── json_helper.cpp
│   │   │   │       └── vector_math.h
│   │   │   ├── res/
│   │   │   │   ├── raw/          # 3D models, textures
│   │   │   │   └── values/
│   │   │   └── assets/
│   │   │       ├── models/       # Building component 3D models
│   │   │       ├── textures/
│   │   │       └── shaders/
│   ├── build.gradle
│   └── CMakeLists.txt
└── build.gradle
```

**AndroidManifest.xml:**
```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.yourcompany.vrconstruction">

    <!-- Quest 2 Permissions -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    
    <!-- Audio Recording for Voice Commands -->
    <uses-permission android:name="android.permission.RECORD_AUDIO" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE" />
    
    <!-- VR Features -->
    <uses-feature android:name="android.hardware.vr.headtracking" android:required="true" />
    <uses-feature android:glEsVersion="0x00030001" android:required="true" />
    <uses-feature android:name="android.hardware.microphone" android:required="true" />
    
    <!-- Quest-specific permissions -->
    <uses-permission android:name="com.oculus.permission.HAND_TRACKING" />
    <uses-feature android:name="oculus.software.handtracking" android:required="false" />

    <application
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="VR Construction"
        android:theme="@android:style/Theme.Black.NoTitleBar.Fullscreen"
        android:isGame="true">
        
        <!-- Quest VR Mode -->
        <meta-data android:name="com.oculus.vr.focusaware" android:value="true" />
        <meta-data android:name="com.oculus.handtracking.frequency" android:value="HIGH" />
        <meta-data android:name="com.oculus.handtracking.version" android:value="V2.0" />
        
        <!-- Main VR Activity -->
        <activity
            android:name=".MainActivity"
            android:screenOrientation="landscape"
            android:configChanges="orientation|keyboardHidden|screenSize"
            android:exported="true">
            
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
                <category android:name="com.oculus.intent.category.VR" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

**build.gradle (app level):**
```gradle
plugins {
    id 'com.android.application'
}

android {
    namespace 'com.yourcompany.vrconstruction'
    compileSdk 33

    defaultConfig {
        applicationId "com.yourcompany.vrconstruction"
        minSdk 29  // Quest 2 requirement
        targetSdk 33
        versionCode 1
        versionName "1.0"

        externalNativeBuild {
            cmake {
                cppFlags "-std=c++17 -frtti -fexceptions"
                arguments "-DANDROID_STL=c++_shared"
            }
        }

        ndk {
            abiFilters 'arm64-v8a'  // Quest 2 uses ARM64
        }
    }

    buildTypes {
        release {
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt')
        }
    }

    externalNativeBuild {
        cmake {
            path file('src/main/cpp/CMakeLists.txt')
            version '3.22.1'
        }
    }

    buildFeatures {
        prefab true
    }
}

dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    
    // Oculus SDK
    implementation 'com.oculus.sdk:ovr:1.87.0'
    
    // HTTP client for C++
    implementation 'com.squareup.okhttp3:okhttp:4.11.0'
}
```

**CMakeLists.txt:**
```cmake
cmake_minimum_required(VERSION 3.22.1)
project("vrconstruction")

# Set C++ standard
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Add Oculus SDK
find_package(oculus REQUIRED CONFIG)

# Source files
add_library(${CMAKE_PROJECT_NAME} SHARED
    main.cpp
    vr_scene.cpp
    design_manager.cpp
    network_client.cpp
    voice_manager.cpp
    ui_manager.cpp
    utils/json_helper.cpp
)

# Include directories
target_include_directories(${CMAKE_PROJECT_NAME} PRIVATE
    ${CMAKE_SOURCE_DIR}
    ${CMAKE_SOURCE_DIR}/utils
)

# Link libraries
target_link_libraries(${CMAKE_PROJECT_NAME}
    android
    log
    EGL
    GLESv3
    oculus::ovr
    curl  # For HTTP multipart upload
)

# JSON library (header-only)
include(FetchContent)
FetchContent_Declare(
    json
    URL https://github.com/nlohmann/json/releases/download/v3.11.2/json.tar.xz
)
FetchContent_MakeAvailable(json)
target_link_libraries(${CMAKE_PROJECT_NAME} nlohmann_json::nlohmann_json)

# libcurl for Android
find_library(CURL_LIBRARY curl)
if(CURL_LIBRARY)
    target_link_libraries(${CMAKE_PROJECT_NAME} ${CURL_LIBRARY})
endif()
```

**Core C++ Implementation:**

**MainActivity.java (Audio Recording):**

```java
// app/src/main/java/com/yourcompany/vrconstruction/MainActivity.java
package com.yourcompany.vrconstruction;

import android.app.Activity;
import android.os.Bundle;
import android.Manifest;
import android.content.pm.PackageManager;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import android.media.MediaRecorder;
import android.util.Log;
import java.io.File;
import java.io.IOException;

public class MainActivity extends Activity {
    private static final String TAG = "VRConstruction";
    private static final int REQUEST_RECORD_AUDIO_PERMISSION = 200;
    
    private MediaRecorder mediaRecorder;
    private String audioFilePath;
    private boolean isRecording = false;
    
    static {
        System.loadLibrary("vrconstruction");
    }
    
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // Request audio permission
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.RECORD_AUDIO},
                    REQUEST_RECORD_AUDIO_PERMISSION);
        }
        
        // Initialize native code
        nativeInit(getServerIP());
    }
    
    // Start recording audio
    public void startRecording() {
        if (isRecording) return;
        
        try {
            // Create temp file for audio
            File cacheDir = getCacheDir();
            audioFilePath = cacheDir.getAbsolutePath() + "/voice_command.wav";
            
            mediaRecorder = new MediaRecorder();
            mediaRecorder.setAudioSource(MediaRecorder.AudioSource.MIC);
            mediaRecorder.setOutputFormat(MediaRecorder.OutputFormat.THREE_GPP);
            mediaRecorder.setAudioEncoder(MediaRecorder.AudioEncoder.AMR_NB);
            mediaRecorder.setOutputFile(audioFilePath);
            
            mediaRecorder.prepare();
            mediaRecorder.start();
            isRecording = true;
            
            Log.i(TAG, "Started recording audio");
        } catch (IOException e) {
            Log.e(TAG, "Failed to start recording: " + e.getMessage());
        }
    }
    
    // Stop recording and send to backend
    public void stopRecordingAndSend() {
        if (!isRecording) return;
        
        try {
            mediaRecorder.stop();
            mediaRecorder.release();
            mediaRecorder = null;
            isRecording = false;
            
            Log.i(TAG, "Stopped recording, sending to backend");
            
            // Call native function to send audio
            nativeSendAudioFile(audioFilePath);
            
        } catch (RuntimeException e) {
            Log.e(TAG, "Failed to stop recording: " + e.getMessage());
        }
    }
    
    // Get server IP from native code or preferences
    private String getServerIP() {
        // TODO: Load from preferences or hardcode for prototype
        return "192.168.1.50";  // Your PC IP
    }
    
    // Native methods
    private native void nativeInit(String serverIp);
    private native void nativeFrame();
    private native void nativeSendAudioFile(String filePath);
    private native void nativeShutdown();
    
    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (isRecording) {
            mediaRecorder.stop();
            mediaRecorder.release();
        }
        nativeShutdown();
    }
}
```

**main.cpp:**
```cpp
#include <jni.h>
#include <android/log.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include "vr_scene.h"
#include "design_manager.h"
#include "network_client.h"
#include "voice_manager.h"
#include "ui_manager.h"

#define LOG_TAG "VRConstruction"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

VRScene* g_vrScene = nullptr;
DesignManager* g_designManager = nullptr;
NetworkClient* g_networkClient = nullptr;
VoiceManager* g_voiceManager = nullptr;
UIManager* g_uiManager = nullptr;
JavaVM* g_javaVM = nullptr;
jobject g_activityObj = nullptr;

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeInit(
    JNIEnv* env, jobject obj, jstring serverIpAddress) {
    
    const char* serverIp = env->GetStringUTFChars(serverIpAddress, nullptr);
    LOGI("Initializing VR Construction App, Server: %s", serverIp);
    
    // Store JavaVM and activity object for callbacks
    env->GetJavaVM(&g_javaVM);
    g_activityObj = env->NewGlobalRef(obj);
    
    // Initialize components
    g_networkClient = new NetworkClient(serverIp, 8000);
    g_designManager = new DesignManager();
    g_voiceManager = new VoiceManager(g_networkClient);
    g_uiManager = new UIManager();
    g_vrScene = new VRScene();
    
    // Set up voice callbacks
    g_voiceManager->setTranscriptionCallback([](const std::string& text) {
        // Text received from backend - display in VR
        LOGI("Transcription received: %s", text.c_str());
        g_uiManager->displayTranscribedText(text);
    });
    
    g_voiceManager->setAIResponseCallback([](const json& response) {
        // AI response received - handle it
        LOGI("AI response received");
        g_uiManager->handleAIResponse(response);
    });
    
    // Connect to backend
    if (g_networkClient->connect()) {
        LOGI("Connected to backend server");
    }
    
    env->ReleaseStringUTFChars(serverIpAddress, serverIp);
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeFrame(
    JNIEnv* env, jobject obj) {
    
    if (g_vrScene) {
        // Update VR scene
        g_vrScene->update();
        g_vrScene->render();
        
        // Update UI
        if (g_uiManager) {
            g_uiManager->update();
            g_uiManager->render();
        }
        
        // Check for voice responses
        if (g_voiceManager) {
            g_voiceManager->update();
        }
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeSendAudioFile(
    JNIEnv* env, jobject obj, jstring audioPath) {
    
    const char* path = env->GetStringUTFChars(audioPath, nullptr);
    LOGI("Sending audio file for transcription: %s", path);
    
    if (g_voiceManager) {
        // Send audio for transcription (not command execution)
        g_voiceManager->sendAudioForTranscription(path);
    }
    
    env->ReleaseStringUTFChars(audioPath, path);
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeShutdown(
    JNIEnv* env, jobject obj) {
    
    LOGI("Shutting down VR Construction App");
    
    if (g_activityObj) {
        env->DeleteGlobalRef(g_activityObj);
        g_activityObj = nullptr;
    }
    
    delete g_vrScene;
    delete g_uiManager;
    delete g_designManager;
    delete g_voiceManager;
    delete g_networkClient;
}

// Helper function to start/stop recording from C++
void startVoiceRecording() {
    if (g_javaVM && g_activityObj) {
        JNIEnv* env;
        g_javaVM->AttachCurrentThread(&env, nullptr);
        
        jclass activityClass = env->GetObjectClass(g_activityObj);
        jmethodID startRecording = env->GetMethodID(activityClass, "startRecording", "()V");
        env->CallVoidMethod(g_activityObj, startRecording);
        
        g_javaVM->DetachCurrentThread();
    }
}

void stopVoiceRecording() {
    if (g_javaVM && g_activityObj) {
        JNIEnv* env;
        g_javaVM->AttachCurrentThread(&env, nullptr);
        
        jclass activityClass = env->GetObjectClass(g_activityObj);
        jmethodID stopRecording = env->GetMethodID(activityClass, "stopRecordingAndSend", "()V");
        env->CallVoidMethod(g_activityObj, stopRecording);
        
        g_javaVM->DetachCurrentThread();
    }
}
```
#include <jni.h>
#include <android/log.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include "vr_scene.h"
#include "design_manager.h"
#include "network_client.h"
#include "voice_manager.h"

#define LOG_TAG "VRConstruction"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

VRScene* g_vrScene = nullptr;
DesignManager* g_designManager = nullptr;
NetworkClient* g_networkClient = nullptr;
VoiceManager* g_voiceManager = nullptr;
JavaVM* g_javaVM = nullptr;
jobject g_activityObj = nullptr;

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeInit(
    JNIEnv* env, jobject obj, jstring serverIpAddress) {
    
    const char* serverIp = env->GetStringUTFChars(serverIpAddress, nullptr);
    LOGI("Initializing VR Construction App, Server: %s", serverIp);
    
    // Store JavaVM and activity object for callbacks
    env->GetJavaVM(&g_javaVM);
    g_activityObj = env->NewGlobalRef(obj);
    
    // Initialize components
    g_networkClient = new NetworkClient(serverIp, 8000);
    g_designManager = new DesignManager();
    g_voiceManager = new VoiceManager(g_networkClient);
    g_vrScene = new VRScene();
    
    // Connect to backend
    if (g_networkClient->connect()) {
        LOGI("Connected to backend server");
    }
    
    env->ReleaseStringUTFChars(serverIpAddress, serverIp);
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeFrame(
    JNIEnv* env, jobject obj) {
    
    if (g_vrScene) {
        // Update VR scene
        g_vrScene->update();
        g_vrScene->render();
        
        // Check for voice command responses
        if (g_voiceManager) {
            g_voiceManager->update();
        }
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeSendAudioFile(
    JNIEnv* env, jobject obj, jstring audioPath) {
    
    const char* path = env->GetStringUTFChars(audioPath, nullptr);
    LOGI("Sending audio file: %s", path);
    
    if (g_voiceManager) {
        g_voiceManager->sendAudioCommand(path);
    }
    
    env->ReleaseStringUTFChars(audioPath, path);
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeShutdown(
    JNIEnv* env, jobject obj) {
    
    LOGI("Shutting down VR Construction App");
    
    if (g_activityObj) {
        env->DeleteGlobalRef(g_activityObj);
        g_activityObj = nullptr;
    }
    
    delete g_vrScene;
    delete g_designManager;
    delete g_voiceManager;
    delete g_networkClient;
}

// Helper function to start/stop recording from C++
void startVoiceRecording() {
    if (g_javaVM && g_activityObj) {
        JNIEnv* env;
        g_javaVM->AttachCurrentThread(&env, nullptr);
        
        jclass activityClass = env->GetObjectClass(g_activityObj);
        jmethodID startRecording = env->GetMethodID(activityClass, "startRecording", "()V");
        env->CallVoidMethod(g_activityObj, startRecording);
        
        g_javaVM->DetachCurrentThread();
    }
}

void stopVoiceRecording() {
    if (g_javaVM && g_activityObj) {
        JNIEnv* env;
        g_javaVM->AttachCurrentThread(&env, nullptr);
        
        jclass activityClass = env->GetObjectClass(g_activityObj);
        jmethodID stopRecording = env->GetMethodID(activityClass, "stopRecordingAndSend", "()V");
        env->CallVoidMethod(g_activityObj, stopRecording);
        
        g_javaVM->DetachCurrentThread();
    }
}
```

**voice_manager.h:**
```cpp
#pragma once
#include <string>
#include <functional>
#include "network_client.h"
#include "nlohmann/json.hpp"

using json = nlohmann::json;

class VoiceManager {
public:
    VoiceManager(NetworkClient* networkClient);
    ~VoiceManager();
    
    // Send audio file to backend for transcription
    void sendAudioForTranscription(const std::string& audioFilePath);
    
    // Send transcribed text as AI prompt
    void sendTextPrompt(const std::string& text, const std::string& promptType);
    
    // Check for responses
    void update();
    
    // Set callback for when transcription is received
    void setTranscriptionCallback(std::function<void(const std::string& text)> callback);
    
    // Set callback for AI response
    void setAIResponseCallback(std::function<void(const json& response)> callback);
    
private:
    NetworkClient* network;
    std::function<void(const std::string&)> transcriptionCallback;
    std::function<void(const json&)> aiResponseCallback;
    bool waitingForResponse;
    
    void handleTranscriptionResponse(const json& response);
    void handleAIPromptResponse(const json& response);
};
```

**voice_manager.cpp:**
```cpp
#include "voice_manager.h"
#include <fstream>
#include <android/log.h>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "VoiceManager", __VA_ARGS__)

VoiceManager::VoiceManager(NetworkClient* networkClient) 
    : network(networkClient), waitingForResponse(false) {
}

VoiceManager::~VoiceManager() {
}

void VoiceManager::sendAudioForTranscription(const std::string& audioFilePath) {
    LOGI("Sending audio for transcription: %s", audioFilePath.c_str());
    
    try {
        // Read audio file
        std::ifstream file(audioFilePath, std::ios::binary);
        if (!file.is_open()) {
            LOGI("Failed to open audio file");
            return;
        }
        
        // Get file size
        file.seekg(0, std::ios::end);
        size_t fileSize = file.tellg();
        file.seekg(0, std::ios::beg);
        
        // Read file content
        std::vector<char> audioData(fileSize);
        file.read(audioData.data(), fileSize);
        file.close();
        
        // Send to backend for transcription only
        json response = network->transcribeAudio(audioData);
        
        LOGI("Transcription response: %s", response.dump().c_str());
        
        // Handle response - extract text
        handleTranscriptionResponse(response);
        
    } catch (const std::exception& e) {
        LOGI("Error sending audio: %s", e.what());
    }
}

void VoiceManager::sendTextPrompt(const std::string& text, const std::string& promptType) {
    LOGI("Sending text prompt: '%s' (type: %s)", text.c_str(), promptType.c_str());
    
    try {
        json response = network->sendAIPrompt(text, promptType);
        handleAIPromptResponse(response);
    } catch (const std::exception& e) {
        LOGI("Error sending prompt: %s", e.what());
    }
}

void VoiceManager::update() {
    // Poll for any async responses if needed
}

void VoiceManager::setTranscriptionCallback(std::function<void(const std::string&)> callback) {
    transcriptionCallback = callback;
}

void VoiceManager::setAIResponseCallback(std::function<void(const json&)> callback) {
    aiResponseCallback = callback;
}

void VoiceManager::handleTranscriptionResponse(const json& response) {
    if (!response.contains("success") || !response["success"].get<bool>()) {
        LOGI("Transcription failed");
        return;
    }
    
    std::string transcribedText = response["text"].get<std::string>();
    LOGI("Transcribed text: %s", transcribedText.c_str());
    
    // Send text to UI for display
    if (transcriptionCallback) {
        transcriptionCallback(transcribedText);
    }
}

void VoiceManager::handleAIPromptResponse(const json& response) {
    if (!response.contains("success") || !response["success"].get<bool>()) {
        LOGI("AI prompt processing failed");
        return;
    }
    
    LOGI("AI response received: %s", response.dump().c_str());
    
    // Execute callback with full response
    if (aiResponseCallback) {
        aiResponseCallback(response);
    }
}
```
#include <jni.h>
#include <android/log.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include "vr_scene.h"
#include "design_manager.h"
#include "network_client.h"

#define LOG_TAG "VRConstruction"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)

VRScene* g_vrScene = nullptr;
DesignManager* g_designManager = nullptr;
NetworkClient* g_networkClient = nullptr;

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeInit(
    JNIEnv* env, jobject obj, jstring serverIpAddress) {
    
    const char* serverIp = env->GetStringUTFChars(serverIpAddress, nullptr);
    LOGI("Initializing VR Construction App, Server: %s", serverIp);
    
    // Initialize components
    g_networkClient = new NetworkClient(serverIp, 8000);
    g_designManager = new DesignManager();
    g_vrScene = new VRScene();
    
    // Connect to backend
    if (g_networkClient->connect()) {
        LOGI("Connected to backend server");
    }
    
    env->ReleaseStringUTFChars(serverIpAddress, serverIp);
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeFrame(
    JNIEnv* env, jobject obj) {
    
    if (g_vrScene) {
        // Update VR scene
        g_vrScene->update();
        g_vrScene->render();
    }
}

extern "C" JNIEXPORT void JNICALL
Java_com_yourcompany_vrconstruction_MainActivity_nativeShutdown(
    JNIEnv* env, jobject obj) {
    
    LOGI("Shutting down VR Construction App");
    
    delete g_vrScene;
    delete g_designManager;
    delete g_networkClient;
}
```

**design_manager.h:**
```cpp
#pragma once
#include <vector>
#include <string>
#include <glm/glm.hpp>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

enum class ElementType {
    WALL,
    FLOOR,
    CEILING,
    DOOR,
    WINDOW,
    ROOM
};

struct DesignElement {
    int id;
    ElementType type;
    glm::vec3 position;
    glm::vec3 rotation;
    glm::vec3 scale;
    json properties;
    
    json toJson() const;
    static DesignElement fromJson(const json& j);
};

class DesignManager {
public:
    DesignManager();
    ~DesignManager();
    
    // Design manipulation
    int addElement(ElementType type, glm::vec3 position);
    void updateElement(int elementId, glm::vec3 position, glm::vec3 rotation);
    void deleteElement(int elementId);
    
    // Data export
    json exportDesign() const;
    void importDesign(const json& designData);
    
    // Getters
    const std::vector<DesignElement>& getElements() const { return elements; }
    
private:
    std::vector<DesignElement> elements;
    int nextId;
};
```

**network_client.h:**
```cpp
#pragma once
#include <string>
#include <functional>
#include <vector>
#include "nlohmann/json.hpp"

using json = nlohmann::json;

class NetworkClient {
public:
    NetworkClient(const std::string& serverIp, int port);
    ~NetworkClient();
    
    bool connect();
    void disconnect();
    
    // API calls
    json createProject(const std::string& name, const std::string& type);
    json saveDesign(int projectId, const json& designData);
    json requestImageGeneration(int projectId, const std::string& viewType);
    json requestConstructionPlan(int projectId);
    
    // Voice/Text operations
    json transcribeAudio(const std::vector<char>& audioData);  // Returns transcribed text
    json sendAIPrompt(const std::string& text, const std::string& promptType);  // Send text as AI prompt
    
    // Image download
    std::vector<char> downloadImage(const std::string& imageUrl);  // Download generated image
    
    // Async callback
    void setImageReceivedCallback(std::function<void(const std::string&)> callback);
    
private:
    std::string serverIp;
    int port;
    bool connected;
    
    json httpPost(const std::string& endpoint, const json& data);
    json httpPostMultipart(const std::string& endpoint, 
                           const std::vector<char>& fileData,
                           const std::string& fieldName,
                           const std::string& fileName);
    json httpGet(const std::string& endpoint);
    std::vector<char> httpGetBinary(const std::string& url);  // For image download
};
```

**network_client.cpp (add image download):**
```cpp
std::vector<char> NetworkClient::downloadImage(const std::string& imageUrl) {
    LOGI("Downloading image: %s", imageUrl.c_str());
    
    return httpGetBinary(imageUrl);
}

std::vector<char> NetworkClient::httpGetBinary(const std::string& url) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        throw std::runtime_error("Failed to initialize CURL");
    }
    
    std::vector<char> responseData;
    
    // Callback for binary data
    auto writeCallback = [](void* contents, size_t size, size_t nmemb, void* userp) -> size_t {
        size_t totalSize = size * nmemb;
        std::vector<char>* vec = (std::vector<char>*)userp;
        vec->insert(vec->end(), (char*)contents, (char*)contents + totalSize);
        return totalSize;
    };
    
    // Setup curl
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &responseData);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);
    
    // Perform request
    CURLcode res = curl_easy_perform(curl);
    
    // Cleanup
    curl_easy_cleanup(curl);
    
    if (res != CURLE_OK) {
        throw std::runtime_error("Image download failed: " + std::string(curl_easy_strerror(res)));
    }
    
    LOGI("Image downloaded: %zu bytes", responseData.size());
    return responseData;
}
```

**image_panel.h (VR Image Display):**
```cpp
#pragma once
#include <glm/glm.hpp>
#include <GLES3/gl3.h>
#include <string>

class VRImagePanel {
public:
    VRImagePanel(glm::vec3 position, glm::vec2 size, GLuint textureId);
    ~VRImagePanel();
    
    void render();
    void setLabel(const std::string& label);
    void setPosition(glm::vec3 pos);
    void attachToController(glm::vec3 controllerPos);
    void detachFromController();
    
    bool rayIntersects(glm::vec3 rayOrigin, glm::vec3 rayDirection, float& distance);
    
private:
    glm::vec3 position;
    glm::vec2 size;
    GLuint textureId;
    std::string label;
    bool attachedToController;
    glm::vec3 attachOffset;
    
    void renderQuad();
    void renderLabel();
};
```

**image_panel.cpp:**
```cpp
#include "image_panel.h"
#include <android/log.h>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "ImagePanel", __VA_ARGS__)

VRImagePanel::VRImagePanel(glm::vec3 pos, glm::vec2 sz, GLuint texId) 
    : position(pos), size(sz), textureId(texId), attachedToController(false) {
    LOGI("Created image panel at (%.2f, %.2f, %.2f)", pos.x, pos.y, pos.z);
}

VRImagePanel::~VRImagePanel() {
    // Clean up texture
    glDeleteTextures(1, &textureId);
}

void VRImagePanel::render() {
    // Save current state
    glPushMatrix();
    
    // Position panel
    glTranslatef(position.x, position.y, position.z);
    
    // Enable texturing
    glEnable(GL_TEXTURE_2D);
    glBindTexture(GL_TEXTURE_2D, textureId);
    
    // Render quad with texture
    renderQuad();
    
    // Render label below image
    renderLabel();
    
    glDisable(GL_TEXTURE_2D);
    glPopMatrix();
}

void VRImagePanel::renderQuad() {
    float halfWidth = size.x / 2.0f;
    float halfHeight = size.y / 2.0f;
    
    glBegin(GL_QUADS);
    
    // Front face with texture coordinates
    glTexCoord2f(0.0f, 1.0f); glVertex3f(-halfWidth, -halfHeight, 0.0f);
    glTexCoord2f(1.0f, 1.0f); glVertex3f( halfWidth, -halfHeight, 0.0f);
    glTexCoord2f(1.0f, 0.0f); glVertex3f( halfWidth,  halfHeight, 0.0f);
    glTexCoord2f(0.0f, 0.0f); glVertex3f(-halfWidth,  halfHeight, 0.0f);
    
    glEnd();
}

void VRImagePanel::setLabel(const std::string& lbl) {
    label = lbl;
}

void VRImagePanel::renderLabel() {
    // Render text label below image
    glm::vec3 labelPos = position + glm::vec3(0, -size.y/2.0f - 0.1f, 0);
    renderText(label, labelPos, 0.05f);
}

bool VRImagePanel::rayIntersects(glm::vec3 rayOrigin, glm::vec3 rayDirection, float& distance) {
    // Simple ray-plane intersection for interaction
    // Panel is a plane at position facing camera
    glm::vec3 planeNormal(0, 0, 1);  // Facing +Z
    float denominator = glm::dot(rayDirection, planeNormal);
    
    if (abs(denominator) > 0.0001f) {
        float t = glm::dot(position - rayOrigin, planeNormal) / denominator;
        if (t >= 0) {
            glm::vec3 hitPoint = rayOrigin + rayDirection * t;
            glm::vec3 localHit = hitPoint - position;
            
            // Check if within panel bounds
            if (abs(localHit.x) <= size.x/2.0f && abs(localHit.y) <= size.y/2.0f) {
                distance = t;
                return true;
            }
        }
    }
    return false;
}

void VRImagePanel::attachToController(glm::vec3 controllerPos) {
    attachedToController = true;
    attachOffset = position - controllerPos;
}

void VRImagePanel::detachFromController() {
    attachedToController = false;
}

void VRImagePanel::setPosition(glm::vec3 pos) {
    position = pos;
}
```

**texture_loader.h:**
```cpp
#pragma once
#include <GLES3/gl3.h>
#include <vector>

// Load PNG image data as OpenGL texture
GLuint loadPNGAsTexture(const std::vector<char>& pngData);

// Load PNG from file
GLuint loadPNGFromFile(const std::string& filepath);
```

**texture_loader.cpp:**
```cpp
#include "texture_loader.h"
#include <android/log.h>

// You can use stb_image for PNG loading
#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "TextureLoader", __VA_ARGS__)

GLuint loadPNGAsTexture(const std::vector<char>& pngData) {
    LOGI("Loading PNG texture from memory, size: %zu bytes", pngData.size());
    
    int width, height, channels;
    unsigned char* imageData = stbi_load_from_memory(
        (unsigned char*)pngData.data(),
        pngData.size(),
        &width,
        &height,
        &channels,
        STBI_rgb_alpha  // Force RGBA
    );
    
    if (!imageData) {
        LOGI("Failed to load PNG: %s", stbi_failure_reason());
        return 0;
    }
    
    LOGI("Loaded PNG: %dx%d, %d channels", width, height, channels);
    
    // Create OpenGL texture
    GLuint textureId;
    glGenTextures(1, &textureId);
    glBindTexture(GL_TEXTURE_2D, textureId);
    
    // Upload texture data
    glTexImage2D(
        GL_TEXTURE_2D,
        0,
        GL_RGBA,
        width,
        height,
        0,
        GL_RGBA,
        GL_UNSIGNED_BYTE,
        imageData
    );
    
    // Set texture parameters
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    
    // Free image data
    stbi_image_free(imageData);
    
    LOGI("Texture created: ID=%u", textureId);
    return textureId;
}
```

**network_client.cpp (updated methods):**
```cpp
#include "network_client.h"
#include <curl/curl.h>
#include <android/log.h>

#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, "NetworkClient", __VA_ARGS__)

// ... (existing code)

json NetworkClient::transcribeAudio(const std::vector<char>& audioData) {
    LOGI("Sending audio for transcription, size: %zu bytes", audioData.size());
    
    // Send to /api/v1/voice/transcribe endpoint
    return httpPostMultipart(
        "/api/v1/voice/transcribe",
        audioData,
        "audio",
        "voice_input.wav"
    );
}

json NetworkClient::sendAIPrompt(const std::string& text, const std::string& promptType) {
    LOGI("Sending AI prompt: '%s' (type: %s)", text.c_str(), promptType.c_str());
    
    json requestData;
    requestData["text"] = text;
    requestData["type"] = promptType;  // 'image', 'design', 'question', 'materials', 'general'
    
    // Send to /api/v1/voice/prompt endpoint
    return httpPost("/api/v1/voice/prompt", requestData);
}

json NetworkClient::httpPostMultipart(
    const std::string& endpoint,
    const std::vector<char>& fileData,
    const std::string& fieldName,
    const std::string& fileName) {
    
    CURL* curl = curl_easy_init();
    if (!curl) {
        throw std::runtime_error("Failed to initialize CURL");
    }
    
    std::string url = "http://" + serverIp + ":" + std::to_string(port) + endpoint;
    std::string responseData;
    
    // Callback for response
    auto writeCallback = [](void* contents, size_t size, size_t nmemb, void* userp) -> size_t {
        ((std::string*)userp)->append((char*)contents, size * nmemb);
        return size * nmemb;
    };
    
    // Setup multipart form
    curl_mime* form = curl_mime_init(curl);
    curl_mimepart* field = curl_mime_addpart(form);
    
    curl_mime_name(field, fieldName.c_str());
    curl_mime_filename(field, fileName.c_str());
    curl_mime_data(field, fileData.data(), fileData.size());
    curl_mime_type(field, "audio/wav");
    
    // Setup curl
    curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
    curl_easy_setopt(curl, CURLOPT_MIMEPOST, form);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, writeCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &responseData);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 30L);  // 30 second timeout
    
    // Perform request
    CURLcode res = curl_easy_perform(curl);
    
    // Cleanup
    curl_mime_free(form);
    curl_easy_cleanup(curl);
    
    if (res != CURLE_OK) {
        throw std::runtime_error("CURL request failed: " + std::string(curl_easy_strerror(res)));
    }
    
    // Parse JSON response
    try {
        return json::parse(responseData);
    } catch (const json::parse_error& e) {
        LOGI("Failed to parse response: %s", responseData.c_str());
        throw std::runtime_error("Invalid JSON response");
    }
}
```

**VR Interaction System:**

**ui_manager.h:**
```cpp
#pragma once
#include <string>
#include <glm/glm.hpp>
#include "design_manager.h"
#include "network_client.h"

class UIManager {
public:
    UIManager();
    ~UIManager();
    
    void handleControllerInput(const ControllerState& controller);
    void render();
    
    // Text input/display
    void displayTranscribedText(const std::string& text);
    void showTextPromptDialog(const std::string& text);
    void handleAIResponse(const json& response);
    
private:
    bool menuVisible;
    bool voiceRecordingActive;
    bool voiceButtonHeld;
    bool voiceTogglePressed;
    bool showVoiceIndicator;
    
    // Text display state
    bool textDialogVisible;
    std::string currentTranscribedText;
    std::string selectedPromptType;  // 'image', 'design', 'question', etc.
    
    void createBuildMenu();
    void createMaterialPalette();
    void renderMenu();
    void renderVoiceRecordingIndicator();
    void renderTextDialog();
    void renderTextPromptTypeSelector();
    void sendTextAsPrompt();
    
    DesignManager* designManager;
    NetworkClient* networkClient;
};
```

**ui_manager.cpp:**
```cpp
#include "ui_manager.h"
#include <GLES3/gl3.h>

// External functions from main.cpp
extern void startVoiceRecording();
extern void stopVoiceRecording();

UIManager::UIManager() {
    createBuildMenu();
    createMaterialPalette();
    voiceButtonHeld = false;
    voiceRecordingActive = false;
    textDialogVisible = false;
    selectedPromptType = "general";
}

void UIManager::createBuildMenu() {
    // Create floating VR menu
    menu.addButton("Wall", ElementType::WALL);
    menu.addButton("Floor", ElementType::FLOOR);
    menu.addButton("Door", ElementType::DOOR);
    menu.addButton("Window", ElementType::WINDOW);
    menu.addButton("🎤 Voice Input", MenuAction::VOICE_COMMAND);
    menu.addButton("Generate Image", MenuAction::GENERATE_IMAGE);
    menu.addButton("Save Design", MenuAction::SAVE);
    menu.addButton("Create Plan", MenuAction::CREATE_PLAN);
}

void UIManager::handleControllerInput(const ControllerState& controller) {
    // If text dialog is visible, handle text dialog input
    if (textDialogVisible) {
        if (controller.triggerPressed) {
            // Send button clicked
            sendTextAsPrompt();
        }
        if (controller.gripPressed) {
            // Cancel button clicked
            textDialogVisible = false;
            currentTranscribedText = "";
        }
        return;  // Don't handle other inputs while dialog is open
    }
    
    // Normal input handling
    if (controller.triggerPressed) {
        if (selectedElementType != ElementType::NONE) {
            glm::vec3 spawnPos = controller.position + controller.forward * 2.0f;
            designManager->addElement(selectedElementType, spawnPos);
        }
    }
    
    if (controller.gripPressed) {
        menuVisible = !menuVisible;
    }
    
    // X/A button - Push-to-talk for voice input
    if (controller.buttonXPressed && !voiceButtonHeld) {
        startVoiceRecording();
        voiceButtonHeld = true;
        voiceRecordingActive = true;
        showVoiceIndicator = true;
        LOGI("Started voice recording");
    }
    
    if (!controller.buttonXPressed && voiceButtonHeld) {
        stopVoiceRecording();  // This will trigger transcription
        voiceButtonHeld = false;
        voiceRecordingActive = false;
        showVoiceIndicator = false;
        LOGI("Stopped voice recording - sending for transcription");
    }
}

void UIManager::render() {
    if (menuVisible) {
        renderMenu();
    }
    
    if (showVoiceIndicator) {
        renderVoiceRecordingIndicator();
    }
    
    if (textDialogVisible) {
        renderTextDialog();
    }
    
    renderSelectedElementPreview();
}

void UIManager::renderVoiceRecordingIndicator() {
    // Render a pulsing microphone icon to show recording is active
    float pulseScale = 1.0f + 0.2f * sin(currentTime * 5.0f);
    
    // Position in front of user's view
    glm::vec3 indicatorPos = cameraPosition + cameraForward * 1.5f + glm::vec3(0, 0.3f, 0);
    
    // Render red pulsing sphere
    renderSphere(indicatorPos, 0.05f * pulseScale, glm::vec3(1.0f, 0.0f, 0.0f));
    
    // Render text
    renderText("🎤 Recording...", indicatorPos + glm::vec3(0.1f, 0, 0));
}

void UIManager::displayTranscribedText(const std::string& text) {
    LOGI("Displaying transcribed text: %s", text.c_str());
    
    currentTranscribedText = text;
    textDialogVisible = true;
    selectedPromptType = "general";  // Default type
}

void UIManager::renderTextDialog() {
    // Render a floating panel in VR showing the transcribed text
    
    glm::vec3 panelPos = cameraPosition + cameraForward * 2.0f;
    glm::vec2 panelSize(1.2f, 0.8f);
    
    // Background panel
    renderQuad(panelPos, panelSize, glm::vec4(0.1f, 0.1f, 0.15f, 0.95f));
    
    // Title
    glm::vec3 titlePos = panelPos + glm::vec3(-0.5f, 0.3f, 0.01f);
    renderText("Voice Input", titlePos, 0.06f);
    
    // Transcribed text (with word wrap)
    glm::vec3 textPos = panelPos + glm::vec3(-0.5f, 0.15f, 0.01f);
    renderTextWrapped(currentTranscribedText, textPos, 0.04f, 1.0f);
    
    // Prompt type selector buttons
    renderTextPromptTypeSelector();
    
    // Buttons
    glm::vec3 sendButtonPos = panelPos + glm::vec3(-0.2f, -0.25f, 0.01f);
    glm::vec3 cancelButtonPos = panelPos + glm::vec3(0.2f, -0.25f, 0.01f);
    
    renderButton("Send", sendButtonPos, glm::vec2(0.3f, 0.1f), glm::vec3(0.2f, 0.7f, 0.2f));
    renderButton("Cancel", cancelButtonPos, glm::vec2(0.3f, 0.1f), glm::vec3(0.7f, 0.2f, 0.2f));
    
    // Instructions
    glm::vec3 instructionPos = panelPos + glm::vec3(-0.5f, -0.35f, 0.01f);
    renderText("Trigger: Send | Grip: Cancel", instructionPos, 0.025f);
}

void UIManager::renderTextPromptTypeSelector() {
    // Small buttons to select prompt type
    glm::vec3 basePos = cameraPosition + cameraForward * 2.0f;
    glm::vec3 selectorPos = basePos + glm::vec3(-0.5f, -0.05f, 0.01f);
    
    renderText("Use for:", selectorPos, 0.03f);
    
    const char* types[] = {"General", "Image", "Design", "Question", "Materials"};
    const char* typeKeys[] = {"general", "image", "design", "question", "materials"};
    
    for (int i = 0; i < 5; i++) {
        glm::vec3 buttonPos = selectorPos + glm::vec3(0.12f + i * 0.16f, 0, 0);
        bool isSelected = (selectedPromptType == typeKeys[i]);
        
        glm::vec3 color = isSelected ? glm::vec3(0.3f, 0.6f, 1.0f) : glm::vec3(0.3f, 0.3f, 0.3f);
        renderButton(types[i], buttonPos, glm::vec2(0.14f, 0.06f), color);
    }
}

void UIManager::sendTextAsPrompt() {
    LOGI("Sending text as AI prompt: '%s' (type: %s)", 
         currentTranscribedText.c_str(), selectedPromptType.c_str());
    
    // Send to backend
    g_voiceManager->sendTextPrompt(currentTranscribedText, selectedPromptType);
    
    // Close dialog
    textDialogVisible = false;
    
    // Show processing message
    showNotification("Processing: " + currentTranscribedText);
}

void UIManager::handleAIResponse(const json& response) {
    LOGI("Received AI response: %s", response.dump().c_str());
    
    std::string responseType = response.value("type", "unknown");
    
    if (responseType == "image_generated") {
        // Image was generated
        std::string imageUrl = response["image_url"];
        std::string message = response["message"];
        
        showNotification(message);
        // Download and display image in VR
        downloadAndDisplayImage(imageUrl);
        
    } else if (responseType == "design_modification") {
        // Design should be modified
        json action = response["action"];
        applyDesignAction(action);
        showNotification(response["message"]);
        
    } else if (responseType == "answer") {
        // Question was answered
        std::string answer = response["answer"];
        showLongTextDialog("AI Assistant", answer);
        
    } else if (responseType == "materials") {
        // Material suggestions
        showMaterialSuggestions(response["suggestions"]);
        
    } else {
        // General response
        std::string message = response.value("response", "Request processed");
        showNotification(message);
    }
}

void UIManager::downloadAndDisplayImage(const std::string& imageUrl) {
    LOGI("Downloading image: %s", imageUrl.c_str());
    
    // Show loading indicator
    showNotification("Downloading image...");
    
    try {
        // Build full URL
        std::string fullUrl = "http://" + serverIp + ":8000" + imageUrl;
        
        // Download image data
        std::vector<char> imageData = networkClient->downloadImage(fullUrl);
        LOGI("Image downloaded: %zu bytes", imageData.size());
        
        // Load as OpenGL texture
        GLuint textureId = loadPNGAsTexture(imageData);
        if (textureId == 0) {
            showNotification("Failed to load image");
            return;
        }
        
        // Create floating image panel in VR
        // Position it 3 meters in front of camera, slightly to the left
        glm::vec3 imagePos = cameraPosition + cameraForward * 3.0f + cameraLeft * 0.5f;
        glm::vec2 imageSize(2.0f, 2.0f);  // 2m x 2m panel
        
        // Create image panel
        VRImagePanel* panel = new VRImagePanel(imagePos, imageSize, textureId);
        panel->setLabel("AI Generated Image");
        
        // Add to active panels list
        activeImagePanels.push_back(panel);
        
        showNotification("Image loaded!");
        
    } catch (const std::exception& e) {
        LOGI("Failed to download/display image: %s", e.what());
        showNotification("Failed to load image");
    }
}

void UIManager::updateImagePanels(const ControllerState& controller) {
    // Update all active image panels
    for (auto panel : activeImagePanels) {
        // If panel is attached to controller, update its position
        if (panel->isAttachedToController()) {
            panel->setPosition(controller.position + panel->getAttachOffset());
        }
        
        // Check for ray intersection
        glm::vec3 rayOrigin = controller.position;
        glm::vec3 rayDirection = controller.forward;
        float distance;
        
        if (panel->rayIntersects(rayOrigin, rayDirection, distance)) {
            // Highlight panel
            panel->setHighlighted(true);
            
            // Handle controller input
            if (controller.triggerJustPressed) {
                // Grab panel
                panel->attachToController(controller.position);
                LOGI("Grabbed image panel");
            }
            
            if (controller.gripJustPressed) {
                // Show options menu
                showImageOptionsMenu(panel);
            }
        } else {
            panel->setHighlighted(false);
        }
        
        // Release panel if trigger released
        if (controller.triggerJustReleased && panel->isAttachedToController()) {
            panel->detachFromController();
            LOGI("Released image panel");
        }
    }
}

void UIManager::showImageOptionsMenu(VRImagePanel* panel) {
    // Show floating menu near the image panel
    currentImageOptionsPanel = panel;
    imageOptionsMenuVisible = true;
    
    // Menu options:
    // - Save to project
    // - Generate variation
    // - Delete image
    // - Set as reference
    // - Pin in place
}
```

**Deliverables:**
- ✓ Quest 2 project created in Android Studio
- ✓ VR scene rendering working
- ✓ Controller input handling
- ✓ **Voice-to-text system integrated**
- ✓ **Text display panel in VR**
- ✓ **Audio recording and transmission to backend**
- ✓ **Transcribed text shown for user confirmation**
- ✓ **Text sent as AI prompt with type selection**
- ✓ Design element placement in VR
- ✓ 3D building component library
- ✓ Network communication to backend
- ✓ UI menu system in VR
- ✓ **Voice recording indicator in VR**
- ✓ **Multi-purpose AI prompt system**

**Updated Voice-to-Text Workflow:**

1. **User speaks**: Holds X/A button and speaks into Quest 2 microphone
2. **Recording indicator**: Red pulsing sphere shows recording is active
3. **Stop recording**: Releases button, audio sent to backend
4. **Backend transcribes**: Whisper converts audio to text
5. **Text displayed in VR**: Floating panel shows transcribed text
6. **User selects type**: Chooses what to do with text (Image, Design, Question, Materials, General)
7. **User confirms**: Presses trigger to send, or grip to cancel
8. **Backend processes**: Text used as AI prompt based on selected type
9. **Results shown**: Response displayed in VR (image, answer, design change, etc.)

**Example Use Cases:**

**Complete Walkthrough - Dog House Example:**

Let's trace the full flow for: *"Show me image of dog house made with cedar tongue and groove for a German Shepherd"*

**Step 1: User Speaks in VR (Quest 2)**
```cpp
// User holds X/A button on controller
// ui_manager.cpp detects button press
if (controller.buttonXPressed && !voiceButtonHeld) {
    startVoiceRecording();  // Calls Java method
    voiceButtonHeld = true;
    voiceRecordingActive = true;
    showVoiceIndicator = true;
}

// User speaks: "Show me image of dog house made with cedar tongue and groove for a German Shepherd"
// Audio is being recorded by Android MediaRecorder

// User releases button
if (!controller.buttonXPressed && voiceButtonHeld) {
    stopVoiceRecording();  // Sends audio to backend
    voiceButtonHeld = false;
    voiceRecordingActive = false;
}
```

**Step 2: Audio Sent to Backend**
```cpp
// MainActivity.java - stopRecordingAndSend()
// Audio file saved at: /cache/voice_command.wav
nativeSendAudioFile(audioFilePath);

// main.cpp
Java_com_yourcompany_vrconstruction_MainActivity_nativeSendAudioFile() {
    g_voiceManager->sendAudioForTranscription("/cache/voice_command.wav");
}

// voice_manager.cpp
void VoiceManager::sendAudioForTranscription(const std::string& audioFilePath) {
    // Read audio file (WAV format, ~2-5 seconds, ~200KB)
    std::vector<char> audioData = readFile(audioFilePath);
    
    // Send via HTTP multipart to backend
    json response = network->transcribeAudio(audioData);
    // POST http://192.168.1.50:8000/api/v1/voice/transcribe
}
```

**Step 3: Backend Receives & Transcribes**
```python
# app/api/v1/voice.py
@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    # Receives WAV file (~200KB)
    audio_data = await audio.read()
    
    # Process with Whisper
    result = await speech_service.transcribe_audio_bytes(audio_data)
    # Whisper model processes audio (~1-2 seconds on GPU)
    
    # Returns JSON
    return {
        "success": True,
        "text": "Show me image of dog house made with cedar tongue and groove for a German Shepherd",
        "language": "en",
        "confidence": 0.94
    }
```

**Step 4: Text Displayed in Quest 2**
```cpp
// voice_manager.cpp
void VoiceManager::handleTranscriptionResponse(const json& response) {
    std::string text = response["text"];  
    // "Show me image of dog house made with cedar tongue and groove for a German Shepherd"
    
    // Callback to UI
    transcriptionCallback(text);
}

// ui_manager.cpp
void UIManager::displayTranscribedText(const std::string& text) {
    currentTranscribedText = text;
    textDialogVisible = true;
    selectedPromptType = "general";  // Default
    
    // VR now shows floating dialog with:
    // ┌─────────────────────────────────────────┐
    // │          Voice Input                    │
    // ├─────────────────────────────────────────┤
    // │ "Show me image of dog house made with   │
    // │  cedar tongue and groove for a German   │
    // │  Shepherd"                              │
    // ├─────────────────────────────────────────┤
    // │ Use for:                                │
    // │ [General] [Image] [Design] [Question]   │
    // ├─────────────────────────────────────────┤
    // │        [Send]        [Cancel]           │
    // └─────────────────────────────────────────┘
}
```

**Step 5: User Selects "Image" Type**
```cpp
// User points controller at "Image" button and clicks trigger
// ui_manager.cpp
void UIManager::handleTextDialogInput(const ControllerState& controller) {
    // Check which button was clicked
    if (hoveredButton == "Image") {
        selectedPromptType = "image";
        // Button highlights in blue
    }
}
```

**Step 6: User Confirms and Sends**
```cpp
// User points at "Send" button and pulls trigger
void UIManager::sendTextAsPrompt() {
    // currentTranscribedText = "Show me image of dog house..."
    // selectedPromptType = "image"
    
    g_voiceManager->sendTextPrompt(currentTranscribedText, selectedPromptType);
    
    textDialogVisible = false;
    showNotification("Generating image...");
}

// voice_manager.cpp
void VoiceManager::sendTextPrompt(const std::string& text, const std::string& promptType) {
    json response = network->sendAIPrompt(text, promptType);
    // POST http://192.168.1.50:8000/api/v1/voice/prompt
}
```

**Step 7: Backend Processes Image Request**
```python
# app/api/v1/voice.py
@router.post("/prompt")
async def process_ai_prompt(request: dict):
    prompt_text = request["text"]
    # "Show me image of dog house made with cedar tongue and groove for a German Shepherd"
    
    prompt_type = request["type"]  # "image"
    
    # Route to image generation
    return await generate_image_from_prompt(prompt_text, context={})


async def generate_image_from_prompt(prompt: str, context: dict):
    from app.services.ai_image_service import ai_image_service
    
    # Enhance prompt for architectural rendering
    enhanced_prompt = f"architectural detailed rendering: {prompt}, photorealistic, professional construction drawing, high quality"
    
    # Full prompt: "architectural detailed rendering: Show me image of dog house 
    # made with cedar tongue and groove for a German Shepherd, photorealistic, 
    # professional construction drawing, high quality"
    
    # Generate image using Stable Diffusion
    image_path = await ai_image_service.generate_from_text_prompt(
        prompt=enhanced_prompt,
        project_id=None
    )
    
    return {
        "success": True,
        "type": "image_generated",
        "image_url": f"/images/{image_path}",
        "image_path": image_path,
        "message": "Generated dog house image"
    }
```

**Step 8: AI Image Service Generates Image**
```python
# app/services/ai_image_service.py
async def generate_from_text_prompt(self, prompt: str, project_id: int = None):
    # Load Stable Diffusion model (if not already loaded)
    if not self.sd_loaded:
        self.load_stable_diffusion()
    
    # Generate image
    image = self.sd_pipe(
        prompt,
        num_inference_steps=50,  # Higher quality
        guidance_scale=7.5,
        height=768,
        width=768
    ).images[0]
    
    # Save image
    timestamp = int(time.time())
    filename = f"doghouse_{timestamp}.png"
    image_path = f"generated_images/{filename}"
    
    image.save(image_path)
    
    # Image generated: 768x768 PNG of cedar dog house
    # Features: tongue and groove siding, sized for German Shepherd
    
    return filename  # "doghouse_1704398234.png"
```

**Step 9: Response Returned to Quest 2**
```python
# Backend returns JSON:
{
    "success": true,
    "type": "image_generated",
    "image_url": "/images/doghouse_1704398234.png",
    "image_path": "doghouse_1704398234.png",
    "message": "Generated dog house image"
}
```

**Step 10: Quest 2 Receives Response**
```cpp
// voice_manager.cpp
void VoiceManager::handleAIPromptResponse(const json& response) {
    // Pass to UI manager
    aiResponseCallback(response);
}

// ui_manager.cpp
void UIManager::handleAIResponse(const json& response) {
    std::string responseType = response["type"];  // "image_generated"
    
    if (responseType == "image_generated") {
        std::string imageUrl = response["image_url"];
        // "/images/doghouse_1704398234.png"
        
        std::string message = response["message"];
        // "Generated dog house image"
        
        showNotification(message);
        
        // Download and display image
        downloadAndDisplayImage(imageUrl);
    }
}
```

**Step 11: Image Downloaded and Displayed in VR**
```cpp
void UIManager::downloadAndDisplayImage(const std::string& imageUrl) {
    // Download image from backend
    std::string fullUrl = "http://192.168.1.50:8000" + imageUrl;
    
    std::vector<char> imageData = g_networkClient->downloadImage(fullUrl);
    // Downloads PNG file (~500KB - 2MB)
    
    // Load as OpenGL texture
    GLuint textureId = loadPNGAsTexture(imageData);
    
    // Create floating image panel in VR space
    glm::vec3 imagePos = cameraPosition + cameraForward * 3.0f;
    glm::vec2 imageSize(2.0f, 2.0f);  // 2m x 2m panel in VR
    
    // Display image on 3D quad
    VRImagePanel* panel = new VRImagePanel(imagePos, imageSize, textureId);
    panel->setLabel("Cedar Dog House for German Shepherd");
    activeImagePanels.push_back(panel);
    
    // User now sees:
    // - Large floating image in VR space
    // - Shows detailed rendering of cedar tongue and groove dog house
    // - Sized appropriately for German Shepherd
    // - Professional architectural quality
    // - User can move closer/further to examine details
    // - User can grab and reposition image panel
}
```

**Step 12: User Interaction with Image**
```cpp
// User can now:
// - View image from different angles
// - Zoom in to see cedar tongue and groove detail
// - Grab image panel to reposition it
// - Pin it to reference while designing
// - Generate variations ("make it darker cedar")
// - Use it as inspiration for actual design

// Controller interactions:
if (controller.rayHitsImage(panel)) {
    if (controller.triggerPressed) {
        // Grab and move image
        panel->attachToController(controller);
    }
    
    if (controller.gripPressed) {
        // Show image options menu:
        // - Save to project
        // - Generate variation
        // - Close image
        // - Set as reference
    }
}
```

**Complete Timeline:**
```
0.0s  - User presses button, starts speaking
3.0s  - User releases button, audio sent (3 seconds of speech)
3.2s  - Backend receives audio (200ms network)
4.5s  - Whisper transcribes (1.3s processing)
4.7s  - Text displayed in Quest 2 (200ms network)
      - User reviews text, selects "Image", clicks Send
5.5s  - User confirms (0.8s user interaction)
5.7s  - Backend receives prompt (200ms network)
20.0s - Stable Diffusion generates image (14.3s GPU processing)
20.5s - Image sent to Quest 2 (500ms for ~1MB image)
20.7s - Image decoded and displayed (200ms)

Total: ~21 seconds from speaking to seeing image
```

**What the User Sees:**

**T+4.7s:** VR Dialog appears
```
┌──────────────────────────────────────────────┐
│              Voice Input                      │
├──────────────────────────────────────────────┤
│ "Show me image of dog house made with cedar  │
│  tongue and groove for a German Shepherd"    │
│                                              │
│ Confidence: 94%                              │
├──────────────────────────────────────────────┤
│ Use for:                                     │
│ [General] [Image✓] [Design] [Question] [Mat]│
├──────────────────────────────────────────────┤
│        [Send ▶]        [Cancel ✕]            │
└──────────────────────────────────────────────┘
```

**T+5.7s:** After clicking Send
```
┌──────────────────────┐
│  Generating image... │
│  ⏳ Please wait      │
└──────────────────────┘
```

**T+20.7s:** Image Displayed
```
    User's view in VR:
    
    ┌─────────────────────────────────────┐
    │  Cedar Dog House - German Shepherd  │
    ├─────────────────────────────────────┤
    │                                     │
    │     [Beautiful rendering of:        │
    │      - Cedar tongue & groove siding │
    │      - Sloped roof with shingles    │
    │      - Large entrance for GSD       │
    │      - Raised floor                 │
    │      - Natural wood finish]         │
    │                                     │
    └─────────────────────────────────────┘
    
    Point and click to move
    Grip for options
```

---

**Scenario 1 - Generate Image (Simple):**
- User: *holds button* "A modern two-story house with large windows and a pitched roof"
- VR displays: "A modern two-story house with large windows and a pitched roof"
- User selects: "Image" type
- User confirms with trigger
- Backend: Generates image using Stable Diffusion
- VR displays: Generated architectural rendering

**Scenario 2 - Ask Question:**
- User: "How much will the materials cost for this design?"
- VR displays: "How much will the materials cost for this design?"
- User selects: "Question" type
- Backend: Calculates materials, generates cost estimate using LLM
- VR displays: Detailed answer with breakdown

**Scenario 3 - Modify Design:**
- User: "Make the living room 20 feet wide instead of 15"
- VR displays: Text
- User selects: "Design" type
- Backend: Parses intent, generates design modification
- VR: Applies modification and shows updated design

**Scenario 4 - Material Search:**
- User: "What's the best drywall for sound insulation?"
- VR displays: Text
- User selects: "Materials" type
- Backend: Searches material database, suggests options
- VR displays: Material suggestions with specs and prices

**Testing Voice-to-Text:**

```bash
# Test transcription endpoint
curl -X POST http://localhost:8000/api/v1/voice/test

# Test transcription with audio file
curl -X POST http://localhost:8000/api/v1/voice/transcribe \
  -F "audio=@test_audio.wav"

# Expected response:
# {
#   "success": true,
#   "text": "generate a modern house with large windows",
#   "language": "en",
#   "confidence": 0.95
# }

# Test AI prompt processing
curl -X POST http://localhost:8000/api/v1/voice/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "text": "create a rendering of a modern house",
    "type": "image"
  }'

# Test from Quest 2:
# 1. Hold X/A button on controller
# 2. Speak clearly: "Generate a modern two-story house"
# 3. Release button
# 4. VR displays: Text panel with transcription
# 5. Select "Image" type
# 6. Press trigger to confirm
# 7. Check backend logs: docker compose logs -f backend
# 8. Should see: "Processing AI prompt: 'generate a modern two-story house' (type: image)"
# 9. Image generation starts
```

---

### Phase 5: Integration & Data Flow (Weeks 15-17)

**Complete Workflow Implementation:**

**1. Design → Image Generation Flow:**

```cpp
// In Quest 2 app
void VRScene::requestImageGeneration() {
    // Export current design
    json designData = g_designManager->exportDesign();
    
    // Send to backend
    json response = g_networkClient->requestImageGeneration(
        currentProjectId,
        "exterior"  // or "interior", "aerial"
    );
    
    if (response["status"] == "processing") {
        showNotification("Generating image...");
        pollForImage(response["task_id"]);
    }
}

void VRScene::pollForImage(const std::string& taskId) {
    // Poll backend for image completion
    // When ready, download and display in VR
}
```

**Backend handling:**
```python
# app/api/v1/ai_image.py
from fastapi import APIRouter, BackgroundTasks
from app.services.ai_image_service import AIImageService

router = APIRouter()
ai_service = AIImageService()

@router.post("/generate")
async def generate_image(
    project_id: int,
    view_type: str,
    background_tasks: BackgroundTasks
):
    # Fetch project design data
    design_data = get_project_design(project_id)
    
    # Generate image asynchronously
    task_id = create_task_id()
    background_tasks.add_task(
        ai_service.generate_rendering,
        design_data,
        view_type,
        task_id
    )
    
    return {
        "status": "processing",
        "task_id": task_id,
        "estimated_time": 30  # seconds
    }

@router.get("/status/{task_id}")
async def check_image_status(task_id: str):
    # Check if image is ready
    if image_ready(task_id):
        return {
            "status": "complete",
            "image_url": f"/api/v1/images/{task_id}.png"
        }
    return {"status": "processing"}
```

**2. Design → Construction Plan Flow:**

```python
# app/api/v1/ai_planning.py
@router.post("/generate")
async def generate_plan(project_id: int):
    # Get full project data
    project = db.query(Project).filter(Project.id == project_id).first()
    design_elements = db.query(DesignElement).filter(
        DesignElement.project_id == project_id
    ).all()
    
    # Calculate materials
    material_calc = await planning_service.calculate_material_quantities(design_elements)
    
    # Generate AI plan
    plan_data = await planning_service.generate_construction_plan({
        'project': project,
        'elements': design_elements,
        'materials': material_calc
    })
    
    # Save to database
    construction_plan = ConstructionPlan(
        project_id=project_id,
        content=plan_data,
        ai_model='llama3.1'
    )
    db.add(construction_plan)
    db.commit()
    
    # Create detailed tasks
    for phase in plan_data['phases']:
        for task in phase['tasks']:
            build_task = BuildTask(
                construction_plan_id=construction_plan.id,
                task_name=task['name'],
                phase=phase['name'],
                estimated_duration=task['duration'],
                estimated_cost=task['cost']
            )
            db.add(build_task)
    
    db.commit()
    
    return {
        "plan_id": construction_plan.id,
        "summary": plan_data
    }
```

**3. WebSocket for Real-time Updates:**

```python
# app/api/v1/websocket.py
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
    
    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket
    
    async def send_update(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)

manager = ConnectionManager()

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle real-time updates from Quest 2
            if data['type'] == 'element_update':
                # Broadcast to other clients if needed
                pass
    except WebSocketDisconnect:
        manager.active_connections.pop(client_id, None)
```

**Deliverables:**
- ✓ Complete data flow Quest 2 ↔ Backend
- ✓ Image generation pipeline working
- ✓ Construction plan generation working
- ✓ Real-time design sync (optional)
- ✓ Error handling throughout
- ✓ Loading states and user feedback

---

### Phase 6: PC Viewing Application (Weeks 18-20)

**Simple Web-based Viewer:**

```python
# app/api/v1/viewer.py
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter()

@router.get("/project/{project_id}", response_class=HTMLResponse)
async def view_project(project_id: int):
    # Serve HTML viewer for project
    project = get_project(project_id)
    plan = get_construction_plan(project_id)
    images = get_project_images(project_id)
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{project.name} - Construction Plan</title>
        <style>
            body {{ font-family: Arial; margin: 20px; }}
            .section {{ margin: 30px 0; }}
            .image-gallery {{ display: flex; gap: 20px; }}
            .image-gallery img {{ max-width: 400px; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            th {{ background-color: #4CAF50; color: white; }}
        </style>
    </head>
    <body>
        <h1>{project.name}</h1>
        
        <div class="section">
            <h2>Project Overview</h2>
            <p><strong>Type:</strong> {project.project_type}</p>
            <p><strong>Status:</strong> {project.status}</p>
        </div>
        
        <div class="section">
            <h2>Renderings</h2>
            <div class="image-gallery">
                {''.join(f'<img src="/images/{img.image_path}" alt="{img.image_type}"/>' for img in images)}
            </div>
        </div>
        
        <div class="section">
            <h2>Materials List</h2>
            <table>
                <tr>
                    <th>Material</th>
                    <th>Quantity</th>
                    <th>Unit</th>
                    <th>Unit Cost</th>
                    <th>Total Cost</th>
                </tr>
                {''.join(create_material_row(m) for m in plan.materials)}
            </table>
        </div>
        
        <div class="section">
            <h2>Construction Timeline</h2>
            <table>
                <tr>
                    <th>Phase</th>
                    <th>Task</th>
                    <th>Duration</th>
                    <th>Cost</th>
                </tr>
                {''.join(create_task_row(t) for t in plan.tasks)}
            </table>
        </div>
    </body>
    </html>
    """
```

**Export to PDF:**
```python
# app/services/export_service.py
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

class ExportService:
    
    def generate_pdf_plan(self, project_id: int) -> str:
        project = get_project(project_id)
        plan = get_construction_plan(project_id)
        
        pdf_path = f"exports/project_{project_id}_plan.pdf"
        c = canvas.Canvas(pdf_path, pagesize=letter)
        
        # Title
        c.setFont("Helvetica-Bold", 24)
        c.drawString(1*inch, 10*inch, project.name)
        
        # Materials list
        y = 9*inch
        c.setFont("Helvetica-Bold", 16)
        c.drawString(1*inch, y, "Materials List")
        
        y -= 0.5*inch
        c.setFont("Helvetica", 12)
        for material in plan.materials:
            c.drawString(1*inch, y, 
                f"{material.name}: {material.quantity} {material.unit} @ ${material.cost}")
            y -= 0.3*inch
        
        # Timeline
        # ... similar rendering
        
        c.save()
        return pdf_path
```

**Deliverables:**
- ✓ Web-based project viewer
- ✓ Material list display
- ✓ Timeline visualization
- ✓ PDF export functionality
- ✓ Image gallery view

---

### Phase 7: Testing & Refinement (Weeks 21-24)

**Testing Checklist:**

**Backend Testing:**
```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_create_project():
    response = client.post("/api/v1/projects", json={
        "name": "Test House",
        "project_type": "house"
    })
    assert response.status_code == 200
    assert "id" in response.json()

def test_add_design_element():
    # Create project first
    project = client.post("/api/v1/projects", json={...}).json()
    
    # Add element
    response = client.post("/api/v1/designs/elements", json={
        "project_id": project["id"],
        "element_type": "wall",
        "position_x": 0.0,
        "position_y": 0.0,
        "position_z": 0.0
    })
    assert response.status_code == 200

def test_image_generation():
    # Mock AI service
    response = client.post("/api/v1/ai/images/generate", json={
        "project_id": 1,
        "view_type": "exterior"
    })
    assert response.status_code == 200
    assert "task_id" in response.json()
```

**Quest 2 Testing:**
- Controller input responsiveness
- Element placement accuracy
- Network latency handling
- Memory usage monitoring
- Frame rate stability (90 FPS target)

**Integration Testing:**
- End-to-end design → image flow
- End-to-end design → plan flow
- Data persistence
- Error recovery

**Performance Optimization:**
```python
# Backend optimizations
- Database indexing
- Query optimization
- Caching frequently accessed data
- Async operations for AI calls
- Image compression
```

```cpp
// Quest 2 optimizations
- Level of detail (LOD) for models
- Occlusion culling
- Efficient rendering pipeline
- Memory pooling
- Asset streaming
```

**Deliverables:**
- ✓ All major features tested
- ✓ Bug tracking and fixes
- ✓ Performance benchmarks
- ✓ Documentation updated
- ✓ User testing feedback incorporated

---

## Development Environment Setup Guide

### PC Setup (Ubuntu 24.04)

**1. Install Base Dependencies:**
```bash
#!/bin/bash

# System update
sudo apt update && sudo apt upgrade -y

# Development tools
sudo apt install -y \
    build-essential \
    git \
    curl \
    wget \
    vim \
    python3.11 \
    python3.11-venv \
    python3-pip \
    cmake \
    ninja-build

# Java for Android development
sudo apt install -y default-jdk

# Install Docker and Docker Compose
sudo apt install -y ca-certificates gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group
sudo usermod -aG docker $USER

# Apply group changes (or log out/in)
newgrp docker

# Verify Docker
docker --version
docker compose version

# Install Android Studio
wget https://redirector.gvt1.com/edgedl/android/studio/ide-zips/2023.1.1.28/android-studio-2023.1.1.28-linux.tar.gz
tar -xzf android-studio-*.tar.gz
sudo mv android-studio /opt/
/opt/android-studio/bin/studio.sh  # Run to complete setup
```

**2. Setup PostgreSQL with Docker:**
```bash
# PostgreSQL runs in Docker - no manual installation needed!
# Will be configured via docker-compose.yml in project setup

# Verify Docker is working
docker run hello-world
```

**3. Install ROCm (for AMD GPU):**
```bash
# Add ROCm repository
wget https://repo.radeon.com/rocm/rocm.gpg.key -O - | sudo apt-key add -
echo 'deb [arch=amd64] https://repo.radeon.com/rocm/apt/6.0 ubuntu main' | \
    sudo tee /etc/apt/sources.list.d/rocm.list

sudo apt update
sudo apt install -y rocm-hip-sdk rocm-libs

# Add user to render and video groups
sudo usermod -a -G render,video $USER

# Reboot required
sudo reboot
```

**4. Install AI Models:**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull models (this will take time, ~4-5GB each)
ollama pull llama3.1:8b-instruct-q4_K_M
ollama pull llama3.1:7b  # Alternative smaller model

# Test Ollama
ollama run llama3.1:8b-instruct-q4_K_M "Hello, how are you?"

# Install Python packages for Stable Diffusion
pip install torch torchvision --index-url https://download.pytorch.org/whl/rocm5.7
pip install diffusers transformers accelerate safetensors

# Download Stable Diffusion model (first run will download)
python3 << EOF
from diffusers import StableDiffusionPipeline
model = StableDiffusionPipeline.from_pretrained("stabilityai/stable-diffusion-2-1")
print("Model downloaded successfully")
EOF
```

**5. Setup Python Backend:**
```bash
# Create project directory
mkdir -p ~/vr-construction-platform
cd ~/vr-construction-platform

# Create backend
mkdir backend
cd backend

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Create requirements.txt
cat > requirements.txt << EOF
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
alembic==1.13.1
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0
python-multipart==0.0.6
aiofiles==23.2.1
pillow==10.2.0
numpy==1.26.3
ollama==0.1.6
google-generativeai==0.3.2
torch==2.1.2
torchvision==0.16.2
diffusers==0.25.0
transformers==4.37.0
accelerate==0.26.1
safetensors==0.4.1
reportlab==4.0.9
websockets==12.0
EOF

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << EOF
DATABASE_URL=postgresql://vr_admin:SecurePassword123!@localhost/vr_construction
GEMINI_API_KEY=your_key_here_optional
ENVIRONMENT=development
HOST=0.0.0.0
PORT=8000
EOF

# Initialize Alembic
alembic init alembic
```

**6. Setup Android Development:**
```bash
# Install Android SDK and NDK via Android Studio
# Or via command line:
mkdir -p ~/Android/Sdk
cd ~/Android/Sdk

# Download command line tools
wget https://dl.google.com/android/repository/commandlinetools-linux-9477386_latest.zip
unzip commandlinetools-linux-9477386_latest.zip
mkdir cmdline-tools
mv cmdline-tools latest

# Install SDK components
./cmdline-tools/latest/bin/sdkmanager --licenses
./cmdline-tools/latest/bin/sdkmanager "platform-tools" "platforms;android-33" "build-tools;33.0.2"
./cmdline-tools/latest/bin/sdkmanager "ndk;25.2.9519653" "cmake;3.22.1"

# Set environment variables
echo 'export ANDROID_HOME=$HOME/Android/Sdk' >> ~/.bashrc
echo 'export PATH=$PATH:$ANDROID_HOME/platform-tools' >> ~/.bashrc
source ~/.bashrc

# Test ADB
adb version
```

### Quest 2 Setup

**1. Enable Developer Mode:**
- Install Meta Quest mobile app on phone
- Sign in with Meta/Facebook account
- Go to Menu → Devices → Select your Quest 2
- Tap Developer Mode and toggle ON
- Accept developer agreement

**2. Connect Quest 2:**
```bash
# Connect via USB first
adb devices

# Should show: XXXXXXXX device

# Enable wireless debugging
adb tcpip 5555

# Find Quest IP address (in Quest: Settings → Wi-Fi → Advanced)
# Example: 192.168.1.100

# Connect wirelessly
adb connect 192.168.1.100:5555

# Verify connection
adb devices
# Should show: 192.168.1.100:5555 device
```

**3. Install Oculus SDK:**
```bash
cd ~/Downloads
wget https://securecdn.oculus.com/binaries/download/?id=XXXXXX -O ovr_sdk_mobile.zip
unzip ovr_sdk_mobile.zip -d ~/OculusSDK
```

---

## Network Configuration

**Docker Network Architecture:**

```
Quest 2 (WiFi)
    ↓
Host PC (192.168.1.50)
    ↓
Docker Bridge Network (vr_network)
    ├── vr_postgres (postgres:5432)
    ├── vr_backend (backend:8000) → exposed as localhost:8000
    └── vr_pgadmin (pgadmin:80) → exposed as localhost:5050

Host Services (GPU access):
    ├── Ollama (localhost:11434) → accessible in container as host.docker.internal:11434
    └── Stable Diffusion (Python process)
```

**Backend Server Configuration:**

```python
# app/config.py
from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # Database (Docker container name used internally)
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://vr_admin:SecurePassword123!@postgres:5432/vr_construction"
    )
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    # AI Services (host.docker.internal accesses host machine from container)
    ollama_url: str = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    
    # Storage (inside container)
    upload_dir: str = "/app/uploads"
    generated_images_dir: str = "/app/generated_images"
    exports_dir: str = "/app/exports"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

**Find PC IP Address:**
```bash
# Get local IP (for Quest 2 to connect)
hostname -I | awk '{print $1}'
# Or
ip addr show | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | cut -d/ -f1

# Should show something like: 192.168.1.50
# Your PC IP: 192.168.1.50
```

**Configure Quest 2 to Connect:**
```cpp
// In Quest app, set server IP (same as before - connects to host PC)
const char* SERVER_IP = "192.168.1.50";  // Your PC's local IP
const int SERVER_PORT = 8000;            // Docker exposes this port
```

**Start Backend Server:**
```bash
cd ~/vr-construction-platform/backend

# Start all Docker services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Should see:
# vr_postgres    running
# vr_backend     running (exposed on http://0.0.0.0:8000)
```

**Access Services:**

**From Host PC:**
```bash
# Backend API
curl http://localhost:8000/health

# PostgreSQL
psql -h localhost -U vr_admin -d vr_construction

# Or via Docker
docker compose exec postgres psql -U vr_admin -d vr_construction

# pgAdmin (in browser)
http://localhost:5050
```

**From Quest 2 (or another device on network):**
```bash
# Backend API (use host PC IP)
curl http://192.168.1.50:8000/health
# Should return: {"status":"healthy"}
```

**Docker Network Communication:**
- Containers communicate using service names (e.g., `postgres`, `backend`)
- Host services accessed via `host.docker.internal` from containers
- External access (Quest 2) uses host PC IP address
- Port mappings expose container services to host network

---

## Monitoring & Debugging

**Docker-Based Development Workflow:**

```bash
# Morning routine - start development environment
cd ~/vr-construction-platform/backend
docker compose up -d
docker compose logs -f backend  # Watch logs

# Make code changes
# Changes to ./app/* are automatically synced (hot reload enabled)

# View live logs while developing
docker compose logs -f backend

# Test API changes
curl http://localhost:8000/api/v1/projects

# Database operations
docker compose exec postgres psql -U vr_admin -d vr_construction

# Create new migration after model changes
docker compose exec backend alembic revision --autogenerate -m "add new field"
docker compose exec backend alembic upgrade head

# End of day - stop everything
docker compose down
# Or keep running for next day:
# docker compose stop
```

**Backend Logging:**
```python
# app/main.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

@app.get("/debug/status")
def debug_status():
    return {
        "ollama_running": check_ollama(),
        "postgres_connected": check_database(),
        "gpu_available": torch.cuda.is_available(),
        "models_loaded": list_loaded_models()
    }
```

**Quest 2 Debugging:**
```bash
# View logs in real-time
adb logcat -s VRConstruction:V

# Clear logs
adb logcat -c

# Save logs to file
adb logcat -d > quest_logs.txt
```

**Performance Monitoring:**
```bash
# Monitor GPU usage (on host - AI models)
watch -n 1 rocm-smi

# Monitor Docker containers
docker stats

# Monitor specific container
docker stats vr_backend

# Monitor CPU/RAM on host
htop

# View backend metrics
curl http://localhost:8000/metrics  # Add prometheus metrics if implemented

# Check disk usage
docker system df
```

**Docker Development Best Practices:**

**1. Volume Management:**
- Use named volumes for persistent data (database)
- Use bind mounts for code (hot reload)
- Don't store large AI models in containers

**2. Image Optimization:**
```dockerfile
# Use multi-stage builds for production
FROM python:3.11-slim as builder
# Install dependencies
RUN pip install --user -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /root/.local /root/.local
# Smaller final image
```

**3. Development vs Production:**
```yaml
# docker-compose.dev.yml (with hot reload)
services:
  backend:
    volumes:
      - ./app:/app/app  # Code sync
    command: uvicorn app.main:app --reload

# docker-compose.prod.yml (optimized)
services:
  backend:
    command: gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker
```

**4. Resource Limits:**
```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

**5. Health Checks:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

---

## Future Enhancements (Post-Prototype)

**Phase 2 Features:**
- Multi-user collaboration in VR
- Cloud deployment (AWS/GCP)
- Mobile companion app
- Voice commands in VR
- AR preview mode (Quest 3 passthrough)
- Professional BIM integration
- Real building code validation
- Cost database with real-time pricing
- Contractor marketplace integration

**Scalability & Production:**

**Docker/Container Strategy:**
- Kubernetes orchestration for multi-container deployment
- Separate containers for each microservice:
  - Frontend API service
  - Image generation service (with GPU nodes)
  - Planning/LLM service (with GPU nodes)
  - Database (managed PostgreSQL or RDS)
  - Redis for caching
  - Message queue (RabbitMQ/Kafka)
  - Load balancer (NGINX)
  
**Infrastructure:**
```yaml
# Example production docker-compose.yml structure
services:
  nginx:
    image: nginx:alpine
    depends_on: [api]
    
  api:
    build: ./backend
    replicas: 3  # Horizontal scaling
    
  image_worker:
    build: ./ai-services/image
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
  
  db:
    image: postgres:16
    volumes:
      - db_data:/var/lib/postgresql/data
      
  redis:
    image: redis:alpine
    
  rabbitmq:
    image: rabbitmq:management
```

**Cloud Deployment Options:**
- AWS ECS/EKS with GPU instances (g4dn, p3)
- Google Cloud Run with Cloud SQL
- Azure Container Instances
- Managed PostgreSQL (RDS, Cloud SQL)
- S3/GCS for image storage
- CloudFront/Cloud CDN for assets

**Monitoring & Observability:**
- Prometheus for metrics
- Grafana for dashboards
- ELK stack for log aggregation
- Sentry for error tracking
- Container health checks and auto-restart

**CI/CD Pipeline:**
```yaml
# .github/workflows/deploy.yml
name: Build and Deploy
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Build Docker images
        run: docker compose build
      - name: Run tests
        run: docker compose run backend pytest
      - name: Push to registry
        run: docker push your-registry/vr-backend
```

**Commercial Features:**
- User accounts and authentication
- Project sharing and permissions
- Subscription billing
- Professional rendering quality
- Export to industry formats (Revit, AutoCAD)
- Building permit automation
- 3D printing integration

---

## Troubleshooting

**Common Issues:**

**1. Docker-related Issues:**

**Docker containers won't start:**
```bash
# Check Docker service
sudo systemctl status docker

# Restart Docker
sudo systemctl restart docker

# Check container logs
docker compose logs

# Remove all containers and start fresh
docker compose down
docker compose up -d --build
```

**Permission denied errors:**
```bash
# Add user to docker group (if not done)
sudo usermod -aG docker $USER
newgrp docker

# Or run with sudo (not recommended)
sudo docker compose up -d
```

**Port already in use (5432 or 8000):**
```bash
# Check what's using the port
sudo lsof -i :5432
sudo lsof -i :8000

# Kill the process or change port in docker-compose.yml
# Change "5432:5432" to "5433:5432" for example
```

**2. Quest can't connect to backend:**
```bash
# Check firewall
sudo ufw status
sudo ufw allow 8000/tcp

# Verify Docker container is exposing port
docker compose ps
# Should show: 0.0.0.0:8000->8000/tcp

# Verify server is accessible
curl http://localhost:8000/health

# Check from another device on network
curl http://YOUR_PC_IP:8000/health

# Restart backend container
docker compose restart backend
```

**3. Database connection errors:**
```bash
# Check PostgreSQL container is running
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Test connection from host
psql -h localhost -p 5432 -U vr_admin -d vr_construction

# Test connection from backend container
docker compose exec backend psql -h postgres -U vr_admin -d vr_construction

# Recreate database (WARNING: deletes all data)
docker compose down -v
docker compose up -d
```

**4. Backend container keeps restarting:**
```bash
# Check logs for errors
docker compose logs backend

# Common causes:
# - Database not ready (wait for health check)
# - Syntax error in Python code
# - Missing environment variables

# Enter container to debug
docker compose exec backend bash
python -c "import app; print('OK')"

# Rebuild with fresh install
docker compose down
docker compose build --no-cache backend
docker compose up -d
```

**5. Ollama not responding:**
```bash
# Check Ollama is running on HOST (not in Docker)
systemctl --user status ollama

# Restart Ollama
systemctl --user restart ollama

# Test Ollama
curl http://localhost:11434/api/version

# Test from inside backend container
docker compose exec backend curl http://host.docker.internal:11434/api/version

# Check logs
journalctl --user -u ollama -f
```

**6. ROCm/GPU issues:**
```bash
# Verify ROCm installation (on HOST, not in Docker)
rocm-smi

# Check PyTorch sees GPU (on HOST)
python3 -c "import torch; print(torch.cuda.is_available())"

# Note: AI models run on HOST, not in containers
# GPU not accessible from Docker containers in this setup
```

**7. Can't access generated images or exports:**
```bash
# Check Docker volumes
docker volume ls

# Inspect volume
docker volume inspect backend_generated_images

# Files are stored in Docker volumes
# Access them via container:
docker compose exec backend ls -la /app/generated_images

# Copy files from container to host
docker cp vr_backend:/app/generated_images/image.png ./

# Or mount host directory instead (modify docker-compose.yml):
# volumes:
#   - ./generated_images:/app/generated_images
```

**8. Hot reload not working:**
```bash
# Ensure volume is mounted correctly in docker-compose.yml:
# volumes:
#   - ./app:/app/app

# Restart with rebuild
docker compose up -d --build

# Check if files are syncing
docker compose exec backend ls -la /app/app
```

**9. Database data lost after restart:**
```bash
# Check if volume exists
docker volume ls | grep postgres

# Ensure docker-compose.yml has volume mapping:
# volumes:
#   - postgres_data:/var/lib/postgresql/data

# Backup database
docker compose exec postgres pg_dump -U vr_admin vr_construction > backup.sql

# Restore database
docker compose exec -T postgres psql -U vr_admin vr_construction < backup.sql
```

**10. Memory issues / containers crashing:**
```bash
# Check Docker resource limits
docker stats

# Increase Docker memory (Docker Desktop settings)
# Or add to docker-compose.yml:
# services:
#   backend:
#     mem_limit: 4g

# Free up space
docker system prune -a --volumes  # WARNING: deletes unused containers/volumes
```

**Useful Docker Commands:**

```bash
# View all logs
docker compose logs

# View specific service logs
docker compose logs backend
docker compose logs postgres

# Follow logs in real-time
docker compose logs -f

# Execute command in running container
docker compose exec backend bash
docker compose exec postgres psql -U vr_admin -d vr_construction

# Restart specific service
docker compose restart backend

# Stop all services
docker compose down

# Stop and remove volumes (deletes data)
docker compose down -v

# Rebuild specific service
docker compose build backend
docker compose up -d backend

# View resource usage
docker stats

# Clean up (remove stopped containers, unused images)
docker system prune
```

---

## Documentation & Resources

**Official Documentation:**
- FastAPI: https://fastapi.tiangolo.com/
- Oculus SDK: https://developer.oculus.com/documentation/
- Ollama: https://ollama.ai/
- Stable Diffusion: https://huggingface.co/docs/diffusers/
- PostgreSQL: https://www.postgresql.org/docs/

**Learning Resources:**
- VR Development: https://developer.oculus.com/learn/
- C++ OpenGL: https://learnopengl.com/
- Android NDK: https://developer.android.com/ndk/guides

**Community:**
- Oculus Developer Forums
- FastAPI Discord
- ROCm Community

---

## Project Milestones Summary

**Month 1:**
- ✓ Environment setup complete
- ✓ Database schema implemented
- ✓ Basic backend API functional

**Month 2:**
- ✓ AI integration working
- ✓ Quest 2 app rendering
- ✓ Network communication established

**Month 3:**
- ✓ Design → Image pipeline complete
- ✓ Construction plan generation working
- ✓ Basic VR interactions implemented

**Month 4:**
- ✓ Full integration tested
- ✓ PC viewer functional
- ✓ PDF export working

**Months 5-6:**
- ✓ Polish and refinement
- ✓ User testing
- ✓ Documentation complete
- ✓ Prototype ready for demo

---

## Cost Breakdown (Prototype Phase)

**Hardware (Already Owned):**
- PC with GPU: $0
- Quest 2: $0

**Software (All Free):**
- Ubuntu: Free
- Android Studio: Free
- Docker & Docker Compose: Free
- PostgreSQL: Free
- Python/FastAPI: Free
- Ollama (Local LLM): Free
- Stable Diffusion: Free
- Whisper (Speech-to-Text): Free
- All development tools: Free

**Optional API Costs:**
- Gemini API: Free tier (60 req/min)
- Backup services: $0 (using free tiers)

**Total Prototype Cost: $0**

---

## Quick Reference: Voice-to-Text System

**How to Use Voice Input:**

1. **Activate**: Hold X/A button on Quest 2 controller
2. **Speak**: Speak your request clearly and naturally
3. **Stop**: Release button - audio is sent to backend
4. **Wait**: Text appears in VR dialog (1-2 seconds)
5. **Review**: Read transcribed text, check accuracy
6. **Select Type**: Choose prompt type (Image, Design, Question, Materials, General)
7. **Confirm**: Press trigger to send, grip to cancel
8. **Result**: AI processes and shows result in VR

**Prompt Types Explained:**

**"Image" - Generate visualizations:**
- "A modern house with solar panels and green roof"
- "Exterior view of a colonial style home"
- "Interior of a spacious kitchen with marble countertops"
- Result: AI-generated architectural rendering

**"Design" - Modify your design:**
- "Make the master bedroom 15 feet wide"
- "Add three windows on the south wall"
- "Change the ceiling height to 10 feet"
- Result: Design automatically updated

**"Question" - Get answers:**
- "How much will this cost to build?"
- "What materials do I need for the walls?"
- "How long will construction take?"
- Result: Detailed answer from AI

**"Materials" - Search materials:**
- "What's the best insulation for this climate?"
- "I need drywall for the interior walls"
- "Recommend flooring for the kitchen"
- Result: Material suggestions with prices

**"General" - Let AI decide:**
- "Help me design a garage"
- "What should I do next?"
- "Optimize this layout"
- Result: AI provides guidance or takes action

**Voice Input Tips:**
1. **Speak clearly** - Whisper works best with clear audio
2. **Be specific** - "20 foot wide room" better than "big room"
3. **Natural language** - Speak normally, no special commands needed
4. **Check text** - Always review transcription before sending
5. **Edit if needed** - In future versions, text will be editable
6. **Choose right type** - Helps AI understand your intent
7. **Quiet environment** - Reduces transcription errors

**Common Phrases That Work Well:**

**For Images:**
- "Generate [view type] of [description]"
- "Show me what this looks like from [angle]"
- "Create a rendering with [details]"

**For Design Changes:**
- "Make [element] [measurement] [unit]"
- "Add [number] [element] to [location]"
- "Change [property] to [value]"

**For Questions:**
- "How much [question]?"
- "What [question]?"
- "When [question]?"
- "Why [question]?"

**Troubleshooting Voice Input:**

```bash
# Check backend logs for transcription errors
docker compose logs backend | grep -i "transcr"

# Test transcription accuracy
curl -X POST http://localhost:8000/api/v1/voice/transcribe \
  -F "audio=@my_test.wav"

# Check Whisper model is loaded
docker compose logs backend | grep -i whisper

# Common issues:
# - Background noise → Use quieter environment
# - Mumbling → Speak more clearly
# - Too fast → Speak slower
# - Wrong text → Use edit feature (future) or re-record
```

---

## Quick Reference: Docker Commands

**Daily Development:**
```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f

# Stop everything
docker compose down

# Restart after code changes
docker compose restart backend
```

**Database Operations:**
```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U vr_admin -d vr_construction

# Run SQL file
docker compose exec -T postgres psql -U vr_admin -d vr_construction < schema.sql

# Backup database
docker compose exec postgres pg_dump -U vr_admin vr_construction > backup_$(date +%Y%m%d).sql

# Restore database
docker compose exec -T postgres psql -U vr_admin vr_construction < backup_20240115.sql

# View all tables
docker compose exec postgres psql -U vr_admin -d vr_construction -c "\dt"
```

**Migrations:**
```bash
# Create migration
docker compose exec backend alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec backend alembic upgrade head

# Rollback migration
docker compose exec backend alembic downgrade -1

# View migration history
docker compose exec backend alembic history
```

**Debugging:**
```bash
# Access backend container shell
docker compose exec backend bash

# Access database shell
docker compose exec postgres bash

# View container details
docker inspect vr_backend

# Check resource usage
docker stats

# View container IP
docker inspect vr_backend | grep IPAddress
```

**Cleanup:**
```bash
# Remove stopped containers
docker compose down

# Remove containers and volumes (deletes data!)
docker compose down -v

# Remove all unused Docker resources
docker system prune -a

# Remove specific volume
docker volume rm backend_postgres_data
```

**File Operations:**
```bash
# Copy file from container to host
docker cp vr_backend:/app/generated_images/image.png ./

# Copy file from host to container
docker cp ./config.json vr_backend:/app/

# View files in container
docker compose exec backend ls -la /app/generated_images
```

**Testing:**
```bash
# Run tests in container
docker compose exec backend pytest

# Run specific test
docker compose exec backend pytest tests/test_api.py

# Run with coverage
docker compose exec backend pytest --cov=app
```

---

This comprehensive plan now includes full Docker integration and **Voice-to-Text** system with complete image generation workflow. The setup provides:
- ✅ Containerized PostgreSQL (easy management)
- ✅ Containerized Python backend (consistent environment)
- ✅ AI models on host (GPU access)
- ✅ **Voice-to-Text with Whisper** (hands-free VR input)
- ✅ **Text display in VR** (see what you said)
- ✅ **Multi-purpose AI prompts** (flexible text-based commands)
- ✅ **Image generation from voice** (Stable Diffusion)
- ✅ **Image download and display in VR** (3D floating panels)
- ✅ **Interactive image manipulation** (grab, move, pin)
- ✅ Easy development workflow
- ✅ Production-ready architecture
- ✅ Complete troubleshooting guide

**Complete Voice-to-Image Architecture:**

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         QUEST 2 VR HEADSET                                │
├──────────────────────────────────────────────────────────────────────────┤
│  1. User holds X/A button                                                 │
│  2. Speaks: "dog house made with cedar tongue and groove for GSD"        │
│  3. Audio recorded (MediaRecorder → WAV file)                            │
│  4. Audio sent to PC via HTTP multipart                                  │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ↓ Audio (200KB WAV)
┌──────────────────────────────────────────────────────────────────────────┐
│                      PC BACKEND (Docker + Host)                           │
├──────────────────────────────────────────────────────────────────────────┤
│  5. FastAPI receives audio at /api/v1/voice/transcribe                   │
│  6. Whisper (on host GPU) transcribes audio → text (1-2 sec)            │
│  7. Text returned: "Show me image of dog house made with..."            │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ↓ JSON response with text
┌──────────────────────────────────────────────────────────────────────────┐
│                         QUEST 2 VR HEADSET                                │
├──────────────────────────────────────────────────────────────────────────┤
│  8. Text displayed in floating VR dialog                                  │
│  9. User selects "Image" type                                            │
│  10. User presses trigger to confirm                                     │
│  11. Text sent to /api/v1/voice/prompt with type="image"                │
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ↓ Text prompt + type
┌──────────────────────────────────────────────────────────────────────────┐
│                      PC BACKEND (Docker + Host)                           │
├──────────────────────────────────────────────────────────────────────────┤
│  12. Backend receives prompt                                             │
│  13. Routes to generate_image_from_prompt()                              │
│  14. Enhances prompt: "architectural detailed rendering: dog house..."  │
│  15. Stable Diffusion (on host GPU) generates 768x768 image (15 sec)   │
│  16. Image saved: generated_images/doghouse_1234567890.png              │
│  17. Returns JSON: {"type": "image_generated", "image_url": "/images/..."}│
└──────────────────────────┬───────────────────────────────────────────────┘
                           │
                           ↓ JSON with image URL
┌──────────────────────────────────────────────────────────────────────────┐
│                         QUEST 2 VR HEADSET                                │
├──────────────────────────────────────────────────────────────────────────┤
│  18. Quest receives image URL                                            │
│  19. Downloads PNG via HTTP GET (500KB-2MB)                              │
│  20. Decodes PNG to pixel data                                           │
│  21. Uploads to GPU as OpenGL texture                                    │
│  22. Creates VRImagePanel with texture                                   │
│  23. Displays 2m×2m floating image in VR space                           │
│  24. User can:                                                           │
│      - View from any angle                                               │
│      - Grab and move image                                               │
│      - Zoom in for details                                               │
│      - Pin as reference                                                  │
│      - Generate variations                                               │
└──────────────────────────────────────────────────────────────────────────┘

Total time: ~21 seconds from speaking to viewing image
```

**Key Technologies Used:**
- **Quest 2**: OpenGL ES 3.0, Android MediaRecorder, HTTP client (libcurl)
- **Backend**: FastAPI, Docker, PostgreSQL
- **AI Models**: Whisper (STT), Stable Diffusion (Image Gen), Llama 3.1 (LLM)
- **Image Processing**: stb_image (PNG loading), OpenGL textures
- **Networking**: REST API, multipart file upload, binary download

**What Makes This Unique:**
1. **Fully voice-driven** - Speak naturally, no memorized commands
2. **User verification** - See transcription before sending
3. **Multi-modal AI** - Voice → Text → Images in one workflow
4. **VR-native display** - Images float in 3D space
5. **Interactive results** - Manipulate generated content
6. **Zero API costs** - Everything runs locally
7. **Production-ready** - Docker, GPU acceleration, proper error handling

Good luck with your project! 🚀🐳🎤🖼️