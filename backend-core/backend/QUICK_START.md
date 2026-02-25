# 🚀 Quick Start - Native Ollama Migration

## ⚡ 5-Minute Setup

Your Ollama was being killed by OOM (Out of Memory). This fixes it by moving Ollama from Docker to native.

### 1️⃣ Install Native Ollama
```bash
curl -fsSL https://ollama.com/install.sh | sh
sudo systemctl start ollama
sudo systemctl enable ollama
```

### 2️⃣ Pull the 8B Model (IMPORTANT!)
```bash
# Use ONLY the 8B model (NOT "latest")
ollama pull llama3.1:8b

# Verify
ollama list
```

### 3️⃣ Update Environment
```bash
cd /development/vr-ai-construction-project/backend-core/backend

# If you don't have .env yet:
cp .env.example .env

# If you have .env, edit it:
nano .env
# Make sure OLLAMA_URL=http://172.17.0.1:11434
```

### 4️⃣ Restart Services
```bash
# Stop old Docker Ollama
docker-compose down

# Restart with new config
docker-compose up -d

# Check logs
docker logs -f vr_backend_dev
# Look for: "✅ Ollama service is available"
```

### 5️⃣ Test It
```bash
# Test Ollama directly
curl http://localhost:11434/api/tags

# Test from backend
docker exec vr_backend_dev curl http://172.17.0.1:11434/api/tags
```

## ✅ Success!

If you see "Ollama service is available" in logs, you're done!

## 🆘 Quick Fixes

**Backend can't connect to Ollama?**
```bash
# Check Ollama is running
sudo systemctl status ollama

# Check Docker bridge IP
ip addr show docker0 | grep inet
# Use that IP in .env as OLLAMA_URL
```

**Still running out of memory?**
```bash
# Add Gemini API fallback (free)
# Get key: https://makersuite.google.com/app/apikey
# Add to .env: GEMINI_API_KEY=your_key_here
```

## 📖 Full Documentation

See `NATIVE_OLLAMA_SETUP.md` for complete guide with troubleshooting.

## 🎯 What Changed

- ❌ Removed Docker Ollama container (was using 8GB, causing OOM)
- ✅ Using native Ollama with 8B model (only 4-5GB)
- ✅ Backend connects via Docker bridge IP (172.17.0.1)
- ✅ Added optional Gemini fallback support

**Result**: No more "signal: killed" errors! 🎉
