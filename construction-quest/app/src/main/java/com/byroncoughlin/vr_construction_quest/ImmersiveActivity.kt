package com.byroncoughlin.vr_construction_quest

import android.Manifest
import android.annotation.SuppressLint
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import android.os.Looper
import android.util.Log
import android.webkit.WebView
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import com.meta.spatial.castinputforward.CastInputForwardFeature
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Query
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.Vector3
import com.meta.spatial.okhttp3.OkHttpAssetFetcher
import com.meta.spatial.runtime.NetworkedAssetLoader
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.AvatarAttachment
import com.meta.spatial.toolkit.Controller
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Sphere
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
    private var voiceIndicator: Entity? = null
    private var buttonADebounceTimer = 0L

    companion object {
        private const val TAG = "VRTEST"
        private var isLibraryLoaded = false
        private const val DEBOUNCE_TIMEOUT_MS = 150L
        private const val SERVER_URL = "http://192.168.7.249:8000"

        init {
            try {
                Log.i(TAG, "🚀 LOADING LIBRARY: vr_construction_quest")
                System.loadLibrary("vr_construction_quest")
                isLibraryLoaded = true
            } catch (e: Exception) {
                Log.e(TAG, "❌ FATAL: Library load failed", e)
            }
        }

        const val BUTTON_A = 0x00000001L
        const val BUTTON_B = 0x00000002L
        const val BUTTON_X = 0x00000100L
        const val BUTTON_Y = 0x00000200L
        const val TRIGGER_MASK = 0x20000000L
        const val GRIP_MASK = 0x04000000L

        const val HAND_LEFT = 0
        const val HAND_RIGHT = 1
    }

    external fun initNative()
    external fun nativeAddElement(
        type: Int,
        x: Float,
        y: Float,
        z: Float,
        dx: Float,
        dy: Float,
        dz: Float
    ): Int

    external fun nativeUpdateElement(
        id: Int,
        x: Float,
        y: Float,
        z: Float,
        dx: Float,
        dy: Float,
        dz: Float
    ): Boolean

    external fun nativeRemoveElement(id: Int): Boolean
    external fun nativeRaycast(
        ox: Float,
        oy: Float,
        oz: Float,
        dx: Float,
        dy: Float,
        dz: Float
    ): Int

    external fun nativeGetElementData(id: Int): FloatArray?
    external fun nativeSnapToGrid(x: Float, y: Float, z: Float, gridSize: Float): FloatArray?
    external fun nativePushAudio(audioData: ShortArray, size: Int)
    external fun nativeFinishRecording()
    external fun nativeSetControllerState(
        hand: Int,
        buttons: Long,
        tx: Float,
        ty: Float,
        tz: Float,
        qx: Float,
        qy: Float,
        qz: Float,
        qw: Float
    )

    // JNI Callbacks
    @Suppress("unused")
    fun onNativePostAudio(audioData: ShortArray, sampleRate: Int) {
        Log.i(TAG, "🎙️ onNativePostAudio: Received ${audioData.size} samples at $sampleRate Hz")

        val byteBuffer = ByteBuffer.allocate(audioData.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        for (sample in audioData) {
            byteBuffer.putShort(sample)
        }
        val pcmBytes = byteBuffer.array()
        val wavBytes = createWavHeader(pcmBytes, sampleRate)

        activityScope.launch(Dispatchers.IO) {
            try {
                val requestBody = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart(
                        "audio_file",
                        "voice.wav",
                        wavBytes.toRequestBody("audio/wav".toMediaType())
                    )
                    .addFormDataPart("sample_rate", sampleRate.toString())
                    .build()

                val request = Request.Builder()
                    .url("$SERVER_URL/api/v1/voice/transcribe")
                    .post(requestBody)
                    .build()

                httpClient.newCall(request).execute().use { response ->
                    if (response.isSuccessful) {
                        val body = response.body?.string()
                        Log.i(TAG, "🎙️ Server Response: $body")
                    } else {
                        Log.e(TAG, "🎙️ Server Error: ${response.code}")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "🎙️ Voice upload failed", e)
            }
        }
    }

    private fun createWavHeader(pcmAudioData: ByteArray, sampleRate: Int): ByteArray {
        val header = ByteArray(44)
        val totalDataLen = pcmAudioData.size
        val totalAudioLen = totalDataLen + 36
        val byteRate = sampleRate * 2

        header[0] = 'R'.toByte() // RIFF
        header[1] = 'I'.toByte()
        header[2] = 'F'.toByte()
        header[3] = 'F'.toByte()
        header[4] = (totalAudioLen and 0xff).toByte()
        header[5] = (totalAudioLen shr 8 and 0xff).toByte()
        header[6] = (totalAudioLen shr 16 and 0xff).toByte()
        header[7] = (totalAudioLen shr 24 and 0xff).toByte()
        header[8] = 'W'.toByte() // WAVE
        header[9] = 'A'.toByte()
        header[10] = 'V'.toByte()
        header[11] = 'E'.toByte()
        header[12] = 'f'.toByte() // fmt
        header[13] = 'm'.toByte()
        header[14] = 't'.toByte()
        header[15] = ' '.toByte()
        header[16] = 16 // size of fmt chunk
        header[17] = 0
        header[18] = 0
        header[19] = 0
        header[20] = 1 // format = 1 (PCM)
        header[21] = 0
        header[22] = 1 // channels = 1
        header[23] = 0
        header[24] = (sampleRate and 0xff).toByte()
        header[25] = (sampleRate shr 8 and 0xff).toByte()
        header[26] = (sampleRate shr 16 and 0xff).toByte()
        header[27] = (sampleRate shr 24 and 0xff).toByte()
        header[28] = (byteRate and 0xff).toByte()
        header[29] = (byteRate shr 8 and 0xff).toByte()
        header[30] = (byteRate shr 16 and 0xff).toByte()
        header[31] = (byteRate shr 24 and 0xff).toByte()
        header[32] = 2 // block align
        header[33] = 0
        header[34] = 16 // bits per sample
        header[35] = 0
        header[36] = 'd'.toByte() // data
        header[37] = 'a'.toByte()
        header[38] = 't'.toByte()
        header[39] = 'a'.toByte()
        header[40] = (totalDataLen and 0xff).toByte()
        header[41] = (totalDataLen shr 8 and 0xff).toByte()
        header[42] = (totalDataLen shr 16 and 0xff).toByte()
        header[43] = (totalDataLen shr 24 and 0xff).toByte()

        return header + pcmAudioData
    }

    @Suppress("unused")
    fun onNativeSyncProject(jsonStr: String) {
        Log.i(TAG, "🏗️ onNativeSyncProject: Received project data: $jsonStr")
    }

    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(VRFeature(this))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (isInitialized) return

        try {
            NetworkedAssetLoader.init(
                File(applicationContext.cacheDir.canonicalPath),
                OkHttpAssetFetcher()
            )
            if (isLibraryLoaded) initNative()

            if (ContextCompat.checkSelfPermission(
                    this,
                    Manifest.permission.RECORD_AUDIO
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.RECORD_AUDIO),
                    1001
                )
            }

            voiceController = VoiceController()
            systemManager.registerSystem(ConstructionInputSystem())

            broadcastReceiver = object : BroadcastReceiver() {
                override fun onReceive(context: Context, intent: Intent) {
                    currentMaterial = intent.getStringExtra("selectedMaterial") ?: "Wood"
                }
            }
            ContextCompat.registerReceiver(
                this,
                broadcastReceiver,
                IntentFilter("com.byroncoughlin.CHANGE_MATERIAL"),
                ContextCompat.RECEIVER_NOT_EXPORTED
            )
            isInitialized = true
        } catch (e: Exception) {
            Log.e(TAG, "Initialization failed", e)
        }
    }

    override fun onDestroy() {
        if (isRecording) voiceController?.stopRecording()
        broadcastReceiver?.let { unregisterReceiver(it) }
        nativeEntities.values.forEach { it.destroy() }
        super.onDestroy()
    }

    override fun onSceneReady() {
        super.onSceneReady()
        scene.setLightingEnvironment(
            ambientColor = Vector3(0.4f, 0.4f, 0.4f),
            sunColor = Vector3(8.0f, 8.0f, 8.0f),
            sunDirection = -Vector3(1.0f, 3.0f, -2.0f),
            environmentIntensity = 0.5f
        )
        scene.setViewOrigin(0.0f, 0.0f, 0.0f, 0.0f)

        val skybox = Entity.create()
        skybox.setComponent(Transform(Pose(t = Vector3(0f, 0f, 0f))))
        skybox.setComponent(Mesh(mesh = "mesh://skybox".toUri()))
        skybox.setComponent(Material().apply {
            baseTextureAndroidResourceId = R.drawable.skydome
            unlit = true
        })
        skybox.setComponent(Visible(true))

        android.os.Handler(Looper.getMainLooper()).postDelayed({ setupInitialConstruction() }, 500)
    }

    inner class ConstructionInputSystem : SystemBase() {
        private var grabbedElementId = -1
        private var grabOffset = Vector3(0f)
        private val leftState = ControllerState()
        private val rightState = ControllerState()

        override fun execute() {
            if (!isLibraryLoaded) return

            val query = Query.where {
                has(AvatarAttachment.id, Transform.id, Controller.id)
            }

            val entities = query.eval()

            for (entity in entities) {
                val attachment = entity.tryGetComponent<AvatarAttachment>() ?: continue
                val transform = entity.tryGetComponent<Transform>() ?: continue
                val controller = entity.tryGetComponent<Controller>() ?: continue
                val hand = if (attachment.type == "hand_left") HAND_LEFT else HAND_RIGHT

                val buttons = controller.buttonState.toLong()

                val p = transform.transform.t
                val q = transform.transform.q
                nativeSetControllerState(hand, buttons, p.x, p.y, p.z, q.x, q.y, q.z, q.w)

                if (hand == HAND_LEFT) {
                    updateControllerState(leftState, transform.transform, buttons)
                    processLeftController(leftState)
                } else {
                    updateControllerState(rightState, transform.transform, buttons)
                    processRightController(rightState)
                }
            }
        }

        private fun updateControllerState(state: ControllerState, pose: Pose, buttons: Long) {
            state.buttonA = (buttons and BUTTON_A) != 0L
            state.buttonB = (buttons and BUTTON_B) != 0L
            state.buttonX = (buttons and BUTTON_X) != 0L
            state.buttonY = (buttons and BUTTON_Y) != 0L
            state.trigger = (buttons and TRIGGER_MASK) != 0L
            state.grip = (buttons and GRIP_MASK) != 0L
            state.pose = pose
        }

        private fun processLeftController(state: ControllerState) {
            handleGrabAndMove(state)
            if (state.buttonX) handleDeletion(state.pose)
        }

        private fun processRightController(state: ControllerState) {
            handleVoiceInput(state)
            if (state.trigger) handlePlacement(state.pose)
            if (state.buttonB) handleDeletion(state.pose)
        }

        private fun handleVoiceInput(state: ControllerState) {
            val now = System.currentTimeMillis()

            if (state.buttonA) {
                buttonADebounceTimer = now
                if (!isRecording) {
                    isRecording = true
                    voiceController?.startRecording()
                    showVoiceIndicator(state.pose, true)
                }
            } else {
                if (isRecording && (now - buttonADebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    isRecording = false
                    voiceController?.stopRecording()
                    showVoiceIndicator(state.pose, false)
                }
            }

            if (isRecording) updateVoiceIndicator(state.pose)
        }

        private fun handleGrabAndMove(state: ControllerState) {
            if (state.grip && grabbedElementId == -1) {
                val origin = state.pose.t
                val forward = state.pose.q * Vector3(0f, 0f, -1f)
                grabbedElementId =
                    nativeRaycast(origin.x, origin.y, origin.z, forward.x, forward.y, forward.z)
                if (grabbedElementId != -1) {
                    highlightElement(grabbedElementId, true)
                    val data = nativeGetElementData(grabbedElementId)
                    if (data != null) grabOffset =
                        Vector3(data[0] - origin.x, data[1] - origin.y, data[2] - origin.z)
                }
            } else if (!state.grip && grabbedElementId != -1) {
                highlightElement(grabbedElementId, false)
                grabbedElementId = -1
            } else if (grabbedElementId != -1) {
                val targetPos =
                    state.pose.t + (state.pose.q * Vector3(0f, 0f, -1f)) * 3.0f + grabOffset
                val snapped = nativeSnapToGrid(targetPos.x, targetPos.y, targetPos.z, 0.5f)
                if (snapped != null) {
                    val d = nativeGetElementData(grabbedElementId) ?: return
                    nativeUpdateElement(
                        grabbedElementId,
                        snapped[0],
                        snapped[1],
                        snapped[2],
                        d[3],
                        d[4],
                        d[5]
                    )
                    nativeEntities[grabbedElementId]?.setComponent(
                        Transform(
                            Pose(
                                t = Vector3(
                                    snapped[0],
                                    snapped[1],
                                    snapped[2]
                                )
                            )
                        )
                    )
                }
            }
        }

        private fun handlePlacement(pose: Pose) {
            val forward = pose.q * Vector3(0f, 0f, -1f)
            if (forward.y < -0.2f) {
                val t = -pose.t.y / forward.y
                if (t > 0 && t < 10.0f) {
                    val fx = pose.t.x + forward.x * t
                    val fz = pose.t.z + forward.z * t
                    val snapped = nativeSnapToGrid(fx, 0f, fz, 0.5f)
                    if (snapped != null) {
                        val id = nativeAddElement(0, snapped[0], 0.8f, snapped[2], 0.4f, 1.6f, 0.1f)
                        createEntityForElement(id, snapped[0], 0.8f, snapped[2], 0.4f, 1.6f, 0.1f)
                    }
                }
            }
        }

        private fun handleDeletion(pose: Pose) {
            val f = pose.q * Vector3(0f, 0f, -1f)
            val hitId = nativeRaycast(pose.t.x, pose.t.y, pose.t.z, f.x, f.y, f.z)
            if (hitId != -1 && nativeRemoveElement(hitId)) {
                nativeEntities[hitId]?.destroy()
                nativeEntities.remove(hitId)
            }
        }
    }

    private fun setupInitialConstruction() {
        if (!isLibraryLoaded) return
        val floorId = nativeAddElement(1, 0f, -0.05f, 0f, 30f, 0.1f, 30f)
        createEntityForElement(floorId, 0f, -0.05f, 0f, 30f, 0.1f, 30f, isFloor = true)
    }

    private fun createEntityForElement(
        id: Int,
        x: Float,
        y: Float,
        z: Float,
        dx: Float,
        dy: Float,
        dz: Float,
        isFloor: Boolean = false
    ) {
        try {
            val entity = Entity.create()
            entity.setComponent(Transform(Pose(t = Vector3(x, y, z))))
            entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
            entity.setComponent(com.meta.spatial.toolkit.Box(Vector3(dx / 2f, dy / 2f, dz / 2f)))

            entity.setComponent(Material().apply {
                if (isFloor) {
                    baseColor = Color4(0.3f, 0.3f, 0.3f, 1.0f)
                    roughness = 0.5f
                } else {
                    baseColor = Color4(0.7f, 0.5f, 0.3f, 1.0f)
                }
                unlit = false
            })
            entity.setComponent(Grabbable())
            entity.setComponent(Visible(true))

            nativeEntities[id] = entity
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create entity $id", e)
        }
    }

    private fun highlightElement(id: Int, h: Boolean) {
        nativeEntities[id]?.let { e ->
            val m = e.tryGetComponent<Material>() ?: return@let
            m.unlit = h
            e.setComponent(m)
        }
    }

    private fun showVoiceIndicator(pose: Pose, show: Boolean) {
        if (show) {
            Log.i(TAG, "🔴 Creating voice indicator")
            voiceIndicator = Entity.create()

            voiceIndicator?.setComponent(Sphere(0.15f))

            val indicatorPose = pose * Pose(t = Vector3(0f, 0.3f, -0.6f))

            voiceIndicator?.setComponent(Transform(indicatorPose))
            voiceIndicator?.setComponent(Scale(Vector3(1f, 1f, 1f)))
            voiceIndicator?.setComponent(Mesh(mesh = "mesh://sphere".toUri()))
            voiceIndicator?.setComponent(Material().apply {
                baseColor = Color4(0f, 1f, 0f, 1f)
                unlit = true
            })
            voiceIndicator?.setComponent(Visible(true))
            Log.i(TAG, "✅ Indicator displayed at ${indicatorPose.t}")
        } else {
            Log.i(TAG, "🔴 Destroying voice indicator")
            voiceIndicator?.destroy()
            voiceIndicator = null
        }
    }

    private fun updateVoiceIndicator(pose: Pose) {
        val indicatorPose = pose * Pose(t = Vector3(0f, 0.3f, -0.6f))
        voiceIndicator?.setComponent(Transform(indicatorPose))
    }

    inner class VoiceController {
        private var audioRecord: AudioRecord? = null
        private var isRecording = false
        private var recordingThread: Thread? = null
        private val sampleRate = 16000
        private val channelConfig = AudioFormat.CHANNEL_IN_MONO
        private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        private var bufferSize =
            AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat).let {
                if (it > 0) it else 2048
            }

        @SuppressLint("MissingPermission")
        fun startRecording() {
            if (!isLibraryLoaded || isRecording) return

            if (ContextCompat.checkSelfPermission(
                    this@ImmersiveActivity,
                    Manifest.permission.RECORD_AUDIO
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                Log.e(TAG, "🎙️ Permission denied: RECORD_AUDIO")
                return
            }

            try {
                audioRecord = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
                )
                if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                    Log.e(TAG, "🎙️ AudioRecord failed to initialize")
                    return
                }

                audioRecord?.startRecording()
                isRecording = true
                recordingThread = Thread {
                    val data = ShortArray(bufferSize)
                    while (isRecording) {
                        try {
                            val read = audioRecord?.read(data, 0, bufferSize) ?: 0
                            if (read > 0 && isRecording) {
                                nativePushAudio(data, read)
                            }
                        } catch (e: Exception) {
                            Log.e(TAG, "Read error", e)
                            break
                        }
                    }
                }
                recordingThread?.start()
                Log.i(TAG, "🎙️ Voice recording started")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Crash prevented: Failed to start recording", e)
            }
        }

        fun stopRecording() {
            if (!isRecording) return
            isRecording = false

            try {
                if (audioRecord?.recordingState == AudioRecord.RECORDSTATE_RECORDING) {
                    audioRecord?.stop()
                }

                recordingThread?.join(500)
                recordingThread = null

                audioRecord?.release()
                audioRecord = null

                if (isLibraryLoaded) {
                    activityScope.launch(Dispatchers.IO) {
                        nativeFinishRecording()
                    }
                }
                Log.i(TAG, "🎙️ Voice recording stopped successfully")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Crash prevented: Error during stopRecording", e)
            }
        }
    }

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
                        loadUrl("http://192.168.7.249:9000")
                    }
                }
            }
        )
    }
}
