package com.byroncoughlin.vr_construction_quest

import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.os.Looper
import android.util.Log
import android.webkit.WebView
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.meta.spatial.castinputforward.CastInputForwardFeature
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector3
import com.meta.spatial.okhttp3.OkHttpAssetFetcher
import com.meta.spatial.runtime.NetworkedAssetLoader
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

// Define ControllerState OUTSIDE the activity (top-level or before activity)
data class ControllerState(
    var buttonA: Boolean = false,
    var buttonB: Boolean = false,
    var buttonX: Boolean = false,
    var buttonY: Boolean = false,
    var trigger: Boolean = false,
    var grip: Boolean = false,
    var pose: Pose = Pose()
)

class ImmersiveActivity : AppSystemActivity() {
    private val activityScope = CoroutineScope(Dispatchers.Main)
    private val nativeEntities = mutableMapOf<Int, Entity>()
    private var voiceController: VoiceController? = null
    private val httpClient = OkHttpClient()
    private var currentMaterial = "Wood"
    private var isRecording = false
    private var broadcastReceiver: BroadcastReceiver? = null
    private var isInitialized = false

    // Voice indicator entity
    private var voiceIndicator: Entity? = null

    companion object {
        private const val TAG = "ImmersiveActivity"

        init {
            System.loadLibrary("vr_construction_quest")
        }

        // Controller Button Masks (SDK 0.9.2)
        const val BUTTON_A = 0x00000001L
        const val BUTTON_B = 0x00000002L
        const val BUTTON_X = 0x00000100L
        const val BUTTON_Y = 0x00000200L
        const val TRIGGER_MASK = 0x20000000L
        const val GRIP_MASK = 0x04000000L

        // Hand indices
        const val HAND_LEFT = 0
        const val HAND_RIGHT = 1
    }

    // Native JNI Methods
    external fun initNative()
    external fun nativeAddElement(type: Int, x: Float, y: Float, z: Float, dx: Float, dy: Float, dz: Float): Int
    external fun nativeUpdateElement(id: Int, x: Float, y: Float, z: Float, dx: Float, dy: Float, dz: Float): Boolean
    external fun nativeRemoveElement(id: Int): Boolean
    external fun nativeRaycast(ox: Float, oy: Float, oz: Float, dx: Float, dy: Float, dz: Float): Int
    external fun nativeGetElementData(id: Int): FloatArray?
    external fun nativeSnapToGrid(x: Float, y: Float, z: Float, gridSize: Float): FloatArray?
    external fun nativePushAudio(audioData: ShortArray, size: Int)
    external fun nativeFinishRecording()
    external fun nativeGetControllerButtonState(hand: Int): Long
    external fun nativeGetControllerPose(hand: Int): FloatArray?

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(
            VRFeature(this),
            CastInputForwardFeature(this)
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (isInitialized) {
            Log.w(TAG, "Activity already initialized, skipping duplicate initialization")
            return
        }

        try {
            Log.i(TAG, "Starting onCreate initialization")

            // Initialize asset loader
            try {
                NetworkedAssetLoader.init(
                    File(applicationContext.cacheDir.canonicalPath),
                    OkHttpAssetFetcher()
                )
                Log.i(TAG, "Asset loader initialized")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to initialize asset loader", e)
                throw e
            }

            // Initialize native layer
            try {
                initNative()
                Log.i(TAG, "Native layer initialized")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to initialize native layer", e)
                throw e
            }

            // Initialize voice controller
            try {
                voiceController = VoiceController()
                Log.i(TAG, "Voice controller initialized")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to initialize voice controller", e)
                // Non-critical, continue
            }

            // Register construction systems
            try {
                systemManager.registerSystem(ConstructionInputSystem())
                Log.i(TAG, "ConstructionInputSystem registered successfully")
            } catch (e: IllegalArgumentException) {
                Log.w(TAG, "System already registered, skipping: ${e.message}")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to register ConstructionInputSystem", e)
                throw e
            }

            // Register broadcast for material changes
            try {
                broadcastReceiver = object : BroadcastReceiver() {
                    override fun onReceive(context: Context, intent: Intent) {
                        currentMaterial = intent.getStringExtra("selectedMaterial") ?: "Wood"
                        Log.i(TAG, "Material changed to: $currentMaterial")
                    }
                }
                val filter = IntentFilter("com.byroncoughlin.CHANGE_MATERIAL")
                val receiverFlags = ContextCompat.RECEIVER_NOT_EXPORTED
                ContextCompat.registerReceiver(
                    this,
                    broadcastReceiver,
                    filter,
                    receiverFlags
                )
                Log.i(TAG, "Broadcast receiver registered")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to register broadcast receiver", e)
                // Non-critical, continue
            }

            isInitialized = true
            Log.i(TAG, "onCreate completed successfully")

        } catch (e: Exception) {
            Log.e(TAG, "Critical error in onCreate", e)
            isInitialized = false
            throw e
        }
    }

