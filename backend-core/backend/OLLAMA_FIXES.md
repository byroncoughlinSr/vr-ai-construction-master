# Ollama Memory Issues and Fixes

## Problem Summary
The Ollama llama runner was being killed due to Out-of-Memory (OOM) issues, causing project generation to fail. The Gemini fallback was also not working properly due to incorrect exception handling.

## Fixes Applied

### 1. AI Planning Service Improvements (`ai_planning_service.py`)

#### Fixed Gemini Fallback Logic
- **Before**: Exception was re-raised after logging, preventing Gemini fallback
- **After**: Proper error capture and fallback chain:
  1. Try Ollama first
  2. If Ollama fails, try Gemini
  3. If both fail, raise appropriate error

#### Reduced Memory Footprint
- Reduced `num_ctx` from 8192 to 4096 tokens (50% reduction)
- Reduced `num_predict` from 4096 to 2048 tokens (50% reduction)
- Added `num_thread: 4` to limit CPU thread usage
- Added 60-second timeout for generation requests
- Added 15-second timeout for name generation

#### Async Execution Improvements
- Moved Ollama calls to executor to prevent blocking
- Added proper timeout handling with `asyncio.wait_for()`
- Better error messages for timeout vs other failures

### 2. Docker Configuration (`docker-compose.yml`)

#### Added Memory Limits to Ollama Container
```yaml
deploy:
  resources:
    limits:
      memory: 8G  # Maximum memory allocation
    reservations:
      memory: 4G  # Minimum reserved memory
```

#### Added Ollama Environment Variables
```yaml
environment:
  - OLLAMA_NUM_PARALLEL=1  # Process one request at a time
  - OLLAMA_MAX_LOADED_MODELS=1  # Only keep one model in memory
```

These settings prevent:
- Multiple concurrent requests from overwhelming memory
- Multiple models being loaded simultaneously
- System-wide memory exhaustion

## Setting Up Gemini API (Optional but Recommended)

To enable Gemini as a fallback when Ollama fails:

### 1. Get a Gemini API Key
1. Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the API key

### 2. Add to Environment File

Create or edit `.env` file in `backend-core/backend/`:

```bash
# AI Services
OLLAMA_URL=http://ollama:11434
GEMINI_API_KEY=your_api_key_here
```

### 3. Restart the Backend Service

```bash
cd backend-core/backend
docker-compose down backend
docker-compose up -d backend
```

### 4. Verify Gemini is Active

Check the backend logs:
```bash
docker logs vr_backend_dev | grep Gemini
```

You should see: `Gemini API initialized`

## Testing the Fixes

### 1. Restart All Services
```bash
cd backend-core/backend
docker-compose down
docker-compose up -d
```

### 2. Monitor Ollama Memory Usage
```bash
# In a separate terminal
docker stats vr_ollama_dev
```

### 3. Test Project Generation
Use the API or dashboard to create a new project. Monitor the logs:

```bash
docker logs -f vr_backend_dev
```

Expected behavior:
- Ollama should complete successfully (without being killed)
- If Ollama fails, Gemini should be attempted automatically
- Clear error messages if both fail

## Memory Usage Comparison

| Configuration | Context Window | Max Tokens | Memory Usage | Risk Level |
|--------------|----------------|------------|--------------|------------|
| **Before**   | 8192          | 4096       | ~6-8 GB      | High (OOM) |
| **After**    | 4096          | 2048       | ~3-4 GB      | Low        |

## Troubleshooting

### Ollama Still Being Killed

1. Check available system memory:
   ```bash
   free -h
   ```

2. Reduce memory limits if needed:
   - Edit `docker-compose.yml`
   - Reduce `limits.memory` to 6G or 4G
   - Further reduce `num_ctx` to 2048 in `ai_planning_service.py`

3. Switch to smaller model:
   ```bash
   docker exec -it vr_ollama_dev ollama pull llama3.1:8b
   ```
   Then update model name in `ai_planning_service.py`

### Gemini Fallback Not Working

1. Verify API key is set:
   ```bash
   docker exec vr_backend_dev env | grep GEMINI
   ```

2. Check for API quota/billing issues at [Google Cloud Console](https://console.cloud.google.com/)

3. Verify logs show Gemini initialization:
   ```bash
   docker logs vr_backend_dev | grep -i gemini
   ```

### Both Services Failing

1. Check if models are corrupted:
   ```bash
   docker exec -it vr_ollama_dev ollama list
   ```

2. Re-pull the model:
   ```bash
   docker exec -it vr_ollama_dev ollama pull llama3.1:latest
   ```

3. Restart services:
   ```bash
   docker-compose restart ollama backend
   ```

## Performance Notes

- Generation time may be slightly longer due to smaller token limits
- Quality should remain similar as context is sufficient for construction planning
- Timeout of 60 seconds should be adequate for most requests
- Gemini API has rate limits (60 requests/minute on free tier)

## Future Improvements

1. **Model Selection**: Add configuration to choose between different Ollama models
2. **Retry Logic**: Implement exponential backoff for transient failures
3. **Caching**: Cache common responses to reduce AI service load
4. **Monitoring**: Add metrics for AI service success rates and response times
5. **Load Balancing**: Distribute requests across multiple Ollama instances
