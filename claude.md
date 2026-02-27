# Dashboard Retry Button & VR Auto-Load Removal

## Overview
This document details the implementation changes to modify the retry button behavior in the dashboard HomeView to load selected projects into VR, and remove automatic project loading from the VR application.

**Date:** February 26, 2026  
**Task:** Change retry button to load current project into VR via backend, generating image and VR geometry. Remove VR auto-load functionality.

---

## Changes Summary

### 1. Dashboard Changes (HomeView.vue)
- **Modify retry button** to load the current/selected project into VR
- Use `currentProject.id` from the projects store
- Call new backend endpoint to generate image and VR geometry
- Track progress via WebSocket

### 2. VR Changes (ImmersiveActivity.kt)
- **Remove auto-load on startup** (line ~952)
- **Remove Button B handler** for loading latest project (line ~817)
- **Rename `loadLatestProject()`** to `loadProjectById(projectId: Int)`
- Load specific projects by ID instead of fetching "latest"

### 3. Backend Changes (projects.py)
- **Add new endpoint:** `POST /api/v1/projects/{project_id}/load-to-vr`
- Generate architectural visualization image (background)
- Prepare VR geometry data
- Return generation_id for WebSocket progress tracking

---

## Detailed Implementation

### Backend Implementation

#### File: `backend-core/backend/app/api/v1/projects.py`

Add new endpoint after the existing `generate_vr_geometry` endpoint:

```python
@router.post("/{project_id}/load-to-vr")
async def load_project_to_vr(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Load an existing project into VR with image generation.
    
    This endpoint:
    1. Validates the project exists
    2. Starts background image generation with WebSocket progress
    3. Prepares VR geometry (already available via /generate-vr)
    4. Returns generation_id for tracking
    
    Use WebSocket /api/v1/ws/image-progress/{generation_id} for progress updates.
    """
    logger.info(f"🎮 Load-to-VR requested for project {project_id}")
    
    # Validate project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    logger.info(f"📦 Project found: '{project.name}' (id={project_id})")
    
    try:
        # Generate unique ID for image generation tracking
        generation_id = str(uuid.uuid4())
        
        # Get project description for image generation
        project_description = project.description or project.name
        
        # Start background image generation
        async def background_image_generation():
            try:
                logger.info(f"🖼️ Starting image generation for project {project_id}")
                
                # Progress callback for WebSocket updates
                async def progress_callback(progress_data):
                    await send_image_progress_update(generation_id, progress_data)
                
                # Generate architectural visualization
                result = await image_service.generate_architectural_visualization(
                    design_description=project_description,
                    style="modern",
                    time_of_day="day",
                    progress_callback=progress_callback,
                    generation_id=generation_id
                )
                
                if result["success"]:
                    await complete_image_generation(generation_id, result)
                    logger.info(f"✅ Image generation completed for project {project_id}")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    await fail_image_generation(generation_id, error_msg)
                    logger.error(f"❌ Image generation failed: {error_msg}")
                    
            except Exception as e:
                logger.error(f"❌ Background image generation error: {e}", exc_info=True)
                await fail_image_generation(generation_id, str(e))
        
        # Start background task
        asyncio.create_task(background_image_generation())
        
        # Return response immediately
        return JSONResponse(
            status_code=202,  # Accepted - processing in background
            content={
                "success": True,
                "project_id": project_id,
                "project_name": project.name,
                "generation_id": generation_id,
                "status": "processing",
                "message": "Project loading to VR initiated. Image generation in progress.",
                "websocket_url": f"/api/v1/ws/image-progress/{generation_id}",
                "vr_geometry_url": f"/api/v1/projects/{project_id}/generate-vr"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Load-to-VR failed for project {project_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load project to VR: {str(e)}"
        )
```

**Required imports to add at the top of the file:**
```python
import uuid
import asyncio
from fastapi import BackgroundTasks
from ..services import AIImageService
from .websocket import send_image_progress_update, complete_image_generation, fail_image_generation

# Add to existing instantiations
image_service = AIImageService()
```

---

### Dashboard Implementation

#### File: `backend-core/dashboard/src/views/HomeView.vue`

**1. Add new method in the `<script setup>` section:**

