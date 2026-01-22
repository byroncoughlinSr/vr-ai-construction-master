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
import com.meta.spatial.toolkit.AvatarAttachment
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.SceneObjectSystem
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.LocomotionSystem
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

class ImmersiveActivity : AppSystemActivity() {
    private val activityScope = CoroutineScope(Dispatchers.Main)
    private val nativeEntities = mutableMapOf<Int, Entity>()
    private var voiceController: VoiceController? = null
    private val httpClient = OkHttpClient()
    private var currentMaterial = "Wood"
    private var isRecording = false

    companion object {
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

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(
            VRFeature(this),
            CastInputForwardFeature(this)
        )
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize asset loader
        NetworkedAssetLoader.init(
            File(applicationContext.cacheDir.canonicalPath),
            OkHttpAssetFetcher()
        )

        // Initialize native layer
        initNative()

        // Initialize voice controller
        voiceController = VoiceController()

        // Register construction input system
        systemManager.registerSystem(ConstructionInputSystem())

        // Setup initial construction scene
        setupInitialConstruction()

        // Register broadcast for material changes
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                currentMaterial = intent.getStringExtra("selectedMaterial") ?: "Wood"
                Log.i("Construction", "Material changed to: $currentMaterial")
            }
        }
        val filter = IntentFilter("com.byroncoughlin.CHANGE_MATERIAL")
        ContextCompat.registerReceiver(
            this,
            receiver,
            filter,
            ContextCompat.RECEIVER_NOT_EXPORTED
        )
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
                        Log.e("AI", "Transcription failed: ${response.code}")
                    }
                }
            } catch (e: Exception) {
                Log.e("AI", "AI request failed", e)
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
                        Log.i("AI", "Material changed to: $currentMaterial")
                    }
                    else -> {
                        Log.w("AI", "Unknown action: $action")
                    }
                }
            } catch (e: Exception) {
                Log.e("AI", "Error processing AI command", e)
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
                        Log.i("Network", "Project synced successfully")
                    } else {
                        Log.e("Network", "Sync failed: ${response.code}")
                    }
                }
            } catch (e: Exception) {
                Log.e("Network", "Sync request failed", e)
            }
        }
    }

    // ========================================================================
    // INPUT SYSTEM (SDK 0.9.2 Compatible)
    // ========================================================================

    inner class ConstructionInputSystem : SystemBase() {
        // State tracking
        private var isAPressed = false
        private var isBPressed = false
        private var isXPressed = false
        private var gripWasPressed = false
        private var triggerWasPressed = false

        // Grabbed element
        private var grabbedElementId = -1
        private var grabOffset = Vector3(0f)

        override fun execute() {
            // Reverting to the old way for now until I find the correct 0.9.2 query API
        }

        private fun processControllerInput(entity: Entity, handType: String) {
            val transform = entity.tryGetComponent<Transform>() ?: return
            val pose = transform.transform
            handleInput(entity, pose, handType)
        }

        private fun handleInput(entity: Entity, pose: Pose, handType: String) {
            val buttonState = getControllerButtonState(handType)

            // Voice Input (A Button - Right Hand)
            if (handType == "hand_right") {
                val aPressed = (buttonState and BUTTON_A) != 0L

                if (aPressed && !isAPressed) {
                    voiceController?.startRecording()
                    isRecording = true
                    showVoiceIndicator(entity, true)
                    Log.i("Input", "🎤 Started recording")
                    isAPressed = true
                } else if (!aPressed && isAPressed) {
                    voiceController?.stopRecording()
                    isRecording = false
                    showVoiceIndicator(entity, false)
                    Log.i("Input", "🎤 Stopped recording")
                    isAPressed = false
                }
            }

            // Grab & Move (Grip Button)
            val gripPressed = (buttonState and GRIP_MASK) != 0L

            if (gripPressed && !gripWasPressed) {
                val origin = pose.t
                val forward = pose.q * Vector3(0f, 0f, -1f)

                grabbedElementId = nativeRaycast(
                    origin.x, origin.y, origin.z,
                    forward.x, forward.y, forward.z
                )

                if (grabbedElementId != -1) {
                    Log.i("Input", "Grabbed element $grabbedElementId")
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
            } else if (!gripPressed && gripWasPressed) {
                if (grabbedElementId != -1) {
                    Log.i("Input", "Released element $grabbedElementId")
                    highlightElement(grabbedElementId, false)
                    grabbedElementId = -1
                }
            }

            gripWasPressed = gripPressed

            // Update grabbed element position
            if (grabbedElementId != -1 && gripPressed) {
                handleMovement(grabbedElementId, pose)
            }

            // Placement (Trigger)
            val triggerPressed = (buttonState and TRIGGER_MASK) != 0L

            if (triggerPressed && !triggerWasPressed) {
                handlePlacement(pose)
            }

            triggerWasPressed = triggerPressed

            // Deletion (B or X Button)
            val bPressed = (buttonState and BUTTON_B) != 0L
            val xPressed = (buttonState and BUTTON_X) != 0L

            if ((bPressed && !isBPressed) || (xPressed && !isXPressed)) {
                handleDeletion(pose)
            }

            isBPressed = bPressed
            isXPressed = xPressed
        }

        private fun handleMovement(id: Int, pose: Pose) {
            val origin = pose.t
            val forward = pose.q * Vector3(0f, 0f, -1f)
            val targetPos = origin + forward * 3.0f + grabOffset

            val snapped = nativeSnapToGrid(targetPos.x, targetPos.y, targetPos.z, 0.5f)

            if (snapped != null) {
                val currentData = nativeGetElementData(id) ?: return

                nativeUpdateElement(
                    id,
                    snapped[0], snapped[1], snapped[2],
                    currentData[3], currentData[4], currentData[5]
                )

                val visualEntity = nativeEntities[id]
                visualEntity?.setComponent(
                    Transform(Pose(
                        t = Vector3(snapped[0], snapped[1], snapped[2])
                    ))
                )
            }
        }

        private fun handlePlacement(pose: Pose) {
            val origin = pose.t
            val forward = pose.q * Vector3(0f, 0f, -1f)

            // Check if pointing at floor
            val hitId = nativeRaycast(origin.x, origin.y, origin.z, forward.x, forward.y, forward.z)

            if (hitId == -1 && forward.y < -0.5f) {
                // Cast ray to floor
                val t = -origin.y / forward.y
                val floorX = origin.x + forward.x * t
                val floorZ = origin.z + forward.z * t

                val snapped = nativeSnapToGrid(floorX, 0f, floorZ, 0.5f)

                if (snapped != null) {
                    // Place wall
                    val newId = nativeAddElement(
                        0, // Wall type
                        snapped[0], 1.5f, snapped[2],
                        0.2f, 3f, 2.0f
                    )
                    createEntityForElement(newId, snapped[0], 1.5f, snapped[2], 0.2f, 3f, 2.0f)
                    Log.i("Input", "Placed wall at (${snapped[0]}, ${snapped[2]})")
                }
            }
        }

        private fun handleDeletion(pose: Pose) {
            val origin = pose.t
            val forward = pose.q * Vector3(0f, 0f, -1f)

            val hitId = nativeRaycast(origin.x, origin.y, origin.z, forward.x, forward.y, forward.z)

            if (hitId != -1) {
                if (nativeRemoveElement(hitId)) {
                    Log.i("Input", "Deleted element $hitId")
                    nativeEntities[hitId]?.destroy()
                    nativeEntities.remove(hitId)
                }
            }
        }

        private fun getControllerButtonState(handType: String): Long {
            return 0L
        }
    }

    // ========================================================================
    // HELPER METHODS
    // ========================================================================

    private fun setupInitialConstruction() {
        // Create floor
        val floorId = nativeAddElement(1, 0f, 0f, -5f, 10f, 0.1f, 10f)
        createEntityForElement(floorId, 0f, 0f, -5f, 10f, 0.1f, 10f)
        Log.i("Construction", "Initial floor created")
    }

    private fun createEntityForElement(
        id: Int,
        x: Float, y: Float, z: Float,
        dx: Float, dy: Float, dz: Float
    ) {
        // Create entity with all components
        val entity = Entity.create()

        // Set transform
        entity.setComponent(Transform(Pose(t = Vector3(x, y, z))))

        // Set mesh (box)
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))

        // Set material
        entity.setComponent(Material().apply {
            baseTextureAndroidResourceId = getMaterialTexture(currentMaterial)
            unlit = false
        })

        // Make grabbable
        entity.setComponent(Grabbable())

        // Make visible
        entity.setComponent(Visible(true))

        // Store reference
        nativeEntities[id] = entity

        Log.i("Construction", "Created entity for element $id")
    }

    private fun getMaterialTexture(material: String): Int {
        return when (material) {
            "Wood" -> R.drawable.skydome // Placeholder
            "Concrete" -> R.drawable.skydome // Placeholder
            "Steel" -> R.drawable.skydome // Placeholder
            "Brick" -> R.drawable.skydome // Placeholder
            "Glass" -> R.drawable.skydome // Placeholder
            else -> R.drawable.skydome
        }
    }

    private fun highlightElement(elementId: Int, highlight: Boolean) {
        nativeEntities[elementId]?.let { entity ->
            val material = entity.tryGetComponent<Material>()
            if (material != null) {
                material.unlit = highlight
                entity.setComponent(material)
            }
        }
    }

    private fun showVoiceIndicator(entity: Entity, show: Boolean) {
        // Create/destroy voice indicator sphere
        if (show) {
            val indicator = Entity.create()
            indicator.setComponent(Transform(Pose(t = Vector3(0.1f, 0.05f, -0.1f))))
            indicator.setComponent(Mesh(mesh = "mesh://sphere".toUri()))
            indicator.setComponent(Material().apply {
                baseColor = Color4(1f, 0f, 0f, 1f) // Red
                unlit = true
            })
            indicator.setComponent(Visible(true))
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

                Log.i("Voice", "Recording started")
            } catch (e: Exception) {
                Log.e("Voice", "Failed to start recording", e)
            }
        }

        fun stopRecording() {
            if (!isRecording) return

            isRecording = false
            audioRecord?.stop()
            audioRecord?.release()
            audioRecord = null
            recordingThread?.join()
            nativeFinishRecording()

            Log.i("Voice", "Recording stopped")
        }
    }

    // ========================================================================
    // SCENE SETUP
    // ========================================================================

    override fun onSceneReady() {
        super.onSceneReady()

        // Set lighting
        scene.setLightingEnvironment(
            ambientColor = Vector3(0.3f, 0.3f, 0.3f),
            sunColor = Vector3(7.0f, 7.0f, 7.0f),
            sunDirection = -Vector3(1.0f, 3.0f, -2.0f),
            environmentIntensity = 0.3f
        )

        // Set IBL environment
        scene.updateIBLEnvironment("environment.env")

        // Set initial view position
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

        Log.i("Scene", "Scene ready")
    }

    // ========================================================================
    // PANEL REGISTRATION (Optional Web UI)
    // ========================================================================

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            PanelRegistration(R.layout.ui_example) {
                config {
                    width = 1.2f
                    height = 0.8f
                    layoutDpi = 400
                }
                panel {
                    rootView?.findViewById<WebView>(R.id.web_view)?.apply {
                        settings.javaScriptEnabled = true
                        loadUrl("http://192.168.1.50:9000")  // Your Vue dashboard
                    }
                }
            }
        )
    }
}
