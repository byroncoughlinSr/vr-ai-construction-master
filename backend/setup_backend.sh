#!/bin/bash

echo "🔧 Setting up VR Construction Backend"
echo "======================================"

cd ~/vr-construction-platform/backend

# Backup old requirements if exists
if [ -f requirements.txt ]; then
    cp requirements.txt requirements.txt.backup.$(date +%Y%m%d_%H%M%S)
    echo "✅ Backed up old requirements.txt"
fi

# Create clean requirements.txt
cat > requirements.txt << 'EOF'
# Web Framework
fastapi==0.109.0
uvicorn[standard]==0.27.0
slowapi==0.1.9

# Database
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
alembic==1.13.1

# Data Validation
pydantic==2.5.3
pydantic-settings==2.1.0
python-dotenv==1.0.0

# File Handling
python-multipart==0.0.6
aiofiles==23.2.1

# Image Processing
pillow==10.2.0
numpy==1.26.3

# AI/ML Core
torch==2.1.2
torchaudio==2.1.2
torchvision==0.16.2

# AI Models
transformers==4.45.0
diffusers==0.30.0
accelerate==0.34.0
safetensors==0.4.5

# LLM Clients
ollama==0.1.6
google-generativeai==0.3.2

# Voice Processing
faster-whisper==1.0.0
ffmpeg-python==0.2.0

# Documents
reportlab==4.0.9

# Network
websockets==12.0
httpx==0.25.2

# Testing
pytest==7.4.4
pytest-asyncio==0.23.2
pytest-cov==4.1.0

# Monitoring
python-json-logger==2.0.7
prometheus-client==0.19.0
sentry-sdk[fastapi]==1.39.1
EOF

echo "✅ Created clean requirements.txt"

# Check for duplicates
echo ""
echo "🔍 Checking for duplicates..."
DUPES=$(sort requirements.txt | uniq -d)
if [ -z "$DUPES" ]; then
    echo "✅ No duplicates found"
else
    echo "⚠️  Duplicates found:"
    echo "$DUPES"
fi

# Rebuild Docker
echo ""
echo "🐳 Rebuilding Docker containers..."
docker compose down
docker compose build --no-cache backend

# Start services
echo ""
echo "🚀 Starting services..."
docker compose up -d

# Wait for startup
echo "⏳ Waiting for services to start..."
sleep 5

# Check health
echo ""
echo "🏥 Health check..."
curl -s http://localhost:8000/health | python3 -m json.tool

# Check voice service
echo ""
echo "🎙️ Voice service check..."
curl -s http://localhost:8000/api/v1/voice/status | python3 -m json.tool

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "  1. Test transcription: curl -X POST http://localhost:8000/api/v1/voice/transcribe -F 'audio_file=@test.wav'"
echo "  2. View logs: docker compose logs -f backend"
echo "  3. Deploy to Quest: ./gradlew installDebug"