```typescript
const loadProjectToVR = async (): Promise<void> => {
  const projectId = projectsStore.currentProject?.id
  
  if (!projectId) {
    $q.notify({
      type: 'warning',
      message: 'No project selected',
      caption: 'Please select a project first'
    })
    return
  }
  
  loading.value = true
  loadingMessage.value = 'Loading project into VR...'
  
  try {
    // Call backend to initiate VR load with image generation
    const response = await apiClient.post(`/projects/${projectId}/load-to-vr`)
    
    const { generation_id, websocket_url, project_name } = response
    
    $q.notify({
      type: 'positive',
      message: `Loading "${project_name}" into VR`,
      caption: 'Image generation in progress...',
      timeout: 3000
    })
    
    // Optional: Connect to WebSocket for real-time progress
    // You can use the existing imageProgress service if needed
    // connectImageProgress(generation_id)
    
    logger.info(`✅ Project ${projectId} load initiated, generation_id: ${generation_id}`)
    
  } catch (err) {
    error.value = (err as Error).message
    $q.notify({
      type: 'negative',
      message: 'Failed to load project to VR',
      caption: (err as Error).message
    })
    logger.error('Load to VR failed:', err)
  } finally {
    loading.value = false
  }
}
```

**2. Update the retry button in the template:**

Find the error banner section with the retry button and update it:

```vue
<!-- Error State -->
<div v-else-if="error" class="q-pa-md">
  <q-banner class="bg-negative text-white">
    <template v-slot:avatar>
      <q-icon name="error" />
    </template>
    {{ error }}
    <template v-slot:action>
      <q-btn flat label="Retry" @click="refreshData" />
      <q-btn flat label="Load to VR" @click="loadProjectToVR" icon="view_in_ar" />
    </template>
  </q-banner>
</div>
```

**Alternative: Replace retry button entirely:**

```vue
<template v-slot:action>
  <q-btn flat label="Load to VR" @click="loadProjectToVR" icon="view_in_ar" />
</template>
```

**3. Optional: Add a dedicated "Load to VR" button in the header:**

```vue
<div class="col-auto">
  <q-btn
    color="primary"
    label="Refresh"
    icon="refresh"
    @click="refreshData"
    :loading="loading"
    class="q-mr-sm"
  />
  <q-btn
    color="secondary"
    label="Load to VR"
    icon="view_in_ar"
    @click="loadProjectToVR"
    :loading="loading"
    :disable="!project"
  />
</div>
```

---

### VR Implementation

#### File: `construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ImmersiveActivity.kt`

**Change 1: Remove auto-load on startup (line ~952)**

Find this code in `onSceneReady()`:
```kotlin
// Auto-load the most recent project on startup (recovers missed generations)
android.os.Handler(Looper.getMainLooper()).postDelayed({ loadLatestProject() }, 2000)
```

**DELETE or comment out these lines:**
```kotlin
// ❌ REMOVED: Auto-load on startup
// android.os.Handler(Looper.getMainLooper()).postDelayed({ loadLatestProject() }, 2000)
```

**Change 2: Remove Button B handler for loading latest project (line ~817)**

Find this code in `processRightController()`:
```kotlin
// IDLE: B = reload last project (recovery if headset slept during generation)
if (state.buttonB && !locomotionEnabled && (now - buttonBDebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
    buttonBDebounceTimer = now
    Log.i(TAG, "🔃 Button B in IDLE — loading latest project")
    loadLatestProject()
}
```

**DELETE or comment out this entire block:**
```kotlin
// ❌ REMOVED: Button B auto-load functionality
// if (state.buttonB && !locomotionEnabled && ...) {
//     loadLatestProject()
// }
```

**Change 3: Rename and modify loadLatestProject() method**

Find the `loadLatestProject()` method and replace it with:

