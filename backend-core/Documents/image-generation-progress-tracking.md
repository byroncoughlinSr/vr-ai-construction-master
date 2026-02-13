# Image Generation Progress Tracking Plan

**Document Version:** 1.0  
**Date:** February 7, 2026  
**Status:** Implementation Ready

---

## Executive Summary

This document outlines the plan for implementing real-time progress tracking for AI image generation in the VR Construction project. The system will provide clients with live updates during the image generation process, which can take 30-60 seconds or more depending on quality settings and hardware.

---

## Current State Analysis

### ✅ Existing Infrastructure

#### 1. WebSocket System (`backend-core/backend/app/api/v1/websocket.py`)
The WebSocket infrastructure is **already implemented** with:

- **Progress WebSocket Endpoint**: `/ws/image-progress/{generation_id}`
  - Clients can connect using a generation ID
  - Maintains active connections per generation
  - Handles automatic cleanup

- **Helper Functions**:
  ```python
  async def send_image_progress_update(generation_id: str, progress_data: Dict[str, Any])
  async def complete_image_generation(generation_id: str, result: Dict[str, Any])
  async def fail_image_generation(generation_id: str, error: str)
  ```

- **Progress Storage**:
  ```python
  image_generation_progress: Dict[str, Dict[str, Any]] = {}
  progress_connections: Dict[str, List[WebSocket]] = {}
  ```

- **Test Interface**: `/ws/image-progress/test/{generation_id}` HTML test page

#### 2. Image Generation Service (`backend-core/backend/app/services/ai_image_service.py`)
The service has progress callback support:

- **Progress Callback Parameter**: Already exists in `generate_image()` method
- **Stable Diffusion Callback**: Configured to report step-by-step progress
- **Progress Data Structure**:
  ```python
  {
      "generation_id": generation_id,
      "step": step,
      "total_steps": num_inference_steps,
      "percentage": percentage,
      "status": "generating"
  }
  ```

### ❌ Missing Integration

The **API endpoint** (`backend-core/backend/app/api/v1/ai_image.py`) does NOT currently:
1. Generate unique generation IDs
2. Pass progress callbacks to the image service
3. Trigger WebSocket progress updates
4. Notify clients of completion/errors

---

## Architecture Overview

### Data Flow Diagram

