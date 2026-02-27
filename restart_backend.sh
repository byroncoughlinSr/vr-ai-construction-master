#!/bin/bash
# Restart Backend Server Script

echo "🔄 Restarting VR AI Construction Backend..."
echo ""

# Kill existing uvicorn processes and anything on port 8000
echo "1. Stopping existing backend process..."
pkill -9 -f "uvicorn app.main" 2>/dev/null
kill -9 $(lsof -ti:8000) 2>/dev/null
echo "   ✓ Cleared port 8000"

# Wait a moment for processes to fully terminate
sleep 2

# Change to backend directory
cd /development/vr-ai-construction-project/backend-core/backend

# Check if we're in the right directory
if [ ! -f "app/main.py" ]; then
    echo "❌ Error: Could not find app/main.py"
    echo "   Current directory: $(pwd)"
    exit 1
fi

echo "2. Activating virtual environment..."
source venv/bin/activate

echo "3. Starting backend server..."
echo "   Host: 0.0.0.0"
echo "   Port: 8000"
echo "   Auto-reload: enabled"
echo ""
echo "✅ Backend starting..."
echo "   Press Ctrl+C to stop"
echo ""

# Start the backend using python module syntax
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