```kotlin
/**
 * Load a specific project by ID from the backend and display its VR geometry.
 * Safe to call from UI or background threads.
 * 
 * @param projectId The database ID of the project to load
 */
fun loadProjectById(projectId: Int) {
    if (locomotionEnabled) {
        Log.i(TAG, "⏭️ loadProjectById($projectId) skipped — house already loaded")
        return
    }
    Log.i(TAG, "🔃 Loading project $projectId from backend…")
    activityScope.launch(Dispatchers.IO) {
        try {
            // Fetch VR geometry for the specific project
            val geometry = houseGenerator?.fetchVRGeometry(projectId)
            if (geometry != null) {
                runOnUiThread {
                    val spawnPos = houseGenerator?.buildFromGeometry(geometry)
                    if (spawnPos != null) {
                        scene.setViewOrigin(spawnPos.x, 0f, spawnPos.z, 0f)
                        Log.i(TAG, "🧍 Spawned at (${spawnPos.x}, ${spawnPos.z})")
                    }
                    locomotionEnabled = true
                    voiceState = VoiceState.IDLE
                    
                    val projectName = geometry.optString("project_name", "Project $projectId")
                    Log.i(TAG, "✅ Project loaded: '$projectName' (id=$projectId)")
                }
            } else {
                Log.w(TAG, "⚠️ fetchVRGeometry returned null for project $projectId")
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ loadProjectById($projectId) failed", e)
        }
    }
}
```

**Change 4: Update HouseGenerator.kt (if needed)**

The `fetchVRGeometry()` method in HouseGenerator already takes a projectId parameter, so no changes needed there. It's already implemented correctly.

**Optional Change: Add WebSocket listener for dashboard load requests**

If you want VR to automatically load projects when the dashboard triggers it, add a WebSocket message handler:

```kotlin
private fun connectToRoom(roomId: String, userId: String) {
    val request = Request.Builder()
        .url("$WS_URL/room/$roomId?user_id=$userId")
        .build()

    roomWebSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
        // ... existing code ...
        
        override fun onMessage(webSocket: WebSocket, text: String) {
            try {
                val json = JSONObject(text)
                val type = json.optString("type")
                
                // NEW: Handle load-to-vr requests from dashboard
                if (type == "load_to_vr") {
                    val projectId = json.optInt("project_id", -1)
                    if (projectId != -1) {
                        Log.i(TAG, "📡 Dashboard requested load for project $projectId")
                        runOnUiThread { loadProjectById(projectId) }
                    }
                } else if (type == "design_update") {
                    handleRemoteDesignUpdate(json)
                } else if (type == "user_joined") {
                    Log.i(TAG, "👥 User joined: ${json.optString("user_id")}")
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ Failed to parse WS message", e)
            }
        }
    })
}
```

---

## Testing Checklist

### Backend Testing
- [ ] Backend endpoint responds correctly: `POST /api/v1/projects/{project_id}/load-to-vr`
- [ ] Returns 404 for non-existent project IDs
- [ ] Returns 202 with generation_id for valid projects
- [ ] Image generation starts in background
- [ ] WebSocket sends progress updates
- [ ] VR geometry endpoint still works: `GET /api/v1/projects/{project_id}/generate-vr`

### Dashboard Testing
- [ ] Retry button calls `loadProjectToVR()` method
- [ ] Shows notification when no project is selected
- [ ] Shows success notification when request succeeds
- [ ] Shows error notification when request fails
- [ ] Loading state is displayed during operation
- [ ] Can track image generation progress via WebSocket (optional)

### VR Testing
- [ ] VR app does NOT auto-load project on startup
- [ ] Button B does NOT trigger project loading
- [ ] `loadProjectById(projectId)` correctly loads specific projects
- [ ] VR geometry renders correctly for loaded projects
- [ ] Player spawns at correct position
- [ ] Locomotion is enabled after project loads
- [ ] Multiple projects can be loaded sequentially (after clearing)

### Integration Testing
- [ ] Dashboard → Backend → VR flow works end-to-end
- [ ] Image generates correctly for existing projects
- [ ] VR geometry is prepared and accessible
- [ ] WebSocket progress updates work correctly
- [ ] Error handling works at each layer

---

## API Endpoints Reference

### New Endpoint
```
POST /api/v1/projects/{project_id}/load-to-vr
```

**Request:** No body required, project_id in URL

**Response (202 Accepted):**
```json
{
  "success": true,
  "project_id": 123,
  "project_name": "Modern House",
  "generation_id": "uuid-here",
  "status": "processing",
  "message": "Project loading to VR initiated. Image generation in progress.",
  "websocket_url": "/api/v1/ws/image-progress/uuid-here",
  "vr_geometry_url": "/api/v1/projects/123/generate-vr"
}
```

### Existing Endpoints (Still Used)
```
GET /api/v1/projects/{project_id}/generate-vr
```
Returns VR geometry JSON for Quest to render.

