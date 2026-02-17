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
import android.webkit.JavascriptInterface
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
import com.meta.spatial.toolkit.Followable
import com.meta.spatial.toolkit.FollowableType
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Sphere
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.VRFeature
import java.io.File
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

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
    private val activityJob = Job()
    private val activityScope = CoroutineScope(Dispatchers.Main + activityJob)
    private val nativeEntities = mutableMapOf<Int, Entity>()
    private var voiceController: VoiceController? = null
    private var roomWebSocket: WebSocket? = null
    private var generationWebSocket: WebSocket? = null
    private var progressBar: ProgressBar? = null
    private var dashboardWebView: WebView? = null
    private var dashboardPanelEntity: Entity? = null

    private enum class VoiceState { IDLE, AWAITING_CONFIRMATION, GENERATING }
    private var voiceState = VoiceState.IDLE
    private var pendingTranscription = ""
    private var pendingConfirmationText: String? = null
    
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(900, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

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
        private const val WS_URL = "ws://192.168.7.249:8000/api/v1/ws"

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

        activityScope.launch(Dispatchers.IO) {
            try {
                val byteBuffer = ByteBuffer.allocate(audioData.size * 2).order(ByteOrder.LITTLE_ENDIAN)
                for (sample in audioData) byteBuffer.putShort(sample)
                val wavBytes = createWavHeader(byteBuffer.array(), sampleRate)

                // ── VR → BACKEND ─────────────────────────────────────────────
                Log.i(TAG, "📤 Sending WAV to backend | size=${wavBytes.size} bytes | " +
                    "samples=${audioData.size} | sampleRate=$sampleRate Hz | " +
                    "url=$SERVER_URL/api/v1/voice/transcribe")

                // Transcribe audio with Whisper — return text to VR for confirmation
                val transcribeBody = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("audio_file", "voice.wav", wavBytes.toRequestBody("audio/wav".toMediaType()))
                    .addFormDataPart("sample_rate", sampleRate.toString())
                    .build()

                var transcribedText = ""
                httpClient.newCall(
                    Request.Builder().url("$SERVER_URL/api/v1/voice/transcribe").post(transcribeBody).build()
                ).execute().use { response ->
                    // ── BACKEND → VR ──────────────────────────────────────────
                    Log.i(TAG, "📨 Backend response | HTTP ${response.code}")
                    if (response.isSuccessful) {
                        val body = response.body?.string() ?: "{}"
                        val json = JSONObject(body)
                        transcribedText = json.optString("text")
                        val lang     = json.optString("language", "?")
                        val duration = json.optJSONObject("metadata")?.optDouble("duration", 0.0) ?: 0.0
                        Log.i(TAG, "✅ Text received from backend | " +
                            "text='$transcribedText' | lang=$lang | " +
                            "duration=${"%.2f".format(duration)}s")
                    } else {
                        Log.e(TAG, "❌ Transcription failed | HTTP ${response.code}")
                    }
                }

                if (transcribedText.isBlank()) {
                    Log.w(TAG, "⚠️ Empty transcription, aborting")
                    return@launch
                }

                // Show confirmation panel — user must confirm or retry before image is generated
                runOnUiThread { showConfirmationPanel(transcribedText) }

            } catch (e: Exception) {
                Log.e(TAG, "🎙️ Voice processing failed", e)
            }
        }
    }

    private fun connectGenerationWebSocket(generationId: String) {
        generationWebSocket?.close(1000, "New generation started")

        val request = Request.Builder()
            .url("$WS_URL/image-progress/$generationId")
            .build()

        generationWebSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "📡 Connected to generation WebSocket: $generationId")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    when (json.optString("type")) {
                        "progress" -> {
                            val percentage = json.optInt("percentage", 0)
                            Log.i(TAG, "📊 Generation progress: $percentage%")
                            runOnUiThread {
                                progressBar?.setProgressPercentage(percentage)
                            }
                        }
                        "completed" -> {
                            Log.i(TAG, "✅ Generation completed!")
                            val imageUrl = json.optJSONObject("result")
                                ?.optJSONArray("images")
                                ?.optJSONObject(0)
                                ?.optString("image_url") ?: ""
                            runOnUiThread {
                                progressBar?.setProgressPercentage(100)
                                progressBar?.setStateColor(ProgressBar.ProgressState.COMPLETE)
                                android.os.Handler(Looper.getMainLooper()).postDelayed({
                                    progressBar?.hide()
                                    progressBar?.destroy()
                                    progressBar = null
                                    voiceState = VoiceState.IDLE
                                    if (imageUrl.isNotEmpty()) {
                                        displayGeneratedImage("$SERVER_URL$imageUrl")
                                    }
                                }, 1500)
                            }
                            webSocket.close(1000, "Generation completed")
                        }
                        "error" -> {
                            val error = json.optString("error", "Unknown error")
                            Log.e(TAG, "❌ Generation error: $error")
                            runOnUiThread {
                                progressBar?.setStateColor(ProgressBar.ProgressState.ERROR)
                                android.os.Handler(Looper.getMainLooper()).postDelayed({
                                    progressBar?.hide()
                                    progressBar?.destroy()
                                    progressBar = null
                                    voiceState = VoiceState.IDLE
                                }, 2000)
                            }
                            webSocket.close(1000, "Generation failed")
                        }
                        "ping" -> webSocket.send("""{"type":"pong"}""")
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Failed to parse generation WebSocket message", e)
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "❌ Generation WebSocket failure", t)
                runOnUiThread {
                    progressBar?.setStateColor(ProgressBar.ProgressState.ERROR)
                    progressBar?.hide()
                    voiceState = VoiceState.IDLE
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "🔌 Generation WebSocket closed: $reason")
            }
        })
    }

    private fun showConfirmationPanel(text: String) {
        pendingTranscription = text
        voiceState = VoiceState.AWAITING_CONFIRMATION
        pendingConfirmationText = text

        val wv = dashboardWebView
        if (wv != null) {
            pendingConfirmationText = null
            loadConfirmationHtml(text)
            return
        }

        Log.w(TAG, "⚠️ dashboardWebView not ready — polling every 500ms | text='$text'")
        pollForDashboardWebView()
    }

    private fun pollForDashboardWebView() {
        val handler = android.os.Handler(Looper.getMainLooper())
        var attempts = 0

        fun poll() {
            val text = pendingConfirmationText
            if (text == null) {
                Log.d(TAG, "🚫 Poll cancelled — pending text already cleared")
                return
            }
            if (voiceState != VoiceState.AWAITING_CONFIRMATION) {
                Log.d(TAG, "🚫 Poll cancelled — voice state changed to $voiceState")
                return
            }

            val wv = dashboardWebView
            if (wv != null) {
                pendingConfirmationText = null
                Log.i(TAG, "✅ Poll found dashboardWebView ready (attempt $attempts) — showing confirmation")
                loadConfirmationHtml(text)
                return
            }

            attempts++
            if (attempts >= 20) {
                Log.e(TAG, "❌ Timed out waiting for dashboardWebView after ${attempts * 500}ms — panel { } never fired. Check that panel entity is in scene and ui_example.xml is correct.")
                voiceState = VoiceState.IDLE
                pendingConfirmationText = null
                return
            }

            Log.d(TAG, "⏳ Poll attempt $attempts — dashboardWebView still null, retrying in 500ms")
            handler.postDelayed({ poll() }, 500)
        }

        handler.postDelayed({ poll() }, 500)
    }

    private fun loadConfirmationHtml(text: String) {
        val safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:24px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="color:#AAAAAA;font-size:20px;margin-bottom:12px;">Did you say?</p>
              <p style="font-size:26px;padding:16px;background:#2A2A4E;border-radius:8px;
                        width:100%;text-align:center;box-sizing:border-box;margin-bottom:32px;">$safe</p>
              <div style="display:flex;gap:16px;width:100%;">
                <button onclick="Android.retry()"
                  style="flex:1;background:#B71C1C;color:white;font-size:22px;
                         padding:14px;border:none;border-radius:8px;cursor:pointer;">Retry</button>
                <button onclick="Android.confirm()"
                  style="flex:1;background:#2E7D32;color:white;font-size:22px;
                         padding:14px;border:none;border-radius:8px;cursor:pointer;">Confirm</button>
              </div>
            </body></html>
        """.trimIndent()

        dashboardWebView?.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
        Log.i(TAG, "📋 Confirmation HTML loaded into dashboard panel | text='$text'")
    }

    private fun loadIdleHtml(wv: WebView) {
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:28px;color:#64B5F6;margin-bottom:16px;">🏗️ Construction Quest</p>
              <p style="font-size:20px;color:#AAAAAA;text-align:center;">
                Hold <strong style="color:white;">A</strong> and speak to describe what you want to build.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
        Log.i(TAG, "🏠 Idle HTML loaded into dashboard panel")
    }

    private fun dismissConfirmationPanel() {
        val wv = dashboardWebView ?: return
        loadIdleHtml(wv)
        Log.i(TAG, "📺 Panel returned to idle state after confirmation")
    }

    internal fun onConfirmTranscription() {
        val text = pendingTranscription
        Log.i(TAG, "✅ User confirmed: '$text'")
        dismissConfirmationPanel()
        voiceState = VoiceState.GENERATING

        // Show progress bar and start image generation
        if (progressBar == null) progressBar = ProgressBar(position = Vector3(0f, 1.5f, -1.0f))
        progressBar?.reset()
        progressBar?.setStateColor(ProgressBar.ProgressState.GENERATING)
        progressBar?.show()

        activityScope.launch(Dispatchers.IO) {
            try {
                val generateJson = JSONObject().apply {
                    put("prompt", "$text, architectural rendering, photorealistic, detailed")
                    put("num_inference_steps", 20)
                    put("guidance_scale", 7.5)
                    put("width", 512)
                    put("height", 512)
                }
                val generateBody = generateJson.toString().toRequestBody("application/json".toMediaType())

                var generationId = ""
                httpClient.newCall(
                    Request.Builder().url("$SERVER_URL/api/v1/image/generate").post(generateBody).build()
                ).execute().use { response ->
                    if (response.isSuccessful) {
                        val json = JSONObject(response.body?.string() ?: "{}")
                        generationId = json.optString("generation_id")
                        Log.i(TAG, "🎨 Generation started: $generationId")
                    } else {
                        Log.e(TAG, "❌ Failed to start generation: ${response.code}")
                    }
                }

                if (generationId.isBlank()) {
                    runOnUiThread {
                        progressBar?.setStateColor(ProgressBar.ProgressState.ERROR)
                        progressBar?.hide()
                        voiceState = VoiceState.IDLE
                    }
                    return@launch
                }

                runOnUiThread { connectGenerationWebSocket(generationId) }

            } catch (e: Exception) {
                Log.e(TAG, "❌ Image generation failed", e)
                runOnUiThread {
                    progressBar?.setStateColor(ProgressBar.ProgressState.ERROR)
                    progressBar?.hide()
                    voiceState = VoiceState.IDLE
                }
            }
        }
    }

    internal fun onRetryTranscription() {
        Log.i(TAG, "🔄 User retried — ready to record again")
        dismissConfirmationPanel()
        voiceState = VoiceState.IDLE
    }

    private fun displayGeneratedImage(imageUrl: String) {
        runOnUiThread {
            Log.i(TAG, "🖼️ Displaying generated image from: $imageUrl")
            val imagePanel = Entity.create()
            
            // Position in front of the user (e.g., 1.5m away, 1.2m high)
            imagePanel.setComponent(Transform(Pose(t = Vector3(0f, 1.2f, -1.5f))))
            
            // Define shape using a Box component (flat like a canvas)
            imagePanel.setComponent(com.meta.spatial.toolkit.Box(Vector3(0.5f, 0.5f, 0.01f)))
            imagePanel.setComponent(Mesh(mesh = "mesh://box".toUri()))

            imagePanel.setComponent(Material().apply {
                baseColor = Color4(1f, 1f, 1f, 1f)  // Changed from baseTexture to baseTextureUri
                unlit = true
            })
            
            imagePanel.setComponent(Visible(true))
            imagePanel.setComponent(Grabbable())
        }
    }

    private fun createWavHeader(pcmAudioData: ByteArray, sampleRate: Int): ByteArray {
        val header = ByteArray(44)
        val totalDataLen = pcmAudioData.size
        val totalAudioLen = totalDataLen + 36
        val byteRate = sampleRate * 2

        header[0] = 'R'.code.toByte() // RIFF
        header[1] = 'I'.code.toByte()
        header[2] = 'F'.code.toByte()
        header[3] = 'F'.code.toByte()
        header[4] = (totalAudioLen and 0xff).toByte()
        header[5] = (totalAudioLen shr 8 and 0xff).toByte()
        header[6] = (totalAudioLen shr 16 and 0xff).toByte()
        header[7] = (totalAudioLen shr 24 and 0xff).toByte()
        header[8] = 'W'.code.toByte() // WAVE
        header[9] = 'A'.code.toByte()
        header[10] = 'V'.code.toByte()
        header[11] = 'E'.code.toByte()
        header[12] = 'f'.code.toByte() // fmt
        header[13] = 'm'.code.toByte()
        header[14] = 't'.code.toByte()
        header[15] = ' '.code.toByte()
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
        header[36] = 'd'.code.toByte() // data
        header[37] = 'a'.code.toByte()
        header[38] = 't'.code.toByte()
        header[39] = 'a'.code.toByte()
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
            
            // Connect to real-time collaboration room
            connectToRoom("tiny_house_room", "quest_user_${System.currentTimeMillis() % 1000}")
            
            isInitialized = true
        } catch (e: Exception) {
            Log.e(TAG, "Initialization failed", e)
        }
    }

    override fun onDestroy() {
        if (isRecording) voiceController?.stopRecording()
        roomWebSocket?.close(1000, "Activity destroyed")
        generationWebSocket?.close(1000, "Activity destroyed")
        progressBar?.destroy()
        progressBar = null
        dashboardPanelEntity?.destroy()
        dashboardPanelEntity = null
        dashboardWebView = null
        broadcastReceiver?.let { unregisterReceiver(it) }
        nativeEntities.values.forEach { it.destroy() }
        activityJob.cancel()
        super.onDestroy()
    }

    private fun connectToRoom(roomId: String, userId: String) {
        val request = Request.Builder()
            .url("$WS_URL/room/$roomId?user_id=$userId")
            .build()

        roomWebSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "🌐 WebSocket Connected to room: $roomId")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    val type = json.optString("type")
                    
                    if (type == "design_update") {
                        handleRemoteDesignUpdate(json)
                    } else if (type == "user_joined") {
                        Log.i(TAG, "👥 User joined: ${json.optString("user_id")}")
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Failed to parse WS message", e)
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "🌐 WebSocket Closing: $reason")
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "🌐 WebSocket Failure", t)
            }
        })
    }

    private fun handleRemoteDesignUpdate(json: JSONObject) {
        val elementId = json.optInt("element_id", -1)
        val action = json.optString("action", "update")
        val data = json.optJSONObject("data") ?: return

        runOnUiThread {
            when (action) {
                "create" -> {
                    val pos = data.getJSONObject("position")
                    val dim = data.getJSONObject("dimensions")
                    val x = pos.getDouble("x").toFloat()
                    val y = pos.getDouble("y").toFloat()
                    val z = pos.getDouble("z").toFloat()
                    val dx = dim.getDouble("width").toFloat()
                    val dy = dim.getDouble("height").toFloat()
                    val dz = dim.getDouble("depth").toFloat()
                    
                    val newId = nativeAddElement(0, x, y, z, dx, dy, dz)
                    createEntityForElement(id = newId, x = x, y = y, z = z, dx = dx, dy = dy, dz = dz)
                }
                "update" -> {
                    val pos = data.getJSONObject("position")
                    val x = pos.getDouble("x").toFloat()
                    val y = pos.getDouble("y").toFloat()
                    val z = pos.getDouble("z").toFloat()
                    
                    val existingData = nativeGetElementData(elementId) ?: return@runOnUiThread
                    nativeUpdateElement(elementId, x, y, z, existingData[3], existingData[4], existingData[5])
                    nativeEntities[elementId]?.setComponent(Transform(Pose(t = Vector3(x, y, z))))
                }
                "delete" -> {
                    if (nativeRemoveElement(elementId)) {
                        nativeEntities[elementId]?.destroy()
                        nativeEntities.remove(elementId)
                    }
                }
            }
        }
    }

    private fun broadcastDesignUpdate(id: Int, action: String, x: Float, y: Float, z: Float, dx: Float, dy: Float, dz: Float) {
        val update = JSONObject().apply {
            put("type", "design_update")
            put("element_id", id)
            put("action", action)
            put("data", JSONObject().apply {
                put("position", JSONObject().apply {
                    put("x", x)
                    put("y", y)
                    put("z", z)
                })
                put("dimensions", JSONObject().apply {
                    put("width", dx)
                    put("height", dy)
                    put("depth", dz)
                })
            })
        }
        roomWebSocket?.send(update.toString())
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
            // For Android drawable resources, use baseTextureAndroidResourceId
            baseTextureAndroidResourceId = R.drawable.skydome
            unlit = true
        })
        skybox.setComponent(Visible(true))

        android.os.Handler(Looper.getMainLooper()).postDelayed({ setupInitialConstruction() }, 500)

        // Create the dashboard panel entity programmatically so the panel { } callback fires.
        // Scene-defined panel entities do NOT trigger panel { } — only Entity.create() does.
        Log.i(TAG, "📺 Creating dashboard panel entity programmatically")
        val panelEntity = Entity.create()
        panelEntity.setComponent(Panel(R.layout.ui_example))
        panelEntity.setComponent(Transform(Pose(t = Vector3(0.3f, 1.1f, -1.7f))))
        panelEntity.setComponent(Visible(true))
        dashboardPanelEntity = panelEntity
        Log.i(TAG, "📺 Dashboard panel entity created: $panelEntity")
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
                    processRightController(rightState, entity)
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

        private fun processRightController(state: ControllerState, controllerEntity: Entity) {
            handleVoiceInput(state, controllerEntity)
            if (state.trigger) handlePlacement(state.pose)
            if (state.buttonB) handleDeletion(state.pose)
        }

        private fun handleVoiceInput(state: ControllerState, controllerEntity: Entity) {
            // Block new recordings while the user is confirming or an image is generating
            if (voiceState != VoiceState.IDLE) return

            val now = System.currentTimeMillis()

            if (state.buttonA) {
                buttonADebounceTimer = now
                if (!isRecording) {
                    isRecording = true
                    voiceController?.startRecording()
                    showVoiceIndicator(controllerEntity, state.pose, true)
                }
            } else {
                if (isRecording && (now - buttonADebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    isRecording = false
                    voiceController?.stopRecording()
                    showVoiceIndicator(null, state.pose, false)
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
                
                // Broadcast the final update when released
                val d = nativeGetElementData(grabbedElementId)
                if (d != null) {
                    broadcastDesignUpdate(grabbedElementId, "update", d[0], d[1], d[2], d[3], d[4], d[5])
                }
                
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
                        
                        // Broadcast the creation
                        broadcastDesignUpdate(id, "create", snapped[0], 0.8f, snapped[2], 0.4f, 1.6f, 0.1f)
                    }
                }
            }
        }

        private fun handleDeletion(pose: Pose) {
            val f = pose.q * Vector3(0f, 0f, -1f)
            val hitId = nativeRaycast(pose.t.x, pose.t.y, pose.t.z, f.x, f.y, f.z)
            if (hitId != -1) {
                if (nativeRemoveElement(hitId)) {
                    nativeEntities[hitId]?.destroy()
                    nativeEntities.remove(hitId)
                    
                    // Broadcast the deletion
                    broadcastDesignUpdate(hitId, "delete", 0f, 0f, 0f, 0f, 0f, 0f)
                }
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

    private fun showVoiceIndicator(controllerEntity: Entity?, pose: Pose, show: Boolean) {
        if (show) {
            if (voiceIndicator != null) return
            Log.i(TAG, "🔴 Creating voice indicator")
            val entity = Entity.create()
            voiceIndicator = entity

            entity.setComponent(Sphere(0.05f))

            val offsetPose = Pose(t = Vector3(0f, 0.15f, 0.2f))
            
            // Ensure the indicator always has a transform component initially
            entity.setComponent(Transform(pose * offsetPose))

            if (controllerEntity != null) {
                // Attach to hand if found
                entity.setComponent(Followable(
                    target = controllerEntity,
                    offset = offsetPose,
                    type = FollowableType.FACE,
                    active = true
                ))
            }

            entity.setComponent(Scale(Vector3(1f, 1f, 1f)))
            entity.setComponent(Mesh(mesh = "mesh://sphere".toUri()))
            entity.setComponent(Material().apply {
                baseColor = Color4(1f, 0f, 0f, 1f)
                unlit = true
            })
            entity.setComponent(Visible(true))
            Log.i(TAG, "✅ Indicator displayed. Following hand: ${controllerEntity != null}")
        } else {
            Log.i(TAG, "🔴 Destroying voice indicator")
            voiceIndicator?.destroy()
            voiceIndicator = null
        }
    }

    private fun updateVoiceIndicator(pose: Pose) {
        // Automatically handled by Followable component
    }

    inner class ConfirmationInterface {
        @JavascriptInterface
        fun confirm() = runOnUiThread { onConfirmTranscription() }

        @JavascriptInterface
        fun retry() = runOnUiThread { onRetryTranscription() }
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
                    Log.i(TAG, "📺 Dashboard panel { } fired | rootView=${if (rootView != null) "OK" else "NULL"}")
                    val wv = rootView?.findViewById<WebView>(R.id.web_view)
                    Log.i(TAG, "📺 Dashboard WebView lookup | webView=${if (wv != null) "OK" else "NULL"}")
                    if (wv == null) {
                        Log.e(TAG, "❌ web_view not found in ui_example layout — check layout XML")
                        return@panel
                    }
                    wv.visibility = android.view.View.VISIBLE
                    wv.settings.javaScriptEnabled = true
                    // JS interface enables Android.confirm() / Android.retry() from confirmation HTML
                    wv.addJavascriptInterface(ConfirmationInterface(), "Android")
                    dashboardWebView = wv
                    Log.i(TAG, "✅ dashboardWebView assigned successfully")

                    // If a voice command finished before the panel was ready, show it now
                    val queued = pendingConfirmationText
                    if (queued != null) {
                        pendingConfirmationText = null
                        Log.i(TAG, "📋 Panel now ready — displaying queued confirmation: '$queued'")
                        loadConfirmationHtml(queued)
                    } else {
                        loadIdleHtml(wv)
                    }
                }
            }
        )
    }
}