```
Client                    FastAPI API              Image Service           WebSocket
  |                           |                          |                      |
  |--POST /generate--------->|                          |                      |
  |<--{generation_id}---------|                          |                      |
  |                           |                          |                      |
  |--WS Connect---------------|------------------------->|                      |
  |   /image-progress/ID      |                          |                      |
  |                           |                          |                      |
  |                           |--generate_image()------->|                      |
  |                           |  with callback           |                      |
  |                           |                          |                      |
  |                           |                          |--Step 1/50---------->|
  |<--{step:1, progress:2%}---|--------------------------|--------------------- |
  |                           |                          |                      |
  |                           |                          |--Step 25/50--------->|
  |<--{step:25, progress:50%}-|--------------------------|--------------------- |
  |                           |                          |                      |
  |                           |                          |--Complete----------->|
  |<--{status:completed}------|<--return result----------|                      |
  |   with image_url          |                          |                      |
  |                           |                          |                      |
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **API Endpoint** | Generate IDs, coordinate flow, handle HTTP requests |
| **Image Service** | Generate images, report progress via callback |
| **WebSocket Manager** | Broadcast progress to connected clients |
| **Client** | Display progress, handle completion |

---

## Implementation Plan

### Phase 1: API Endpoint Integration

**File:** `backend-core/backend/app/api/v1/ai_image.py`

#### Changes Required:

1. **Add UUID Generation**
   ```python
   import uuid
   from datetime import datetime
   ```

2. **Import WebSocket Functions**
   ```python
   from .websocket import (
       send_image_progress_update,
       complete_image_generation,
       fail_image_generation
   )
   ```

3. **Update `/generate` Endpoint**

   **Before:**
   ```python
   @router.post("/generate")
   async def generate_image(request: ImageGenerationRequest, background_tasks: BackgroundTasks):
       result = await image_service.generate_image(
           prompt=request.prompt,
           # ... other params
       )
       return JSONResponse(status_code=200, content=result)
   ```

   **After:**
   ```python
   @router.post("/generate")
   async def generate_image(request: ImageGenerationRequest, background_tasks: BackgroundTasks):
       # Generate unique ID for tracking
       generation_id = str(uuid.uuid4())
       
       # Define progress callback
       async def progress_callback(progress_data):
           await send_image_progress_update(generation_id, progress_data)
       
       # Start generation with progress tracking
       result = await image_service.generate_image(
           prompt=request.prompt,
           negative_prompt=request.negative_prompt,
           width=request.width,
           height=request.height,
           num_inference_steps=request.num_inference_steps,
           guidance_scale=request.guidance_scale,
           progress_callback=progress_callback,
           generation_id=generation_id
       )
       
       # Notify completion or failure
       if result["success"]:
           await complete_image_generation(generation_id, result)
           result["generation_id"] = generation_id
           return JSONResponse(status_code=200, content=result)
       else:
           await fail_image_generation(generation_id, result.get("error", "Unknown error"))
           raise HTTPException(status_code=500, detail=result.get("error"))
   ```

4. **Update Response Model**
   ```python
   class ImageGenerationResponse(BaseModel):
       generation_id: str
       success: bool
       images: List[dict]
       count: int
       metadata: dict
   ```

### Phase 2: Architectural Visualization Endpoint

**Same changes for `/architectural-visualization`:**

```python
@router.post("/architectural-visualization")
async def generate_architectural_visualization(
    request: ArchitecturalVisualizationRequest,
    background_tasks: BackgroundTasks
):
    generation_id = str(uuid.uuid4())
    
    async def progress_callback(progress_data):
        await send_image_progress_update(generation_id, progress_data)
    
    result = await image_service.generate_architectural_visualization(
        design_description=request.design_description,
        style=request.style,
        time_of_day=request.time_of_day,
        progress_callback=progress_callback,
        generation_id=generation_id
    )
    
    if result["success"]:
        await complete_image_generation(generation_id, result)
        result["generation_id"] = generation_id
        return JSONResponse(status_code=200, content=result)
    else:
        await fail_image_generation(generation_id, result.get("error"))
        raise HTTPException(status_code=500, detail=result.get("error"))
```

### Phase 3: Image Service Updates

**File:** `backend-core/backend/app/services/ai_image_service.py`

The service **already supports** progress callbacks. Verify the callback is properly invoked:

```python
# In generate_image() method, the callback is already configured:
def stable_diffusion_callback(step: int, timestep, latents):
    if progress_callback and generation_id:
        try:
            percentage = int((step / num_inference_steps) * 100)
            asyncio.create_task(
                progress_callback({
                    "generation_id": generation_id,
                    "step": step,
                    "total_steps": num_inference_steps,
                    "percentage": percentage,
                    "status": "generating"
                })
            )
        except Exception as e:
            logger.warning(f"Failed to send progress update: {e}")
```

✅ **No changes needed** - already implemented correctly.

### Phase 4: Voice Integration

**File:** `backend-core/backend/app/api/v1/voice.py`

If voice commands trigger image generation, ensure they also use the progress system:

```python
# When calling image service from voice endpoint
generation_id = str(uuid.uuid4())

async def progress_callback(progress_data):
    await send_image_progress_update(generation_id, progress_data)

result = await image_service.generate_from_voice_input(
    voice_text=transcribed_text,
    progress_callback=progress_callback,
    generation_id=generation_id
)
```

---

## Client-Side Integration

### 1. Vue.js / Quasar Implementation

#### WebSocket Service (`dashboard/src/services/imageProgress.ts`)

```typescript
export interface ImageProgress {
  generation_id: string;
  step: number;
  total_steps: number;
  percentage: number;
  status: 'generating' | 'completed' | 'failed';
}

export class ImageProgressService {
  private ws: WebSocket | null = null;
  private callbacks: Map<string, (progress: ImageProgress) => void> = new Map();