```
WS /api/v1/ws/image-progress/{generation_id}
```
WebSocket for real-time image generation progress.

### Deprecated Endpoint
```
GET /api/v1/projects/latest
```
**Status:** No longer used by VR  
**Reason:** VR loads specific projects by ID instead of "latest"  
**Keep or Remove:** Can keep for backward compatibility, but VR won't call it

---

## Communication Flow

### Dashboard Retry Button Flow
```
1. User clicks "Load to VR" button in HomeView
2. Dashboard gets currentProject.id from store
3. Dashboard → Backend: POST /projects/{id}/load-to-vr
4. Backend validates project exists
5. Backend starts async image generation (with WebSocket updates)
6. Backend returns generation_id immediately (202)
7. Dashboard shows "Loading..." notification
8. [Optional] Dashboard connects to WebSocket for progress
9. VR can fetch geometry at any time via /generate-vr endpoint
```

### VR Loading Flow (Manual)
```
1. VR app launches (NO auto-load)
2. User triggers project load (via dashboard, or future VR UI)
3. VR calls loadProjectById(projectId)
4. VR → Backend: GET /projects/{id}/generate-vr
5. Backend returns VR geometry JSON
6. VR builds entities from geometry
7. VR enables locomotion and spawns player
```

### VR Loading Flow (With WebSocket - Optional)
```
1. Dashboard clicks "Load to VR"
2. Backend sends WebSocket message: {"type": "load_to_vr", "project_id": 123}
3. VR receives WebSocket message
4. VR automatically calls loadProjectById(123)
5. Rest follows manual flow above
```

---

## Files Modified

### Backend
- ✅ `backend-core/backend/app/api/v1/projects.py` - Added `load_to_vr` endpoint

### Dashboard
- ✅ `backend-core/dashboard/src/views/HomeView.vue` - Modified retry button behavior

### VR
- ✅ `construction-quest/app/src/main/java/com/byroncoughlin/vr_construction_quest/ImmersiveActivity.kt`
  - Removed auto-load on startup
  - Removed Button B load handler
  - Renamed `loadLatestProject()` → `loadProjectById(projectId)`

---

## Migration Notes

### For Existing Projects
- All existing projects remain compatible
- Can be loaded via new load-to-vr endpoint
- VR geometry generation still works as before
- Image generation will run when projects are loaded to VR

### For Development
- Update VR app build and redeploy to Quest
- Backend change is backward compatible
- Dashboard change improves UX with explicit "Load to VR" action

### For Users
- VR app no longer auto-loads on startup (intentional)
- Users explicitly control when projects load via dashboard
- Better control over VR experience
- Can still generate new projects via voice commands

---

## Troubleshooting

### Issue: Backend returns 404 for project
**Solution:** Verify project exists in database: `SELECT * FROM projects WHERE id = {project_id}`

### Issue: Image generation doesn't start
**Solution:** Check AIImageService initialization and logs. Verify Stable Diffusion model is loaded.

### Issue: VR doesn't load project
**Solution:** 
1. Check VR logs for errors
2. Verify network connectivity to backend
3. Ensure `/generate-vr` endpoint returns valid JSON
4. Check that `loadProjectById()` is called with valid ID

### Issue: WebSocket connection fails
**Solution:** Verify WebSocket endpoint is accessible, check CORS settings, ensure generation_id is valid.

---

## Future Enhancements

### Possible Additions
1. **Dashboard Project Selector**: Dropdown to select which project to load
2. **VR UI**: In-VR menu to browse and load projects
3. **Batch Loading**: Load multiple projects into different VR zones
4. **Auto-Sync**: VR polls backend for load requests (polling approach)
5. **Deep Links**: Dashboard opens Quest app with deep link to load specific project

### Scalability Considerations
- Add rate limiting to load-to-vr endpoint
- Cache VR geometry for frequently loaded projects
- Optimize image generation queue for multiple concurrent requests
- Add project load history tracking

---

## Summary

This implementation provides clean separation of concerns:
- **Dashboard** controls project selection and load initiation
- **Backend** handles image generation and geometry preparation
- **VR** loads specific projects on demand without auto-loading

The retry button now has a clear purpose: Load the current project into VR with full image generation and geometry. No more mysterious auto-loads or button B shortcuts.

**Result:** More predictable, user-controlled VR experience with proper dashboard integration.