    override fun onDestroy() {
        Log.i(TAG, "onDestroy called")

        try {
            // Stop any active recording
            if (isRecording) {
                voiceController?.stopRecording()
                isRecording = false
            }

            // Clean up voice controller
            voiceController = null

            // Unregister broadcast receiver
            broadcastReceiver?.let {
                try {
                    unregisterReceiver(it)
                    Log.i(TAG, "Broadcast receiver unregistered")
                } catch (e: Exception) {
                    Log.w(TAG, "Error unregistering receiver", e)
                }
            }
            broadcastReceiver = null

            // Destroy voice indicator
            try {
                voiceIndicator?.destroy()
                voiceIndicator = null
            } catch (e: Exception) {
                Log.w(TAG, "Error destroying voice indicator", e)
            }

            // Clean up all entities
            try {
                nativeEntities.values.forEach { entity ->
                    try {
                        entity.destroy()
                    } catch (e: Exception) {
                        Log.w(TAG, "Error destroying entity", e)
                    }
                }
                nativeEntities.clear()
                Log.i(TAG, "All entities cleaned up")
            } catch (e: Exception) {
                Log.e(TAG, "Error cleaning up entities", e)
            }

            isInitialized = false
            Log.i(TAG, "Activity cleanup complete")

        } catch (e: Exception) {
            Log.e(TAG, "Error in onDestroy", e)
        } finally {
            super.onDestroy()
        }
    }

    // ========================================================================
    // SCENE SETUP
    // ========================================================================

    override fun onSceneReady() {
        super.onSceneReady()

        try {
            Log.i(TAG, "Scene ready - setting up environment")

            // Setup lighting environment
            scene.setLightingEnvironment(
                ambientColor = Vector3(0.3f, 0.3f, 0.3f),
                sunColor = Vector3(7.0f, 7.0f, 7.0f),
                sunDirection = -Vector3(1.0f, 3.0f, -2.0f),
                environmentIntensity = 0.3f
            )

            scene.updateIBLEnvironment("environment.env")
            scene.setViewOrigin(0.0f, 0.0f, 2.0f, 180.0f)

            // Create skybox
            val skybox = Entity.create()
            skybox.setComponent(Transform(Pose(t = Vector3(0f, 0f, 0f))))
            skybox.setComponent(Mesh(mesh = "mesh://skybox".toUri()))
            skybox.setComponent(Material().apply {
                baseTextureAndroidResourceId = R.drawable.skydome
                unlit = true
            })
            skybox.setComponent(Visible(true))
            Log.i(TAG, "Skybox created")

            // CRITICAL: Delay entity creation by one frame to ensure MeshCreationSystem is ready
            android.os.Handler(Looper.getMainLooper()).postDelayed({
                try {
                    setupInitialConstruction()
                    Log.i(TAG, "Initial construction setup complete")
                } catch (e: Exception) {
                    Log.e(TAG, "Error in delayed setupInitialConstruction", e)
                }
            }, 100) // 100ms delay to ensure everything is ready

            Log.i(TAG, "Scene setup initiated")
        } catch (e: Exception) {
            Log.e(TAG, "Error in onSceneReady", e)
        }
    }

    // ========================================================================
    // AI & NETWORK LOGIC
    // ========================================================================