  connect(generationId: string, onProgress: (progress: ImageProgress) => void) {
    const wsUrl = `ws://localhost:8000/api/v1/ws/image-progress/${generationId}`;
    
    this.ws = new WebSocket(wsUrl);
    this.callbacks.set(generationId, onProgress);

    this.ws.onopen = () => {
      console.log(`Connected to progress WebSocket for ${generationId}`);
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      if (data.type === 'progress') {
        onProgress({
          generation_id: data.generation_id,
          step: data.step,
          total_steps: data.total_steps,
          percentage: data.percentage,
          status: 'generating'
        });
      } else if (data.type === 'completed') {
        onProgress({
          ...data.result.metadata,
          status: 'completed'
        });
        this.disconnect();
      } else if (data.type === 'error') {
        onProgress({
          generation_id: data.generation_id,
          step: 0,
          total_steps: 0,
          percentage: 0,
          status: 'failed'
        });
        this.disconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.callbacks.delete(generationId);
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
```

#### Vue Component Example

```vue
<template>
  <div class="image-generator">
    <q-input v-model="prompt" label="Image Prompt" />
    <q-btn @click="generateImage" :loading="isGenerating">
      Generate Image
    </q-btn>

    <!-- Progress Bar -->
    <q-linear-progress 
      v-if="isGenerating"
      :value="progress.percentage / 100"
      color="primary"
      class="q-mt-md"
    >
      <div class="absolute-full flex flex-center">
        <q-badge color="white" text-color="primary">
          {{ progress.step }} / {{ progress.total_steps }} steps ({{ progress.percentage }}%)
        </q-badge>
      </div>
    </q-linear-progress>

    <!-- Generated Image -->
    <q-img 
      v-if="generatedImageUrl"
      :src="generatedImageUrl"
      class="q-mt-md"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { api } from '@/services/api';
import { ImageProgressService } from '@/services/imageProgress';

const prompt = ref('');
const isGenerating = ref(false);
const progress = ref({ step: 0, total_steps: 0, percentage: 0 });
const generatedImageUrl = ref('');

const progressService = new ImageProgressService();

async function generateImage() {
  isGenerating.value = true;
  progress.value = { step: 0, total_steps: 0, percentage: 0 };
  generatedImageUrl.value = '';

  try {
    // Start generation
    const response = await api.post('/api/v1/ai-image/generate', {
      prompt: prompt.value,
      width: 768,
      height: 512,
      num_inference_steps: 50
    });

    const generationId = response.data.generation_id;

    // Connect to progress WebSocket
    progressService.connect(generationId, (progressData) => {
      if (progressData.status === 'generating') {
        progress.value = {
          step: progressData.step,
          total_steps: progressData.total_steps,
          percentage: progressData.percentage
        };
      } else if (progressData.status === 'completed') {
        isGenerating.value = false;
        generatedImageUrl.value = response.data.images[0].image_url;
      } else if (progressData.status === 'failed') {
        isGenerating.value = false;
        // Handle error
      }
    });

  } catch (error) {
    console.error('Generation failed:', error);
    isGenerating.value = false;
  }
}
</script>
```

### 2. React Implementation

```typescript
import { useState, useEffect } from 'react';

function useImageGeneration() {
  const [progress, setProgress] = useState({ step: 0, totalSteps: 0, percentage: 0 });
  const [isGenerating, setIsGenerating] = useState(false);
  const [imageUrl, setImageUrl] = useState('');

  const generateImage = async (prompt: string) => {
    setIsGenerating(true);
    setProgress({ step: 0, totalSteps: 0, percentage: 0 });

    try {
      // Start generation
      const response = await fetch('/api/v1/ai-image/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, width: 768, height: 512, num_inference_steps: 50 })
      });

      const data = await response.json();
      const generationId = data.generation_id;

      // Connect to WebSocket
      const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/image-progress/${generationId}`);

      ws.onmessage = (event) => {
        const progressData = JSON.parse(event.data);

        if (progressData.type === 'progress') {
          setProgress({
            step: progressData.step,
            totalSteps: progressData.total_steps,
            percentage: progressData.percentage
          });
        } else if (progressData.type === 'completed') {
          setIsGenerating(false);
          setImageUrl(data.images[0].image_url);
          ws.close();
        }
      };

    } catch (error) {
      console.error('Generation failed:', error);
      setIsGenerating(false);
    }
  };

  return { generateImage, progress, isGenerating, imageUrl };
}
```

### 3. VR Client (Quest) Integration

For the Android VR app, use WebSocket client in Kotlin:

```kotlin
// File: construction-quest/app/src/main/java/com/byroncoughlin/ImageProgressWebSocket.kt

class ImageProgressWebSocket(private val generationId: String) {
    private var webSocket: WebSocket? = null
    private val client = OkHttpClient()

    fun connect(onProgress: (Int, Int, Int) -> Unit, onComplete: (String) -> Unit) {
        val request = Request.Builder()
            .url("ws://YOUR_SERVER/api/v1/ws/image-progress/$generationId")
            .build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) {
                val json = JSONObject(text)
                when (json.getString("type")) {
                    "progress" -> {
                        val step = json.getInt("step")
                        val totalSteps = json.getInt("total_steps")
                        val percentage = json.getInt("percentage")
                        onProgress(step, totalSteps, percentage)
                    }
                    "completed" -> {
                        val result = json.getJSONObject("result")
                        val imageUrl = result.getJSONArray("images")
                            .getJSONObject(0)
                            .getString("image_url")
                        onComplete(imageUrl)
                    }
                }
            }
        })
    }

    fun disconnect() {
        webSocket?.close(1000, "Completed")
    }
}
```

---

## Testing Strategy

### 1. Unit Tests

Test the progress callback mechanism:

```python
# tests/test_image_progress.py

import pytest
from app.services.ai_image_service import AIImageService

@pytest.mark.asyncio
async def test_progress_callback():
    service = AIImageService()
    progress_updates = []

    async def mock_callback(data):
        progress_updates.append(data)

    await service.generate_image(
        prompt="test house",
        width=512,
        height=512,
        num_inference_steps=5,  # Small number for testing
        progress_callback=mock_callback,
        generation_id="test-123"
    )

    # Verify we received progress updates
    assert len(progress_updates) > 0
    assert all(u["generation_id"] == "test-123" for u in progress_updates)
    assert all(u["status"] == "generating" for u in progress_updates)
```

### 2. Integration Tests

Test the full WebSocket flow:

```python
# tests/test_websocket_progress.py

import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_websocket_progress_connection():
    client = TestClient(app)
    
    with client.websocket_connect("/api/v1/ws/image-progress/test-id") as websocket:
        # Should connect successfully
        data = websocket.receive_json()
        assert data is not None
```

### 3. Manual Testing

1. **Use Built-in Test Page**
   - Navigate to: `http://localhost:8000/api/v1/ws/image-progress/test/YOUR_GEN_ID`
   - Click "Start Image Generation"
   - Observe progress updates in real-time

2. **cURL Testing**
   ```bash
   # Start generation
   curl -X POST http://localhost:8000/api/v1/ai-image/generate \
     -H "Content-Type: application/json" \
     -d '{
       "prompt": "modern house",
       "width": 512,
       "height": 512,
       "num_inference_steps": 20
     }'
   
   # Note the generation_id from response
   # Then connect via WebSocket in browser
   ```

3. **Frontend Testing**
   - Implement the Vue component above
   - Test with various prompts and settings
   - Verify progress bar updates smoothly

---

## Performance Considerations

### 1. WebSocket Connection Limits

- **Issue**: Each client connection consumes server resources
- **Solution**: Implement connection pooling and timeout limits
  ```python
  # In websocket.py, add timeout
  CONNECTION_TIMEOUT = 300  # 5 minutes
  ```

### 2. Progress Update Frequency

- **Issue**: Too frequent updates (every step) may overwhelm clients
- **Solution**: Throttle updates to every N steps
  ```python
  # In ai_image_service.py
  if step % 5 == 0:  # Update every 5 steps
      await progress_callback({...})
  ```

### 3. Memory Management

- **Issue**: Storing progress data for completed generations
- **Solution**: Clean up after completion (already implemented)
  ```python
  # Cleanup happens in complete_image_generation()
  if generation_id in image_generation_progress:
      del image_generation_progress[generation_id]
  ```

### 4. Concurrent Generations

- **Issue**: Multiple users generating images simultaneously
- **Solution**: Each generation has unique ID, no conflicts
- **Monitor**: Use Redis for distributed tracking if scaling horizontally

---

## Error Handling

### Scenarios to Handle

| Scenario | Solution |
|----------|----------|
| WebSocket disconnects during generation | Generation continues; client can reconnect |
| Generation fails mid-process | Call `fail_image_generation()` to notify clients |
| Client never connects to WebSocket | Generation still completes; result in HTTP response |
| Server restart during generation | Generation lost; implement persistence if needed |

### Implementation

```python
# In ai_image.py, wrap generation in try-catch
try:
    result = await image_service.generate_image(...)
    if result["success"]:
        await complete_image_generation(generation_id, result)
    else:
        await fail_image_generation(generation_id, result.get("error"))
except Exception as e:
    logger.error(f"Generation failed: {e}")
    await fail_image_generation(generation_id, str(e))
    raise HTTPException(status_code=500, detail=str(e))
```

---

## Deployment Checklist

- [ ] Update `ai_image.py` with generation ID and WebSocket integration
- [ ] Test locally with built-in test page
- [ ] Update frontend to use WebSocket progress
- [ ] Add monitoring/logging for WebSocket connections
- [ ] Configure CORS for WebSocket connections if needed
- [ ] Add rate limiting for WebSocket connections
- [ ] Document API changes in OpenAPI/Swagger
- [ ] Update client SDK/documentation
- [ ] Load test with concurrent generations
- [ ] Deploy to staging environment
- [ ] Verify in production

---

## API Documentation Updates

### POST `/api/v1/ai-image/generate`

**Response Changes:**

```json
{
  "generation_id": "550e8400-e29b-41d4-a716-446655440000",
  "success": true,
  "images": [...],
  "count": 1,
  "metadata": {...}
}
```

**New Field:**
- `generation_id` (string): UUID for tracking progress via WebSocket

### WebSocket `/api/v1/ws/image-progress/{generation_id}`

**Connection:**
```javascript
const ws = new WebSocket(`ws://localhost:8000/api/v1/ws/image-progress/${generationId}`);
```

**Message Types:**

1. **Progress Update**
   ```json
   {
     "type": "progress",
     "generation_id": "...",
     "step": 25,
     "total_steps": 50,
     "percentage": 50,
     "status": "generating"
   }
   ```

2. **Completion**
   ```json
   {
     "type": "completed",
     "generation_id": "...",
     "status": "completed",
     "result": {
       "success": true,
       "images": [...],
       "metadata": {...}
     },
     "timestamp": "2026-02-07T14:10:00Z"
   }
   ```

3. **Error**
   ```json
   {
     "type": "error",
     "generation_id": "...",
     "status": "failed",
     "error": "CUDA out of memory",
     "timestamp": "2026-02-07T14:10:00Z"
   }
   ```

---

## Future Enhancements

### 1. Queue System
If multiple users generate images, implement job queue:
- Use Celery or Redis Queue
- Show queue position to users
- Estimate wait time

### 2. Progress Estimation
Add time remaining estimates:
```python
{
  "step": 25,
  "total_steps": 50,
  "percentage": 50,
  "estimated_seconds_remaining": 15
}
```

### 3. Multiple Image Previews
Generate low-res previews during generation:
- Send preview at 25%, 50%, 75%
- Allows users to cancel early if not satisfied

### 4. Persistent Progress
Save progress to database:
- Allows reconnecting after disconnect
- Historical tracking of generations
- Analytics on generation times

### 5. WebSocket Authentication
Add JWT token validation:
```python
@router.websocket("/image-progress/{generation_id}")
async def image_progress_websocket(
    websocket: WebSocket,
    generation_id: str,
    token: str = Query(...)
):
    # Validate JWT token
    user = await verify_token(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
```

---

## Conclusion

The infrastructure for real-time image generation progress tracking is **90% complete**. The main task is to integrate the existing WebSocket system with the image generation API endpoints by:

1. Adding generation ID creation
2. Passing progress callbacks
3. Handling completion/error notifications

This will provide users with real-time feedback during the 30-60 second image generation process, significantly improving user experience.

---

## References

- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- Stable Diffusion Callbacks: https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion
- WebSocket Protocol: RFC 6455
- Vue WebSocket Integration: https://socket.io/docs/v4/client-initialization/

---

**Next Steps:** Toggle to ACT mode and implement Phase 1 changes to `ai_image.py`.