    fun onNativePostAudio(audioData: ShortArray) {
        activityScope.launch(Dispatchers.IO) {
            try {
                val byteBuffer = ByteBuffer.allocate(audioData.size * 2)
                    .order(ByteOrder.LITTLE_ENDIAN)
                audioData.forEach { byteBuffer.putShort(it) }

                val requestBody = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(
                        "audio",
                        "command.raw",
                        byteBuffer.array().toRequestBody("audio/raw".toMediaType())
                    )
                    .build()

                val request = Request.Builder()
                    .url("http://192.168.1.50:8000/api/v1/voice/transcribe")
                    .post(requestBody)
                    .build()

                httpClient.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        val result = response.body?.string() ?: "{}"
                        processAICommand(JSONObject(result))
                    } else {
                        Log.e(TAG, "Transcription failed: ${response.code}")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "AI request failed", e)
            }
        }
    }

    private fun processAICommand(json: JSONObject) {
        activityScope.launch(Dispatchers.Main) {
            try {
                val action = json.optString("action")
                val params = json.optJSONObject("params") ?: return@launch

                when (action) {
                    "ADD_WALL" -> {
                        val x = params.optDouble("x", 0.0).toFloat()
                        val y = params.optDouble("y", 1.5).toFloat()
                        val z = params.optDouble("z", -2.0).toFloat()
                        val w = params.optDouble("w", 2.0).toFloat()
                        val h = params.optDouble("h", 3.0).toFloat()
                        val d = params.optDouble("d", 0.2).toFloat()

                        val newId = nativeAddElement(0, x, y, z, w, h, d)
                        createEntityForElement(newId, x, y, z, w, h, d)
                    }
                    "CHANGE_MATERIAL" -> {
                        currentMaterial = params.optString("material", "Wood")
                        Log.i(TAG, "Material changed to: $currentMaterial")
                    }
                    else -> {
                        Log.w(TAG, "Unknown action: $action")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing AI command", e)
            }
        }
    }

    fun onNativeSyncProject(jsonStr: String) {
        activityScope.launch(Dispatchers.IO) {
            try {
                val request = Request.Builder()
                    .url("http://192.168.1.50:8000/api/v1/projects/sync")
                    .post(jsonStr.toRequestBody("application/json".toMediaType()))
                    .build()

                httpClient.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        Log.i(TAG, "Project synced successfully")
                    } else {
                        Log.e(TAG, "Sync failed: ${response.code}")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Sync request failed", e)
            }
        }
    }

    // ========================================================================
    // DIRECT CONTROLLER INPUT SYSTEM
    // ========================================================================

    inner class ConstructionInputSystem : SystemBase() {
        // Controller states (using top-level ControllerState class)
        private val leftController = ControllerState()
        private val rightController = ControllerState()

        // Interaction state
        private var grabbedElementId = -1
        private var grabOffset = Vector3(0f)

        override fun execute() {
            try {
                // Update controller states directly from native code
                updateControllerState(HAND_LEFT, leftController)
                updateControllerState(HAND_RIGHT, rightController)

                // Process each controller
                processLeftController()
                processRightController()
            } catch (e: Exception) {
                Log.e(TAG, "Error in ConstructionInputSystem.execute", e)
            }
        }

        private fun updateControllerState(hand: Int, state: ControllerState) {
            try {
                // Get button state from native
                val buttonState = nativeGetControllerButtonState(hand)

                // Update button states
                state.buttonA = (buttonState and BUTTON_A) != 0L
                state.buttonB = (buttonState and BUTTON_B) != 0L
                state.buttonX = (buttonState and BUTTON_X) != 0L
                state.buttonY = (buttonState and BUTTON_Y) != 0L
                state.trigger = (buttonState and TRIGGER_MASK) != 0L
                state.grip = (buttonState and GRIP_MASK) != 0L

                // Get pose from native
                val poseData = nativeGetControllerPose(hand)
                if (poseData != null && poseData.size >= 7) {
                    state.pose = Pose(
                        t = Vector3(poseData[0], poseData[1], poseData[2]),
                        q = Quaternion(poseData[3], poseData[4], poseData[5], poseData[6])
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error updating controller state for hand $hand", e)
            }
        }

        private fun processLeftController() {
            try {
                // Left controller: Grab and move elements
                handleGrabAndMove(leftController)

                // X button: Delete element
                if (leftController.buttonX) {
                    handleDeletion(leftController.pose)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing left controller", e)
            }
        }

        private fun processRightController() {
            try {
                // Right controller: Voice input
                handleVoiceInput(rightController)

                // Trigger: Place new elements
                if (rightController.trigger) {
                    handlePlacement(rightController.pose)
                }

                // B button: Also delete (alternative)
                if (rightController.buttonB) {
                    handleDeletion(rightController.pose)
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error processing right controller", e)
            }
        }

        private fun handleVoiceInput(controller: ControllerState) {
            // A button for voice recording (push-to-talk)
            if (controller.buttonA && !isRecording) {
                voiceController?.startRecording()
                isRecording = true
                showVoiceIndicator(controller.pose, true)
                Log.i(TAG, "🎤 Started recording")
            } else if (!controller.buttonA && isRecording) {
                voiceController?.stopRecording()
                isRecording = false
                showVoiceIndicator(controller.pose, false)
                Log.i(TAG, "🎤 Stopped recording")
            }

            // Update voice indicator position if recording
            if (isRecording) {
                updateVoiceIndicator(controller.pose)
            }
        }

        private fun handleGrabAndMove(controller: ControllerState) {
            val gripPressed = controller.grip
            val pose = controller.pose

            // Grip just pressed - start grab
            if (gripPressed && grabbedElementId == -1) {
                val origin = pose.t
                val forward = pose.q * Vector3(0f, 0f, -1f)

                grabbedElementId = nativeRaycast(
                    origin.x, origin.y, origin.z,
                    forward.x, forward.y, forward.z
                )

                if (grabbedElementId != -1) {
                    Log.i(TAG, "✊ Grabbed element $grabbedElementId")
                    highlightElement(grabbedElementId, true)

                    // Calculate grab offset
                    val elementData = nativeGetElementData(grabbedElementId)
                    if (elementData != null && elementData.size >= 3) {
                        grabOffset = Vector3(
                            elementData[0] - origin.x,
                            elementData[1] - origin.y,
                            elementData[2] - origin.z
                        )
                    }
                }
            }
            // Grip released - drop element
            else if (!gripPressed && grabbedElementId != -1) {
                Log.i(TAG, "🤚 Released element $grabbedElementId")
                highlightElement(grabbedElementId, false)
                grabbedElementId = -1
            }
            // Grip held - move element
            else if (gripPressed && grabbedElementId != -1) {
                moveGrabbedElement(pose)
            }
        }

        private fun moveGrabbedElement(pose: Pose) {
            val origin = pose.t
            val forward = pose.q * Vector3(0f, 0f, -1f)
            val targetPos = origin + forward * 3.0f + grabOffset

            // Snap to grid
            val snapped = nativeSnapToGrid(targetPos.x, targetPos.y, targetPos.z, 0.5f)

            if (snapped != null) {
                val currentData = nativeGetElementData(grabbedElementId) ?: return

                // Update native element
                nativeUpdateElement(
                    grabbedElementId,
                    snapped[0], snapped[1], snapped[2],
                    currentData[3], currentData[4], currentData[5]
                )

                // Update visual entity
                nativeEntities[grabbedElementId]?.setComponent(
                    Transform(Pose(
                        t = Vector3(snapped[0], snapped[1], snapped[2])
                    ))
                )
            }
        }

        private fun handlePlacement(pose: Pose) {
            val origin = pose.t
            val forward = pose.q * Vector3(0f, 0f, -1f)

            // Check if pointing at floor (downward)
            if (forward.y < -0.5f) {
                // Cast ray to floor
                val t = -origin.y / forward.y
                if (t > 0) {
                    val floorX = origin.x + forward.x * t
                    val floorZ = origin.z + forward.z * t

                    val snapped = nativeSnapToGrid(floorX, 0f, floorZ, 0.5f)

                    if (snapped != null) {
                        // Place wall at floor position
                        val newId = nativeAddElement(
                            0, // Wall type
                            snapped[0], 1.5f, snapped[2],
                            0.2f, 3f, 2.0f
                        )
                        createEntityForElement(newId, snapped[0], 1.5f, snapped[2], 0.2f, 3f, 2.0f)
                        Log.i(TAG, "📦 Placed wall at (${snapped[0]}, ${snapped[2]})")
                    }
                }
            }
        }

        private fun handleDeletion(pose: Pose) {
            val origin = pose.t
            val forward = pose.q * Vector3(0f, 0f, -1f)

            val hitId = nativeRaycast(
                origin.x, origin.y, origin.z,
                forward.x, forward.y, forward.z
            )

            if (hitId != -1) {
                if (nativeRemoveElement(hitId)) {
                    Log.i(TAG, "🗑️ Deleted element $hitId")
                    nativeEntities[hitId]?.destroy()
                    nativeEntities.remove(hitId)
                }
            }
        }
    }

    // ========================================================================
    // HELPER METHODS
    // ========================================================================
/**
    private fun setupInitialConstruction() {
        try {
            // Create floor
            val floorId = nativeAddElement(1, 0f, 0f, -5f, 10f, 0.1f, 10f)
            createEntityForElement(floorId, 0f, 0f, -5f, 10f, 0.1f, 10f)
            Log.i(TAG, "Initial floor created")
        } catch (e: Exception) {
            Log.e(TAG, "Error in setupInitialConstruction", e)
        }
    }
    **/

private fun setupInitialConstruction() {
    try {
        // Create floor
        val floorId = nativeAddElement(1, 0f, 0f, -5f, 10f, 0.1f, 10f)
        createEntityForElement(floorId, 0f, 0f, -5f, 10f, 0.1f, 10f)
        Log.i(TAG, "Initial floor created")
    } catch (e: Exception) {
        Log.e(TAG, "Error in setupInitialConstruction", e)
    }
}

    private fun createEntityForElement(
        id: Int,
        x: Float, y: Float, z: Float,
        dx: Float, dy: Float, dz: Float
    ) {
        try {
            // Create entity with Box component (the correct way for box meshes)
            val entity = Entity.create(
                listOf(
                    Transform(Pose(t = Vector3(x, y, z))),
                    com.meta.spatial.toolkit.Box(Vector3(dx, dy, dz)),
                    Material().apply {
                        baseTextureAndroidResourceId = getMaterialTexture(currentMaterial)
                        unlit = false
                    },
                    Grabbable(),
                    Visible(true)
                )
            )
            nativeEntities[id] = entity
            Log.i(TAG, "Created entity for element $id using Box component")
        } catch (e: Exception) {
            Log.e(TAG, "Error creating entity for element $id", e)
        }
    }

    private fun getMaterialTexture(material: String): Int {
        return when (material) {
            "Wood" -> R.drawable.skydome
            "Concrete" -> R.drawable.skydome
            "Steel" -> R.drawable.skydome
            "Brick" -> R.drawable.skydome
            "Glass" -> R.drawable.skydome
            else -> R.drawable.skydome
        }
    }

    private fun highlightElement(elementId: Int, highlight: Boolean) {
        try {
            nativeEntities[elementId]?.let { entity ->
                val material = entity.tryGetComponent<Material>()
                if (material != null) {
                    material.unlit = highlight
                    entity.setComponent(material)
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error highlighting element $elementId", e)
        }
    }

    private fun showVoiceIndicator(pose: Pose, show: Boolean) {
        try {
            if (show) {
                voiceIndicator = Entity.create()
                voiceIndicator?.setComponent(
                    Transform(Pose(
                        t = pose.t + pose.q * Vector3(0.1f, 0.05f, -0.2f)
                    ))
                )
                voiceIndicator?.setComponent(Mesh(mesh = "mesh://sphere".toUri()))
                voiceIndicator?.setComponent(Material().apply {
                    baseColor = Color4(1f, 0f, 0f, 1f)
                    unlit = true
                })
                voiceIndicator?.setComponent(Visible(true))
                Log.i(TAG, "🔴 Voice indicator shown")
            } else {
                voiceIndicator?.destroy()
                voiceIndicator = null
                Log.i(TAG, "⚫ Voice indicator hidden")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error showing/hiding voice indicator", e)
        }
    }

    private fun updateVoiceIndicator(pose: Pose) {
        try {
            voiceIndicator?.setComponent(
                Transform(Pose(
                    t = pose.t + pose.q * Vector3(0.1f, 0.05f, -0.2f)
                ))
            )
        } catch (e: Exception) {
            Log.e(TAG, "Error updating voice indicator", e)
        }
    }

    // ========================================================================
    // VOICE CONTROLLER
    // ========================================================================

    inner class VoiceController {
        private var audioRecord: AudioRecord? = null
        private var isRecording = false
        private var recordingThread: Thread? = null
        private val sampleRate = 16000
        private val channelConfig = AudioFormat.CHANNEL_IN_MONO
        private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        private val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

        @SuppressLint("MissingPermission")
        fun startRecording() {
            if (isRecording) return

            try {
                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
                )

                audioRecord?.startRecording()
                isRecording = true

                recordingThread = Thread {
                    val audioData = ShortArray(bufferSize)
                    while (isRecording) {
                        val readSize = audioRecord?.read(audioData, 0, bufferSize) ?: 0
                        if (readSize > 0) {
                            nativePushAudio(audioData, readSize)
                        }
                    }
                }
                recordingThread?.start()

                Log.i(TAG, "Recording started")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start recording", e)
            }
        }

        fun stopRecording() {
            if (!isRecording) return

            try {
                isRecording = false
                audioRecord?.stop()
                audioRecord?.release()
                audioRecord = null
                recordingThread?.join()
                nativeFinishRecording()

                Log.i(TAG, "Recording stopped")
            } catch (e: Exception) {
                Log.e(TAG, "Error stopping recording", e)
            }
        }
    }

    // ========================================================================
    // PANEL REGISTRATION
    // ========================================================================

    override fun registerPanels(): List<PanelRegistration> {
        return try {
            listOf(
                PanelRegistration(R.layout.ui_example) {
                    config {
                        width = 1.2f
                        height = 0.8f
                        layoutDpi = 400
                    }
                    panel {
                        rootView?.findViewById<WebView>(R.id.web_view)?.apply {
                            settings.javaScriptEnabled = true
                            loadUrl("http://192.168.1.50:9000")
                        }
                    }
                }
            )
        } catch (e: Exception) {
            Log.e(TAG, "Error registering panels", e)
            emptyList()
        }
    }
}