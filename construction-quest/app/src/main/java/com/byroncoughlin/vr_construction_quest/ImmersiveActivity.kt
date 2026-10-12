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
    private var progressBar: VRProgressBar? = null
    private var dashboardWebView: WebView? = null
    private var dashboardPanelEntity: Entity? = null
    private var webPanelEntity: Entity? = null

    // Two-prompt voice flow: prompt 1 generates the walkable VR floor plan,
    // prompt 2 (spoken from inside the house) generates a 2D image the user reviews.
    private enum class VoiceState {
        IDLE,                 // ready to hold A and record prompt 1
        RECORDING_PROMPT1,    // mid-recording prompt 1 audio
        CONFIRMING_TEXT1,     // prompt 1 transcribed, awaiting Confirm/Retry
        GENERATING_GEOMETRY,  // VR geometry being fetched and built
        READY_FOR_PROMPT2,    // floor plan built, ready for prompt 2 recording
        RECORDING_PROMPT2,    // mid-recording prompt 2 audio
        CONFIRMING_TEXT2,     // prompt 2 transcribed, awaiting Confirm/Retry
        GENERATING_IMAGE,     // image being generated (WebSocket progress)
        REVIEWING_IMAGE,      // image shown with Accept / Edit / Start Over
        WALKING,              // image accepted, walking the floor plan with it
        RECORDING_REFINE,     // grip held inside a saved house: recording a floor-plan change
        CONFIRMING_REFINE,    // change transcribed, awaiting Confirm/Retry
        REFINING_GEOMETRY     // backend revising the floor plan; the house is rebuilt after
    }
    private var voiceState = VoiceState.IDLE
    private var pendingTranscription = ""
    private var pendingConfirmationText: String? = null

    // Two-prompt flow state
    private var currentImageGenerationId: String? = null
    private var currentImagePrompt: String? = null
    private var currentImageUrl: String? = null
    // Where the prompt panel, progress bar and review panel are placed relative to.
    // The origin until a floor plan is built, then the player's spawn point, so the
    // prompt-2 UI appears in front of the player inside the house.
    private var panelAnchor = Vector3(0f, 0f, 0f)
    // Watchdog for the image-generation WebSocket: if the socket goes silent (backend
    // died, message lost) we must not sit in GENERATING_IMAGE forever — that state
    // blocks all controller input, so the only way out would be force-quitting.
    private val generationWatchdogHandler = android.os.Handler(Looper.getMainLooper())
    private var generationWatchdog: Runnable? = null
    private var walkingImagePanelEntity: Entity? = null
    private var walkingImageWebView: WebView? = null
    // Dedicated review panel for the generated 2D image — its own entity, twice the
    // size of the prompt panel, so the image is not squeezed in beside the buttons.
    private var reviewImagePanelEntity: Entity? = null
    private var reviewImageWebView: WebView? = null
    private var pendingReviewImageUrl: String? = null

    // The house on display. Houses from the voice flow and the dashboard are saved
    // projects, so they can be refined by voice and their accepted image linked.
    private var currentProjectId: Int? = null
    private var currentHouseName: String? = null
    private var currentFloorPlanVersion: Int? = null
    // Server path of the accepted image (/generated_images/...), for linking.
    private var currentImagePath: String? = null
    // Where a floor-plan refinement returns to: READY_FOR_PROMPT2 or WALKING.
    private var refineReturnState = VoiceState.READY_FOR_PROMPT2
    // Name sign floating above the panels: which house is being displayed.
    private var houseSignEntity: Entity? = null
    private var houseSignWebView: WebView? = null
    
    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(60, TimeUnit.SECONDS)
        .readTimeout(900, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    private var houseGenerator: HouseGenerator? = null

    private var locomotionEnabled = false
    private var xrayEnabled = false
    private var roomLabelsVisible = false
    private val roomLabelEntities = mutableListOf<Entity>()
    private val pendingRoomLabels = java.util.concurrent.ConcurrentLinkedQueue<RoomInfo>()
    private var currentMaterial = "Wood"
    private var isRecording = false
    // Set from button release until the transcription comes back (or fails); input is
    // ignored meanwhile so a second recording can't start on top of the first.
    private var transcribing = false
    private var broadcastReceiver: BroadcastReceiver? = null
    private var isInitialized = false
    private var voiceIndicator: Entity? = null
    private var buttonADebounceTimer = 0L
    private var buttonBDebounceTimer = 0L

    companion object {
        private const val TAG = "VRTEST"
        private var isLibraryLoaded = false
        private const val DEBOUNCE_TIMEOUT_MS = 150L
        // The server pings an idle progress socket every 30s, so any live connection
        // produces traffic well inside this window.
        private const val GENERATION_STALL_TIMEOUT_MS = 90_000L
        // How far in front of the player (along -z) the panels sit. 1.7 m was close
        // enough that the panels were hard to grab and move.
        private const val PANEL_DISTANCE = 2.6f
        // Prompt panel: 1.2 x 1.2 centred at x=0.3 (so it spans x -0.3 .. 0.9).
        private const val PROMPT_PANEL_SIZE = 1.2f
        // Review image panel: twice the prompt panel in each dimension, parked to its
        // right with a 0.1 gap (left edge 1.0 -> centre 2.2) and raised so the taller
        // panel does not clip through the floor.
        private const val REVIEW_PANEL_SIZE = PROMPT_PANEL_SIZE * 2f
        private const val REVIEW_PANEL_X = 2.2f
        private const val REVIEW_PANEL_Y = 1.4f
        private const val REVIEW_PANEL_Z = -PANEL_DISTANCE
        // House name sign: above the prompt panel and the walking image panel.
        private const val HOUSE_SIGN_WIDTH = 1.6f
        private const val HOUSE_SIGN_HEIGHT = 0.4f
        private const val HOUSE_SIGN_Y = 2.45f
        // Prompt numbers passed through recording/transcription; 3 is a floor-plan change.
        private const val PHASE_REFINE = 3
        // From gradle.properties (serverHost) via app/build.gradle.kts.
        private const val SERVER_URL = BuildConfig.SERVER_URL
        private const val WS_URL = BuildConfig.WS_URL

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

    /**
     * Send a finished recording to Whisper and show the confirmation panel for [phase]
     * (1 = floor plan, 2 = house look). Any failure returns the user to recording the
     * same prompt — never to the other one. Call from a background thread.
     */
    private fun transcribeAudio(audioData: ShortArray, sampleRate: Int, phase: Int) {
        Log.i(TAG, "🎙️ Transcribing ${audioData.size} samples at $sampleRate Hz (prompt $phase)")
        try {
            if (audioData.isEmpty()) {
                failTranscription(phase, "No audio was recorded")
                return
            }
            val byteBuffer = ByteBuffer.allocate(audioData.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            for (sample in audioData) byteBuffer.putShort(sample)
            val wavBytes = createWavHeader(byteBuffer.array(), sampleRate)

            val transcribeBody = MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart("audio_file", "voice.wav", wavBytes.toRequestBody("audio/wav".toMediaType()))
                .addFormDataPart("sample_rate", sampleRate.toString())
                .build()

            var transcribedText = ""
            httpClient.newCall(
                Request.Builder().url("$SERVER_URL/api/v1/voice/transcribe").post(transcribeBody).build()
            ).execute().use { response ->
                Log.i(TAG, "📨 Transcription response | HTTP ${response.code}")
                if (response.isSuccessful) {
                    val json = JSONObject(response.body?.string() ?: "{}")
                    transcribedText = json.optString("text")
                    Log.i(TAG, "✅ Transcribed: '$transcribedText' | lang=${json.optString("language", "?")}")
                } else {
                    failTranscription(phase, "Transcription failed (HTTP ${response.code})")
                    return
                }
            }

            if (transcribedText.isBlank()) {
                failTranscription(phase, "Didn't catch that")
                return
            }

            // User must confirm or retry before we act on the prompt
            runOnUiThread {
                transcribing = false
                showConfirmationPanel(transcribedText, phase)
            }
        } catch (e: Exception) {
            Log.e(TAG, "🎙️ Voice processing failed", e)
            failTranscription(phase, e.message ?: "Could not reach the server")
        }
    }

    private fun failTranscription(phase: Int, reason: String) {
        Log.w(TAG, "⚠️ Transcription failed (prompt $phase): $reason")
        runOnUiThread {
            transcribing = false
            voiceState = readyStateFor(phase)
            showPanel()
            dashboardWebView?.let { loadVoiceRetryHtml(it, phase, reason) }
        }
    }

    private fun loadVoiceRetryHtml(wv: WebView, phase: Int, reason: String) {
        val safe = reason.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        val what = when (phase) {
            1 -> "the floor plan"
            PHASE_REFINE -> "the change to the floor plan"
            else -> "how the house should look"
        }
        val button = if (phase == PHASE_REFINE) "the grip" else "A"
        val step = if (phase == PHASE_REFINE) "Change the floor plan" else "Step $phase of 2"
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:14px;color:#64B5F6;margin:0 0 8px;">$step</p>
              <p style="font-size:24px;color:#F9A825;margin-bottom:12px;">🎙️ $safe</p>
              <p style="font-size:18px;color:#AAAAAA;text-align:center;">
                Hold <strong style="color:white;">$button</strong> and describe $what again.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    /**
     * (Re)arm the stall watchdog. Called when the progress socket is opened and again on
     * every message received, so the timer only fires after a genuine silence.
     */
    private fun armGenerationWatchdog() {
        cancelGenerationWatchdog()
        val runnable = Runnable {
            generationWatchdog = null
            Log.e(TAG, "⏱️ No progress for ${GENERATION_STALL_TIMEOUT_MS}ms — aborting image generation")
            abortImageGeneration("Generation timed out — no response from server")
        }
        generationWatchdog = runnable
        generationWatchdogHandler.postDelayed(runnable, GENERATION_STALL_TIMEOUT_MS)
    }

    private fun cancelGenerationWatchdog() {
        generationWatchdog?.let { generationWatchdogHandler.removeCallbacks(it) }
        generationWatchdog = null
    }

    /**
     * Tear down a failed/stalled generation and return the panel to idle so the user can
     * record again. Safe to call from any state; must run on the UI thread.
     */
    private fun abortImageGeneration(reason: String) {
        cancelGenerationWatchdog()
        // A late socket error after the image already arrived must not wipe the
        // review panel and drag the user back to IDLE.
        if (voiceState != VoiceState.GENERATING_IMAGE) {
            Log.i(TAG, "🛑 Ignoring abort in state $voiceState: $reason")
            return
        }
        Log.w(TAG, "🛑 Aborting image generation: $reason")
        generationWebSocket?.close(1000, "Generation aborted")
        generationWebSocket = null
        currentImageGenerationId = null
        progressBar?.setStateColor(VRProgressBar.ProgressState.ERROR)
        dismissProgressBar(2000)
        voiceState = VoiceState.READY_FOR_PROMPT2
        showPanel()
        dashboardWebView?.let { loadErrorHtml(it, reason) }
    }

    private fun loadErrorHtml(wv: WebView, reason: String) {
        val safe = reason.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:26px;color:#EF5350;margin-bottom:12px;">⚠️ Generation failed</p>
              <p style="font-size:16px;color:#AAAAAA;text-align:center;margin-bottom:20px;">$safe</p>
              <p style="font-size:18px;color:#AAAAAA;text-align:center;">
                Hold <strong style="color:white;">A</strong> and speak to try again.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    private fun connectGenerationWebSocket(generationId: String) {
        generationWebSocket?.close(1000, "New generation started")

        val request = Request.Builder()
            .url("$WS_URL/image-progress/$generationId")
            .build()

        generationWebSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "📡 Connected to generation WebSocket: $generationId")
                runOnUiThread { armGenerationWatchdog() }
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                // Any traffic proves the backend is alive — push the deadline out.
                runOnUiThread { armGenerationWatchdog() }
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
                            Log.i(TAG, "✅ Image generation completed!")
                            val imageUrl = json.optJSONObject("result")
                                ?.optJSONArray("images")
                                ?.optJSONObject(0)
                                ?.optString("image_url") ?: ""
                            runOnUiThread {
                                // Stale result: the generation was aborted or replaced.
                                if (voiceState != VoiceState.GENERATING_IMAGE ||
                                    currentImageGenerationId != generationId) {
                                    Log.w(TAG, "⏭️ Ignoring completion of $generationId in state $voiceState")
                                    deleteGeneratedImage(generationId)
                                    return@runOnUiThread
                                }
                                cancelGenerationWatchdog()
                                progressBar?.setProgressPercentage(100)
                                progressBar?.setStateColor(VRProgressBar.ProgressState.COMPLETE)
                                dismissProgressBar(1500)
                                android.os.Handler(Looper.getMainLooper()).postDelayed({
                                    if (voiceState != VoiceState.GENERATING_IMAGE) return@postDelayed
                                    if (imageUrl.isNotEmpty()) {
                                        val fullUrl = "$SERVER_URL$imageUrl"
                                        currentImageUrl = fullUrl
                                        currentImagePath = imageUrl
                                        voiceState = VoiceState.REVIEWING_IMAGE
                                        displayReviewPanel(fullUrl)
                                    } else {
                                        voiceState = VoiceState.READY_FOR_PROMPT2
                                        showPanel()
                                        dashboardWebView?.let { loadPrompt2Html(it) }
                                    }
                                }, 1500)
                            }
                            webSocket.close(1000, "Generation completed")
                        }
                        "error" -> {
                            val error = json.optString("error", "Unknown error")
                            Log.e(TAG, "❌ Generation error: $error")
                            runOnUiThread { abortImageGeneration(error) }
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
                    abortImageGeneration(t.message ?: "Lost connection to server")
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "🔌 Generation WebSocket closed: $reason")
            }
        })
    }

    private fun showConfirmationPanel(text: String, phase: Int) {
        pendingTranscription = text
        voiceState = confirmingStateFor(phase)
        pendingConfirmationText = text

        val wv = dashboardWebView
        if (wv != null) {
            pendingConfirmationText = null
            loadConfirmationHtml(text, phase)
            return
        }

        Log.w(TAG, "⚠️ dashboardWebView not ready — polling every 500ms | text='$text'")
        pollForDashboardWebView(phase)
    }

    private fun pollForDashboardWebView(phase: Int) {
        val handler = android.os.Handler(Looper.getMainLooper())
        var attempts = 0
        val expectedState = confirmingStateFor(phase)

        fun poll() {
            val text = pendingConfirmationText
            if (text == null) {
                Log.d(TAG, "🚫 Poll cancelled — pending text already cleared")
                return
            }
            if (voiceState != expectedState) {
                Log.d(TAG, "🚫 Poll cancelled — voice state changed to $voiceState")
                return
            }

            val wv = dashboardWebView
            if (wv != null) {
                pendingConfirmationText = null
                Log.i(TAG, "✅ Poll found dashboardWebView ready (attempt $attempts) — showing confirmation")
                loadConfirmationHtml(text, phase)
                return
            }

            attempts++
            if (attempts >= 20) {
                Log.e(TAG, "❌ Timed out waiting for dashboardWebView after ${attempts * 500}ms — panel { } never fired. Check that panel entity is in scene and ui_example.xml is correct.")
                voiceState = readyStateFor(phase)
                pendingConfirmationText = null
                return
            }

            Log.d(TAG, "⏳ Poll attempt $attempts — dashboardWebView still null, retrying in 500ms")
            handler.postDelayed({ poll() }, 500)
        }

        handler.postDelayed({ poll() }, 500)
    }

    private fun loadConfirmationHtml(text: String, phase: Int) {
        val safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
        val headline = when (phase) {
            1 -> "Describe the floor plan (walkable)"
            PHASE_REFINE -> "Change the floor plan"
            else -> "Describe the house look (2D image)"
        }
        val step = if (phase == PHASE_REFINE) "Floor plan change" else "Step $phase of 2"
        val html = """
            <!DOCTYPE html><html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="margin:0;padding:24px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="color:#64B5F6;font-size:14px;margin:0 0 4px;">$step</p>
              <p style="color:#AAAAAA;font-size:18px;margin:0 0 12px;">$headline — did you say?</p>
              <p style="font-size:26px;padding:16px;background:#2A2A4E;border-radius:8px;
                        width:100%;text-align:center;box-sizing:border-box;margin-bottom:20px;">$safe</p>
              <p style="color:#64B5F6;font-size:16px;margin-bottom:24px;text-align:center;">
                <strong style="color:white;">Button A</strong> to confirm •
                <strong style="color:white;">Button B</strong> to retry
              </p>
              <div style="display:flex;gap:16px;width:100%;">
                <button onclick="try { Android.retry(); } catch(e) { console.log('Retry error: ' + e); }"
                  style="flex:1;background:#B71C1C;color:white;font-size:22px;
                         padding:14px;border:none;border-radius:8px;cursor:pointer;
                         -webkit-tap-highlight-color:rgba(0,0,0,0.3);">Retry</button>
                <button onclick="try { Android.confirm(); } catch(e) { console.log('Confirm error: ' + e); }"
                  style="flex:1;background:#2E7D32;color:white;font-size:22px;
                         padding:14px;border:none;border-radius:8px;cursor:pointer;
                         -webkit-tap-highlight-color:rgba(0,0,0,0.3);">Confirm</button>
              </div>
            </body></html>
        """.trimIndent()

        dashboardWebView?.loadDataWithBaseURL("file:///android_asset/", html, "text/html", "UTF-8", null)
        Log.i(TAG, "📋 Confirmation HTML loaded (phase $phase) | text='$text'")
    }

    private fun loadIdleHtml(wv: WebView) {
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:28px;color:#64B5F6;margin-bottom:16px;">🏗️ Construction Quest</p>
              <p style="font-size:14px;color:#64B5F6;margin:0 0 8px;">Step 1 of 2 — Floor Plan</p>
              <p style="font-size:20px;color:#AAAAAA;text-align:center;">
                Hold <strong style="color:white;">A</strong> and describe the floor plan —
                rooms, layout, size.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
        Log.i(TAG, "🏠 Idle HTML loaded into dashboard panel")
    }

    private fun confirmingStateFor(phase: Int) = when (phase) {
        1 -> VoiceState.CONFIRMING_TEXT1
        PHASE_REFINE -> VoiceState.CONFIRMING_REFINE
        else -> VoiceState.CONFIRMING_TEXT2
    }

    /** The state to go back to when recording [phase] has to be repeated. */
    private fun readyStateFor(phase: Int) = when (phase) {
        1 -> VoiceState.IDLE
        PHASE_REFINE -> refineReturnState
        else -> VoiceState.READY_FOR_PROMPT2
    }

    private fun hidePanel() {
        dashboardPanelEntity?.setComponent(Visible(false))
        Log.i(TAG, "👁️ Panel hidden")
    }
    
    private fun showPanel() {
        dashboardPanelEntity?.setComponent(Visible(true))
        Log.i(TAG, "👁️ Panel shown")
    }

    internal fun onConfirmTranscription() {
        when (voiceState) {
            VoiceState.CONFIRMING_TEXT1 -> onConfirmPrompt1()
            VoiceState.CONFIRMING_TEXT2 -> onConfirmPrompt2()
            VoiceState.CONFIRMING_REFINE -> onConfirmRefine()
            else -> Log.w(TAG, "⚠️ onConfirmTranscription in unexpected state: $voiceState")
        }
    }

    /**
     * Prompt 1: user confirmed the floor plan description — fetch walkable VR geometry,
     * build it, spawn the player inside, then prompt for the house look (prompt 2).
     */
    private fun onConfirmPrompt1() {
        val text = pendingTranscription
        Log.i(TAG, "✅ Prompt 1 confirmed (floor plan): '$text'")
        hidePanel()
        voiceState = VoiceState.GENERATING_GEOMETRY
        showProgressBar()

        activityScope.launch(Dispatchers.IO) {
            try {
                val geometry = houseGenerator?.fetchVRGeometryFromPrompt(text, null)
                if (geometry == null) {
                    Log.w(TAG, "⚠️ fetchVRGeometryFromPrompt returned null")
                    runOnUiThread { failGeometryGeneration("Could not generate the floor plan") }
                    return@launch
                }

                runOnUiThread {
                    enterHouse(geometry)

                    progressBar?.setProgressPercentage(100)
                    progressBar?.setStateColor(VRProgressBar.ProgressState.COMPLETE)
                    dismissProgressBar(1500)

                    // The prompt panel came along, so prompt 2 is asked from inside the house.
                    showPanel()
                    dashboardWebView?.let { loadPrompt2Html(it) }
                    voiceState = VoiceState.READY_FOR_PROMPT2
                }

            } catch (e: Exception) {
                Log.e(TAG, "❌ Prompt 1 geometry fetch failed", e)
                runOnUiThread { failGeometryGeneration(e.message ?: "Could not reach the server") }
            }
        }
    }

    /**
     * Build [geometry], move the player to its spawn point and bring the prompt UI
     * along. Replaces any house already loaded. UI thread only.
     */
    private fun enterHouse(geometry: JSONObject) {
        // Labels and the walking image belong to the previous house.
        if (roomLabelsVisible) toggleRoomLabels()
        destroyWalkingImagePanel()

        currentProjectId = geometry.optInt("project_id", 0).takeIf { it > 0 }
        currentHouseName = geometry.optString("project_name", "").ifBlank { null }
        currentFloorPlanVersion = geometry.optJSONObject("floor_plan")
            ?.optInt("version", 0)?.takeIf { it > 0 }
        Log.i(TAG, "🏡 Displaying '$currentHouseName' (project=$currentProjectId, plan v$currentFloorPlanVersion)")

        val spawnPos = houseGenerator?.buildFromGeometry(geometry)
        Log.i(TAG, "🏠 House built. Spawn: $spawnPos")
        if (spawnPos != null) {
            scene.setViewOrigin(spawnPos.x, 0f, spawnPos.z, 0f)
        }
        locomotionEnabled = true
        if (!roomLabelsVisible) toggleRoomLabels()

        panelAnchor = spawnPos ?: Vector3(0f, 0f, 0f)
        placePromptPanel()
        showHouseSign()
    }

    /**
     * Show which house is on display on a sign above the panels. The panel { }
     * callback fills it in (and refills it via [loadHouseSignHtml] when the name
     * or version changes). UI thread only.
     */
    private fun showHouseSign() {
        val pose = Pose(t = Vector3(panelAnchor.x + 0.3f, HOUSE_SIGN_Y, panelAnchor.z - PANEL_DISTANCE))
        val existing = houseSignEntity
        if (existing != null) {
            existing.setComponent(Transform(pose))
            existing.setComponent(Visible(true))
            loadHouseSignHtml()
            return
        }
        val entity = Entity.create()
        entity.setComponent(Panel(R.layout.house_sign))
        entity.setComponent(Transform(pose))
        entity.setComponent(Grabbable())
        entity.setComponent(Visible(true))
        houseSignEntity = entity
    }

    private fun destroyHouseSign() {
        houseSignEntity?.destroy()
        houseSignEntity = null
        houseSignWebView = null
    }

    private fun loadHouseSignHtml() {
        val wv = houseSignWebView ?: return
        // Names come from the LLM or the dashboard.
        val name = (currentHouseName ?: "Generated House")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        val details = buildList {
            currentFloorPlanVersion?.let { add("Floor plan v$it") }
            if (currentProjectId != null) add("Hold grip to change the floor plan")
        }.joinToString(" • ")
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:10px 18px;background:rgba(20,20,40,0.9);
                border-radius:14px;display:flex;flex-direction:column;justify-content:center;
                align-items:center;height:100vh;box-sizing:border-box;font-family:sans-serif;color:#fff;">
              <p style="margin:0;font-size:12px;letter-spacing:2px;color:#64B5F6;">NOW VIEWING</p>
              <p style="margin:4px 0;font-size:30px;font-weight:bold;text-align:center;">🏠 $name</p>
              <p style="margin:0;font-size:14px;opacity:0.75;text-align:center;">$details</p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    /** A fresh progress bar in front of the player (at [panelAnchor]). */
    private fun showProgressBar() {
        progressBar?.destroy()
        progressBar = VRProgressBar(position = progressBarPosition())
        progressBar?.reset()
        progressBar?.setStateColor(VRProgressBar.ProgressState.GENERATING)
        progressBar?.show()
    }

    /**
     * Hide and destroy the current progress bar after [delayMs]. Captures this bar,
     * so a new one shown in the meantime is left alone.
     */
    private fun dismissProgressBar(delayMs: Long) {
        val bar = progressBar ?: return
        android.os.Handler(Looper.getMainLooper()).postDelayed({
            bar.hide()
            bar.destroy()
            if (progressBar === bar) progressBar = null
        }, delayMs)
    }

    private fun failGeometryGeneration(reason: String) {
        progressBar?.setStateColor(VRProgressBar.ProgressState.ERROR)
        dismissProgressBar(2000)
        voiceState = VoiceState.IDLE
        showPanel()
        dashboardWebView?.let { loadErrorHtml(it, reason) }
    }

    /**
     * Prompt 2: user confirmed the house-look description — request a 2D image from the
     * backend. Shows a progress bar while generating; on completion, transitions to
     * REVIEWING_IMAGE so the user can Accept / Edit / Start Over.
     */
    private fun onConfirmPrompt2() {
        val text = pendingTranscription
        Log.i(TAG, "✅ Prompt 2 confirmed (house look): '$text'")
        currentImagePrompt = text
        voiceState = VoiceState.GENERATING_IMAGE
        showProgressBar()
        // Covers the window between the POST and the progress socket opening.
        armGenerationWatchdog()

        activityScope.launch(Dispatchers.IO) {
            try {
                val body = JSONObject()
                    .put("prompt", text)
                    .toString()
                    .toRequestBody("application/json".toMediaType())

                var generationId = ""
                httpClient.newCall(
                    Request.Builder()
                        .url("$SERVER_URL/api/v1/image/generate")
                        .post(body)
                        .build()
                ).execute().use { response ->
                    if (response.isSuccessful) {
                        val json = JSONObject(response.body?.string() ?: "{}")
                        generationId = json.optString("generation_id", "")
                        Log.i(TAG, "🎨 Image generation started: id=$generationId")
                    } else {
                        Log.e(TAG, "❌ /image/generate failed: HTTP ${response.code}")
                    }
                }

                if (generationId.isBlank()) {
                    runOnUiThread { abortImageGeneration("Server did not start a generation") }
                    return@launch
                }

                runOnUiThread {
                    // The watchdog may have aborted while the POST was in flight.
                    if (voiceState != VoiceState.GENERATING_IMAGE) {
                        Log.w(TAG, "⏭️ Generation $generationId started after abort — discarding")
                        deleteGeneratedImage(generationId)
                        return@runOnUiThread
                    }
                    currentImageGenerationId = generationId
                    connectGenerationWebSocket(generationId)
                }

            } catch (e: Exception) {
                Log.e(TAG, "❌ Prompt 2 image generation failed", e)
                runOnUiThread {
                    abortImageGeneration(e.message ?: "Could not reach the server")
                }
            }
        }
    }

    /**
     * Floor-plan change confirmed: the backend revises the saved plan (a new version)
     * and the house is rebuilt from it. The player returns to the spawn point, since
     * walls may now stand where they were. Failure keeps the current house.
     */
    private fun onConfirmRefine() {
        val text = pendingTranscription
        val projectId = currentProjectId
        if (projectId == null) {
            Log.w(TAG, "⚠️ Refinement confirmed without a saved house")
            returnFromRefine()
            return
        }
        Log.i(TAG, "✅ Floor-plan change confirmed: '$text'")
        hidePanel()
        voiceState = VoiceState.REFINING_GEOMETRY
        showProgressBar()

        activityScope.launch(Dispatchers.IO) {
            val geometry = houseGenerator?.refineFloorPlan(projectId, text)
            runOnUiThread {
                if (voiceState != VoiceState.REFINING_GEOMETRY) return@runOnUiThread
                if (geometry == null) {
                    progressBar?.setStateColor(VRProgressBar.ProgressState.ERROR)
                    dismissProgressBar(2000)
                    returnFromRefine()
                    showPanel()  // also while walking, so the error is seen
                    dashboardWebView?.let { loadRefineHintHtml(it, "Could not change the floor plan") }
                    return@runOnUiThread
                }
                enterHouse(geometry)
                progressBar?.setProgressPercentage(100)
                progressBar?.setStateColor(VRProgressBar.ProgressState.COMPLETE)
                dismissProgressBar(1500)
                returnFromRefine()
                dashboardWebView?.let { loadRefineHintHtml(it, null) }
            }
        }
    }

    /**
     * Back to where the refinement started: walking with the accepted image (re-spawned,
     * since rebuilding the house removes it), or the prompt-2 panel. UI thread only.
     */
    private fun returnFromRefine() {
        voiceState = refineReturnState
        if (voiceState == VoiceState.WALKING && currentImageUrl != null) {
            hidePanel()
            if (walkingImagePanelEntity == null) spawnWalkingImagePanel(panelAnchor)
        } else {
            voiceState = VoiceState.READY_FOR_PROMPT2
            showPanel()
        }
    }

    /** Prompt-2 panel, with [error] (if any) from the last floor-plan change on top. */
    private fun loadRefineHintHtml(wv: WebView, error: String?) {
        if (error == null) {
            loadPrompt2Html(wv)
            return
        }
        val safe = error.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:24px;color:#EF5350;margin-bottom:12px;">⚠️ $safe</p>
              <p style="font-size:18px;color:#AAAAAA;text-align:center;">
                The house is unchanged. Hold the <strong style="color:white;">grip</strong> to try
                another change, or <strong style="color:white;">A</strong> to describe the look.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    internal fun onRetryTranscription() {
        Log.i(TAG, "🔄 User retried — ready to record again")
        if (voiceState == VoiceState.CONFIRMING_REFINE) {
            returnFromRefine()
            dashboardWebView?.let { loadRefineHintHtml(it, null) }
            return
        }
        val wasPrompt2 = voiceState == VoiceState.CONFIRMING_TEXT2
        voiceState = if (wasPrompt2) VoiceState.READY_FOR_PROMPT2 else VoiceState.IDLE
        val wv = dashboardWebView ?: return
        if (wasPrompt2) loadPrompt2Html(wv) else loadIdleHtml(wv)
    }

    /**
     * Spawn a world-space entity holding the confirmed 2D image near the player's
     * spawn point, so the image stays visible while the user walks the floor plan.
     * Destroys any prior walking image panel first.
     */
    private fun spawnWalkingImagePanel(spawnPos: Vector3?) {
        walkingImagePanelEntity?.destroy()
        walkingImagePanelEntity = null
        walkingImageWebView = null

        val anchor = spawnPos ?: Vector3(0f, 0f, 0f)
        val entity = Entity.create()
        entity.setComponent(Panel(R.layout.image_panel))
        entity.setComponent(Transform(Pose(
            t = Vector3(anchor.x, 1.6f, anchor.z - (PANEL_DISTANCE - 0.2f)),
            q = com.meta.spatial.core.Quaternion(0f, 0f, 0f)
        )))
        entity.setComponent(Grabbable())
        entity.setComponent(Visible(true))
        walkingImagePanelEntity = entity
        Log.i(TAG, "🖼️ Walking image panel entity spawned at (${anchor.x}, 1.6, ${anchor.z - (PANEL_DISTANCE - 0.2f)})")
    }

    private fun loadWalkingImageHtml(imageUrl: String) {
        val wv = walkingImageWebView ?: return
        val html = """
            <!DOCTYPE html><html>
            <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin:0;padding:0;background:#000;display:flex;
                         justify-content:center;align-items:center;height:100vh;">
              <img src="$imageUrl" alt="Design"
                   style="max-width:100%;max-height:100%;object-fit:contain;" />
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL("$SERVER_URL/", html, "text/html", "UTF-8", null)
    }

    /**
     * Spawn the dedicated review panel holding the generated 2D image. The panel { }
     * callback fires asynchronously after Entity.create(), so the URL is stashed in
     * pendingReviewImageUrl and loaded by whichever of the two runs second.
     */
    private fun spawnReviewImagePanel(imageUrl: String) {
        destroyReviewImagePanel()
        pendingReviewImageUrl = imageUrl

        val entity = Entity.create()
        entity.setComponent(Panel(R.layout.review_image_panel))
        entity.setComponent(Transform(Pose(
            t = Vector3(panelAnchor.x + REVIEW_PANEL_X, REVIEW_PANEL_Y, panelAnchor.z + REVIEW_PANEL_Z)
        )))
        entity.setComponent(Grabbable())
        entity.setComponent(Visible(true))
        reviewImagePanelEntity = entity
        Log.i(TAG, "🖼️ Review image panel spawned at ($REVIEW_PANEL_X, $REVIEW_PANEL_Y, $REVIEW_PANEL_Z) size ${REVIEW_PANEL_SIZE}m")
    }

    private fun loadReviewImageHtml(imageUrl: String) {
        val wv = reviewImageWebView ?: return
        pendingReviewImageUrl = null
        val html = """
            <!DOCTYPE html><html>
            <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin:0;padding:0;background:#000;display:flex;
                         justify-content:center;align-items:center;height:100vh;">
              <img src="$imageUrl" alt="Generated design"
                   style="max-width:100%;max-height:100%;object-fit:contain;" />
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL("$SERVER_URL/", html, "text/html", "UTF-8", null)
        Log.i(TAG, "🖼️ Review image loaded: $imageUrl")
    }

    private fun destroyReviewImagePanel() {
        reviewImagePanelEntity?.destroy()
        reviewImagePanelEntity = null
        reviewImageWebView = null
        pendingReviewImageUrl = null
    }

    private fun destroyWalkingImagePanel() {
        walkingImagePanelEntity?.destroy()
        walkingImagePanelEntity = null
        walkingImageWebView = null
    }

    /**
     * Fire-and-forget DELETE /api/v1/image/{id} — cleans up the image file on the backend
     * when the user picks Edit Prompt or Start Over during image review.
     */
    private fun deleteGeneratedImage(generationId: String) {
        if (generationId.isBlank()) return
        activityScope.launch(Dispatchers.IO) {
            try {
                httpClient.newCall(
                    Request.Builder()
                        .url("$SERVER_URL/api/v1/image/$generationId")
                        .delete()
                        .build()
                ).execute().use { response ->
                    Log.i(TAG, "🗑️ DELETE /image/$generationId → HTTP ${response.code}")
                }
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Failed to delete image $generationId: ${e.message}")
            }
        }
    }

    /**
     * Load a saved project (sent from the dashboard), replacing any house already in
     * the scene. With [generationId] — the image the backend started for it — the
     * image is shown for review once ready, exactly like step 2 of the voice flow;
     * without one, the user is asked to describe the look. UI thread only.
     */
    fun loadProjectById(projectId: Int, generationId: String? = null) {
        val busy = isRecording || transcribing ||
            voiceState == VoiceState.GENERATING_GEOMETRY || voiceState == VoiceState.GENERATING_IMAGE ||
            voiceState == VoiceState.REFINING_GEOMETRY
        if (busy) {
            Log.w(TAG, "⏭️ loadProjectById($projectId) ignored — busy ($voiceState)")
            return
        }
        Log.i(TAG, "🔃 Loading project $projectId from backend (image=$generationId)…")
        activityScope.launch(Dispatchers.IO) {
            try {
                val geometry = houseGenerator?.fetchVRGeometry(projectId)
                if (geometry == null) {
                    Log.w(TAG, "⚠️ fetchVRGeometry returned null for project $projectId")
                    return@launch
                }
                runOnUiThread {
                    // An image still under review would otherwise be orphaned on disk.
                    if (voiceState == VoiceState.REVIEWING_IMAGE) discardGeneratedImage()
                    clearHouse()
                    enterHouse(geometry)
                    showPanel()
                    if (generationId != null) {
                        voiceState = VoiceState.GENERATING_IMAGE
                        currentImageGenerationId = generationId
                        showProgressBar()
                        armGenerationWatchdog()
                        connectGenerationWebSocket(generationId)
                        dashboardWebView?.let { loadRenderingHtml(it) }
                    } else {
                        voiceState = VoiceState.READY_FOR_PROMPT2
                        dashboardWebView?.let { loadPrompt2Html(it) }
                    }
                    val projectName = geometry.optString("project_name", "Project $projectId")
                    Log.i(TAG, "✅ Project loaded: '$projectName' (id=$projectId)")
                }
            } catch (e: Exception) {
                Log.e(TAG, "❌ loadProjectById($projectId) failed", e)
            }
        }
    }

    private fun loadListeningHtml(wv: WebView) {
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:24px;color:#EF5350;margin-bottom:16px;">🎙️ Listening…</p>
              <p style="font-size:18px;color:#AAAAAA;text-align:center;">
                Say what to change in the floor plan, then release the grip.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    private fun loadRenderingHtml(wv: WebView) {
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:24px;color:#64B5F6;margin-bottom:16px;">🎨 Rendering the house…</p>
              <p style="font-size:18px;color:#AAAAAA;text-align:center;">
                Look around while the image is generated — it will appear for review.
              </p>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    private fun handleTeleportation(pose: Pose) {
        val forward = pose.q * Vector3(0f, 0f, -1f)
        if (forward.y >= 0f) return  // must aim downward toward floor
        val t = -pose.t.y / forward.y  // parametric distance to y=0 plane
        if (t < 0.3f || t > 20.0f) return  // too close or too far
        val tx = pose.t.x + forward.x * t
        val tz = pose.t.z + forward.z * t
        scene.setViewOrigin(tx, 0f, tz, 0f)
        Log.i(TAG, "🌀 Teleported to (${"%.1f".format(tx)}, ${"%.1f".format(tz)})")
    }

    private fun toggleXRay() {
        xrayEnabled = !xrayEnabled
        houseGenerator?.setXRayEnabled(xrayEnabled)
        Log.i(TAG, "🔍 X-ray ${if (xrayEnabled) "ON" else "OFF"}")
    }

    private fun toggleRoomLabels() {
        roomLabelsVisible = !roomLabelsVisible
        if (roomLabelsVisible) {
            val rooms = houseGenerator?.getRoomInfoList() ?: emptyList()
            if (rooms.isEmpty()) {
                Log.w(TAG, "⚠️ No room data for labels — house not loaded yet?")
                roomLabelsVisible = false
                return
            }
            // Queue room info for the panel callbacks
            pendingRoomLabels.clear()
            pendingRoomLabels.addAll(rooms)

            rooms.forEach { room ->
                // Label floats at eye level in the middle of the room. (room.depth used to
                // arrive as 0, which put it here; keep it off the walls now that they have doorways.)
                val labelZ = room.centerZ
                val entity = Entity.create()
                entity.setComponent(Panel(R.layout.room_label))
                entity.setComponent(Transform(Pose(
                    t = Vector3(room.centerX, 1.6f, labelZ),
                    q = com.meta.spatial.core.Quaternion(0f, 180f, 0f)
                )))
                entity.setComponent(Visible(true))
                roomLabelEntities.add(entity)
            }
            Log.i(TAG, "🏷️ Room labels shown: ${rooms.size}")
        } else {
            roomLabelEntities.forEach { it.destroy() }
            roomLabelEntities.clear()
            Log.i(TAG, "🏷️ Room labels hidden")
        }
    }

    /**
     * Show the generated 2D image with three review buttons: Accept, Edit Prompt, Start Over.
     * Wired to the `ReviewInterface` JS bridge registered on dashboardWebView.
     */
    private fun displayReviewPanel(imageUrl: String) {
        Log.i(TAG, "🖼️ Review panel for: $imageUrl")

        // The image gets its own, larger panel; the prompt panel keeps the controls.
        spawnReviewImagePanel(imageUrl)

        val wv = dashboardWebView
        if (wv == null) {
            Log.e(TAG, "❌ dashboardWebView is null, cannot show review controls")
            return
        }
        val html = """
            <!DOCTYPE html><html>
            <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin:0;padding:20px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="color:#64B5F6;font-size:14px;margin:0 0 6px;">Step 2 of 2 — Review image</p>
              <p style="color:#AAAAAA;font-size:17px;margin:0 0 20px;text-align:center;">
                Your design is on the large panel to the right.
              </p>
              <p style="color:#AAAAAA;font-size:15px;margin:0 0 18px;text-align:center;">
                <strong style="color:white;">A</strong> = Accept •
                <strong style="color:white;">B</strong> = Edit Prompt
              </p>
              <div style="display:flex;gap:10px;width:100%;">
                <button onclick="try { Android.editPrompt(); } catch(e){}"
                  style="flex:1;background:#F9A825;color:#1A1A2E;font-size:18px;
                         padding:14px;border:none;border-radius:8px;cursor:pointer;font-weight:bold;">
                  Edit Prompt
                </button>
                <button onclick="try { Android.acceptImage(); } catch(e){}"
                  style="flex:1;background:#2E7D32;color:white;font-size:18px;
                         padding:14px;border:none;border-radius:8px;cursor:pointer;font-weight:bold;">
                  Accept
                </button>
              </div>
              <button onclick="try { Android.startOver(); } catch(e){}"
                style="margin-top:10px;width:100%;background:#B71C1C;color:white;font-size:16px;
                       padding:12px;border:none;border-radius:8px;cursor:pointer;">
                Start Over
              </button>
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    internal fun onAcceptImage() {
        Log.i(TAG, "✅ Image accepted — walking the floor plan")
        destroyReviewImagePanel()
        // The prompt panel would sit where the walking image panel spawns.
        hidePanel()
        spawnWalkingImagePanel(panelAnchor)
        voiceState = VoiceState.WALKING
        linkAcceptedImage()
    }

    /** Record the accepted image on the house's current floor plan (fire-and-forget). */
    private fun linkAcceptedImage() {
        val projectId = currentProjectId ?: return
        val generationId = currentImageGenerationId ?: return
        val path = currentImagePath ?: return
        activityScope.launch(Dispatchers.IO) {
            try {
                val body = JSONObject()
                    .put("generation_id", generationId)
                    .put("image_url", path)
                    .toString()
                    .toRequestBody("application/json".toMediaType())
                httpClient.newCall(
                    Request.Builder()
                        .url("$SERVER_URL/api/v1/projects/$projectId/floor-plan/image")
                        .put(body)
                        .build()
                ).execute().use { response ->
                    Log.i(TAG, "🔗 Image $generationId linked to project $projectId → HTTP ${response.code}")
                }
            } catch (e: Exception) {
                Log.w(TAG, "⚠️ Could not link image to project $projectId: ${e.message}")
            }
        }
    }

    internal fun onEditPrompt() {
        Log.i(TAG, "✏️ Edit Prompt — deleting previous image and re-recording prompt 2")
        discardGeneratedImage()
        dashboardWebView?.let { loadPrompt2Html(it) }
        voiceState = VoiceState.READY_FOR_PROMPT2
    }

    internal fun onStartOver() {
        Log.i(TAG, "🔄 Start Over — deleting image, clearing house, returning to idle")
        discardGeneratedImage()
        clearHouse()
    }

    private fun discardGeneratedImage() {
        destroyReviewImagePanel()
        currentImageGenerationId?.let { deleteGeneratedImage(it) }
        currentImageGenerationId = null
        currentImagePrompt = null
        currentImageUrl = null
        currentImagePath = null
    }

    /** Remove the generated house and its panels and return to step 1. UI thread only. */
    private fun clearHouse() {
        houseGenerator?.clearAllEntities()
        roomLabelEntities.forEach { it.destroy() }
        roomLabelEntities.clear()
        roomLabelsVisible = false
        destroyReviewImagePanel()
        destroyWalkingImagePanel()
        locomotionEnabled = false
        voiceState = VoiceState.IDLE
        currentImageGenerationId = null
        currentImagePrompt = null
        currentImageUrl = null
        currentImagePath = null
        currentProjectId = null
        currentHouseName = null
        currentFloorPlanVersion = null
        destroyHouseSign()
        panelAnchor = Vector3(0f, 0f, 0f)
        placePromptPanel()
        webPanelEntity?.setComponent(Transform(Pose(t = Vector3(-1.9f, 1.1f, -PANEL_DISTANCE))))
        showPanel()
        dashboardWebView?.let { loadIdleHtml(it) }
    }

    private fun placePromptPanel() {
        dashboardPanelEntity?.setComponent(Transform(Pose(
            t = Vector3(panelAnchor.x + 0.3f, 1.1f, panelAnchor.z - PANEL_DISTANCE)
        )))
    }

    private fun progressBarPosition() = Vector3(panelAnchor.x, 1.5f, panelAnchor.z - 1.0f)

    private fun loadPrompt2Html(wv: WebView) {
        val refineHint = if (currentProjectId != null) """
              <p style="font-size:15px;color:#888;text-align:center;margin-top:14px;">
                Want a different layout? Hold the <strong style="color:white;">grip</strong> and say
                what to change — "make the kitchen bigger".
              </p>""" else ""
        val html = """
            <!DOCTYPE html><html>
            <body style="margin:0;padding:32px;background:#1A1A2E;color:white;
                         font-family:sans-serif;display:flex;flex-direction:column;
                         align-items:center;justify-content:center;height:100vh;box-sizing:border-box;">
              <p style="font-size:14px;color:#64B5F6;margin:0 0 4px;">Step 2 of 2</p>
              <p style="font-size:24px;color:#64B5F6;margin-bottom:16px;">🎨 House Look</p>
              <p style="font-size:18px;color:#AAAAAA;text-align:center;">
                Hold <strong style="color:white;">A</strong> and describe how the house
                should look — style, materials, colours.
              </p>
              $refineHint
            </body></html>
        """.trimIndent()
        wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
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
    override fun registerFeatures(): List<SpatialFeature> {
        return listOf(VRFeature(this), CastInputForwardFeature(this))
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
            
            houseGenerator = HouseGenerator(SERVER_URL)
            
            // Connect to real-time collaboration room
            connectToRoom("tiny_house_room", "quest_user_${System.currentTimeMillis() % 1000}")
            
            isInitialized = true
        } catch (e: Exception) {
            Log.e(TAG, "Initialization failed", e)
        }
    }

    override fun onDestroy() {
        if (isRecording) voiceController?.cancel()
        cancelGenerationWatchdog()
        roomWebSocket?.close(1000, "Activity destroyed")
        generationWebSocket?.close(1000, "Activity destroyed")
        progressBar?.destroy()
        progressBar = null
        dashboardPanelEntity?.destroy()
        dashboardPanelEntity = null
        dashboardWebView = null
        destroyReviewImagePanel()
        destroyWalkingImagePanel()
        broadcastReceiver?.let { unregisterReceiver(it) }
        nativeEntities.values.forEach { it.destroy() }
        roomLabelEntities.forEach { it.destroy() }
        roomLabelEntities.clear()
        houseGenerator?.clearAllEntities()
        activityJob.cancel()
        super.onDestroy()
    }

    private fun connectToRoom(roomId: String, userId: String) {
        val token = BuildConfig.COLLAB_TOKEN
        val query = "user_id=$userId" + if (token.isNotEmpty()) "&token=$token" else ""
        val request = Request.Builder()
            .url("$WS_URL/room/$roomId?$query")
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

        // ❌ REMOVED: Auto-load on startup - projects now loaded explicitly via dashboard
        // android.os.Handler(Looper.getMainLooper()).postDelayed({ loadLatestProject() }, 2000)

        // Create the dashboard panel entity programmatically so the panel { } callback fires.
        // Scene-defined panel entities do NOT trigger panel { } — only Entity.create() does.
        Log.i(TAG, "📺 Creating dashboard panel entity programmatically")
        val panelEntity = Entity.create()
        panelEntity.setComponent(Panel(R.layout.ui_example))
        panelEntity.setComponent(Transform(Pose(t = Vector3(0.3f, 1.1f, -PANEL_DISTANCE))))
        panelEntity.setComponent(Grabbable())
        panelEntity.setComponent(Visible(true))
        dashboardPanelEntity = panelEntity
        Log.i(TAG, "📺 Dashboard panel entity created: $panelEntity")

        // Create the Vue/Quasar web panel to the left of the speak panel.
        // Speak panel is 1.2f wide centered at x=0.3f; place new panel 0.1f gap to its left.
        Log.i(TAG, "🌐 Creating web panel entity programmatically")
        val webPanelEntityLocal = Entity.create()
        webPanelEntityLocal.setComponent(Panel(R.layout.web_panel))
        webPanelEntityLocal.setComponent(Transform(Pose(t = Vector3(-1.9f, 1.1f, -PANEL_DISTANCE))))
        webPanelEntityLocal.setComponent(Grabbable())
        webPanelEntityLocal.setComponent(Visible(true))
        webPanelEntity = webPanelEntityLocal
        Log.i(TAG, "🌐 Web panel entity created: $webPanelEntityLocal")
    }

    inner class ConstructionInputSystem : SystemBase() {
        private var grabbedElementId = -1
        private var grabOffset = Vector3(0f)
        private val leftState = ControllerState()
        private val rightState = ControllerState()
        private var xrayDebounceTimer = 0L
        private var teleportDebounceTimer = 0L
        private var roomLabelDebounceTimer = 0L
        private var prevButtonB = false
        private var gripDebounceTimer = 0L

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
            if (locomotionEnabled) {
                // Explore mode: X = toggle x-ray, Y = toggle room label beacons
                val now = System.currentTimeMillis()
                if (state.buttonX && (now - xrayDebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    xrayDebounceTimer = now
                    toggleXRay()
                }
                if (state.buttonY && (now - roomLabelDebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    roomLabelDebounceTimer = now
                    toggleRoomLabels()
                }
            } else {
                // Construction mode: grip = grab/move, X = delete
                handleGrabAndMove(state)
                if (state.buttonX) handleDeletion(state.pose)
            }
        }

        private fun processRightController(state: ControllerState, controllerEntity: Entity) {
            // Sampled before handleVoiceInput, which may move a Retry/Edit press into a
            // clearable state within this same frame.
            val stateBefore = voiceState
            val bPressed = state.buttonB && !prevButtonB
            prevButtonB = state.buttonB
            handleVoiceInput(state, controllerEntity)
            if (locomotionEnabled) {
                // Explore mode: trigger = teleport, B = clear house
                val now = System.currentTimeMillis()
                if (state.trigger && (now - teleportDebounceTimer > 300L)) {
                    teleportDebounceTimer = now
                    handleTeleportation(state.pose)
                }
                // B means Retry / Edit Prompt during confirm and review, and clearing
                // mid-generation would orphan the in-flight request — only clear when idle.
                // Edge-triggered so a B held through Retry does not then clear the house.
                val canClear = stateBefore == VoiceState.IDLE ||
                    stateBefore == VoiceState.READY_FOR_PROMPT2 ||
                    stateBefore == VoiceState.WALKING
                if (canClear && bPressed) {
                    Log.i(TAG, "🗑️ Button B — clearing house")
                    runOnUiThread { clearHouse() }
                }
            } else {
                // Construction mode: trigger = place element, B = delete
                if (state.trigger) handlePlacement(state.pose)
                if (state.buttonB) handleDeletion(state.pose)
            }
        }

        private fun handleVoiceInput(state: ControllerState, controllerEntity: Entity) {
            val now = System.currentTimeMillis()

            // Text confirmation (prompt 1 or prompt 2): A = confirm, B = retry
            if (voiceState == VoiceState.CONFIRMING_TEXT1 ||
                voiceState == VoiceState.CONFIRMING_TEXT2) {
                if (state.buttonA && (now - buttonADebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    buttonADebounceTimer = now
                    Log.i(TAG, "✅ Button A — confirming text via controller")
                    onConfirmTranscription()
                }
                if (state.buttonB && (now - buttonBDebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    buttonBDebounceTimer = now
                    Log.i(TAG, "🔄 Button B — retrying text via controller")
                    onRetryTranscription()
                }
                return
            }

            // Image review: A = accept, B = edit prompt. Start Over is HTML-only.
            if (voiceState == VoiceState.REVIEWING_IMAGE) {
                if (state.buttonA && (now - buttonADebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    buttonADebounceTimer = now
                    Log.i(TAG, "✅ Button A — accepting image via controller")
                    runOnUiThread { onAcceptImage() }
                }
                if (state.buttonB && (now - buttonBDebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    buttonBDebounceTimer = now
                    Log.i(TAG, "✏️ Button B — edit prompt via controller")
                    runOnUiThread { onEditPrompt() }
                }
                return
            }

            // Text confirmation of a floor-plan change: same buttons.
            if (voiceState == VoiceState.CONFIRMING_REFINE) {
                if (state.buttonA && (now - buttonADebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    buttonADebounceTimer = now
                    onConfirmTranscription()
                }
                if (state.buttonB && (now - buttonBDebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    buttonBDebounceTimer = now
                    onRetryTranscription()
                }
                return
            }

            // Block input while generating image or geometry
            if (voiceState == VoiceState.GENERATING_IMAGE ||
                voiceState == VoiceState.GENERATING_GEOMETRY ||
                voiceState == VoiceState.REFINING_GEOMETRY) return

            // Hold the right grip inside a saved house to say how to change its floor plan.
            if (handleRefineRecording(state, controllerEntity, now)) return

            // Voice recording in IDLE (prompt 1) or READY_FOR_PROMPT2 (prompt 2).
            // Also allow the active RECORDING_* states through so we can detect button release.
            val canRecord = voiceState == VoiceState.IDLE ||
                voiceState == VoiceState.READY_FOR_PROMPT2 ||
                voiceState == VoiceState.RECORDING_PROMPT1 ||
                voiceState == VoiceState.RECORDING_PROMPT2
            if (!canRecord) return

            // Waiting for the last recording's transcription.
            if (transcribing) return

            if (state.buttonA) {
                buttonADebounceTimer = now
                if (!isRecording) {
                    isRecording = true
                    voiceState = if (voiceState == VoiceState.READY_FOR_PROMPT2) {
                        VoiceState.RECORDING_PROMPT2
                    } else {
                        VoiceState.RECORDING_PROMPT1
                    }
                    voiceController?.startRecording()
                    showVoiceIndicator(controllerEntity, state.pose, true)
                }
            } else {
                if (isRecording && (now - buttonADebounceTimer > DEBOUNCE_TIMEOUT_MS)) {
                    isRecording = false
                    transcribing = true
                    // Which prompt this was is fixed now, not when Whisper answers.
                    val phase = if (voiceState == VoiceState.RECORDING_PROMPT2) 2 else 1
                    val controller = voiceController
                    if (controller == null) {
                        failTranscription(phase, "Microphone unavailable")
                    } else {
                        controller.stopRecording { audio ->
                            transcribeAudio(audio, controller.sampleRate, phase)
                        }
                    }
                    showVoiceIndicator(null, state.pose, false)
                }
            }

        }

        /** Returns true when the grip recording consumed this frame's input. */
        private fun handleRefineRecording(state: ControllerState, controllerEntity: Entity, now: Long): Boolean {
            if (voiceState == VoiceState.RECORDING_REFINE) {
                // Released and stopped: wait here for the transcription.
                if (!isRecording) return true
                if (state.grip) {
                    gripDebounceTimer = now
                } else if (now - gripDebounceTimer > DEBOUNCE_TIMEOUT_MS) {
                    isRecording = false
                    transcribing = true
                    val controller = voiceController
                    if (controller == null) {
                        failTranscription(PHASE_REFINE, "Microphone unavailable")
                    } else {
                        controller.stopRecording { audio ->
                            transcribeAudio(audio, controller.sampleRate, PHASE_REFINE)
                        }
                    }
                    showVoiceIndicator(null, state.pose, false)
                }
                return true
            }
            val canRefine = currentProjectId != null && !isRecording && !transcribing &&
                (voiceState == VoiceState.READY_FOR_PROMPT2 || voiceState == VoiceState.WALKING)
            if (!canRefine || !state.grip || state.buttonA) return false
            gripDebounceTimer = now
            isRecording = true
            refineReturnState = voiceState
            voiceState = VoiceState.RECORDING_REFINE
            Log.i(TAG, "🎙️ Grip held — recording a floor-plan change")
            voiceController?.startRecording()
            showVoiceIndicator(controllerEntity, state.pose, true)
            if (refineReturnState == VoiceState.WALKING) showPanel()
            dashboardWebView?.let { loadListeningHtml(it) }
            return true
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
            entity.setComponent(centeredBox(Vector3(dx, dy, dz)))

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

    inner class ConfirmationInterface {
        @JavascriptInterface
        fun confirm() = runOnUiThread { onConfirmTranscription() }

        @JavascriptInterface
        fun retry() = runOnUiThread { onRetryTranscription() }

        @JavascriptInterface
        fun acceptImage() = runOnUiThread { onAcceptImage() }

        @JavascriptInterface
        fun editPrompt() = runOnUiThread { onEditPrompt() }

        @JavascriptInterface
        fun startOver() = runOnUiThread { onStartOver() }
    }

    inner class VoiceController {
        private var audioRecord: AudioRecord? = null
        // Read by the recording thread every loop; must be visible across threads.
        @Volatile private var isRecording = false
        private var recordingThread: Thread? = null
        // Filled only by the recording thread; read only after that thread has ended.
        private var chunks = mutableListOf<ShortArray>()
        val sampleRate = 16000
        private val channelConfig = AudioFormat.CHANNEL_IN_MONO
        private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
        private var bufferSize =
            AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat).let {
                if (it > 0) it else 2048
            }

        @SuppressLint("MissingPermission")
        fun startRecording() {
            if (isRecording) return

            if (ContextCompat.checkSelfPermission(
                    this@ImmersiveActivity,
                    Manifest.permission.RECORD_AUDIO
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                Log.e(TAG, "🎙️ Permission denied: RECORD_AUDIO")
                return
            }

            try {
                val record = AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate,
                    channelConfig,
                    audioFormat,
                    bufferSize
                )
                if (record.state != AudioRecord.STATE_INITIALIZED) {
                    Log.e(TAG, "🎙️ AudioRecord failed to initialize")
                    record.release()
                    return
                }

                val captured = mutableListOf<ShortArray>()
                chunks = captured
                audioRecord = record
                record.startRecording()
                isRecording = true
                recordingThread = Thread {
                    val data = ShortArray(bufferSize)
                    while (isRecording) {
                        val read = try {
                            record.read(data, 0, bufferSize)
                        } catch (e: Exception) {
                            Log.e(TAG, "Read error", e)
                            break
                        }
                        if (read > 0) captured.add(data.copyOf(read))
                    }
                }.also { it.start() }
                Log.i(TAG, "🎙️ Voice recording started")
            } catch (e: Exception) {
                Log.e(TAG, "❌ Failed to start recording", e)
            }
        }

        /**
         * Stop recording and hand the captured audio to [onFinished] on a background
         * thread. Always calls [onFinished] — with an empty array if nothing was
         * recorded — so the caller's state can't get stuck waiting.
         */
        fun stopRecording(onFinished: (ShortArray) -> Unit) {
            val wasRecording = isRecording
            isRecording = false
            val record = audioRecord
            val thread = recordingThread
            val captured = chunks
            audioRecord = null
            recordingThread = null

            activityScope.launch(Dispatchers.IO) {
                var audio = ShortArray(0)
                try {
                    if (wasRecording && record != null) {
                        // stop() unblocks a pending read(), so the thread ends promptly.
                        if (record.recordingState == AudioRecord.RECORDSTATE_RECORDING) record.stop()
                        thread?.join(2000)
                        if (thread?.isAlive == true) {
                            // Never read the buffer while the thread may still append to it.
                            Log.e(TAG, "🎙️ Recording thread did not stop — discarding audio")
                        } else {
                            audio = ShortArray(captured.sumOf { it.size })
                            var offset = 0
                            for (chunk in captured) {
                                chunk.copyInto(audio, offset)
                                offset += chunk.size
                            }
                        }
                        record.release()
                    }
                    Log.i(TAG, "🎙️ Voice recording stopped: ${audio.size} samples")
                } catch (e: Exception) {
                    Log.e(TAG, "❌ Error during stopRecording", e)
                }
                onFinished(audio)
            }
        }

        /** Stop without transcribing, synchronously (the activity is shutting down). */
        fun cancel() {
            isRecording = false
            val record = audioRecord ?: return
            audioRecord = null
            try {
                if (record.recordingState == AudioRecord.RECORDSTATE_RECORDING) record.stop()
                recordingThread?.join(500)
            } catch (e: Exception) {
                Log.w(TAG, "🎙️ Error stopping recording on shutdown", e)
            } finally {
                recordingThread = null
                record.release()
            }
        }
    }

    override fun registerPanels(): List<PanelRegistration> {
        return listOf(
            PanelRegistration(R.layout.web_panel) {
                config {
                    width = 3.0f
                    height = 2.0f
                    layoutDpi = 250
                }
                panel {
                    val wv = rootView?.findViewById<WebView>(R.id.web_view) ?: return@panel
                    wv.settings.javaScriptEnabled = true
                    wv.settings.domStorageEnabled = true
                    
                    // Add JavaScript interface for dashboard to trigger VR loading
                    wv.addJavascriptInterface(object {
                        @JavascriptInterface
                        fun loadProject(projectId: Int) {
                            Log.i(TAG, "📲 Dashboard requested loadProject($projectId)")
                            runOnUiThread { loadProjectById(projectId) }
                        }

                        /** Load the house and review the image the backend is generating for it. */
                        @JavascriptInterface
                        fun loadProjectWithImage(projectId: Int, generationId: String) {
                            Log.i(TAG, "📲 Dashboard requested loadProjectWithImage($projectId, $generationId)")
                            runOnUiThread { loadProjectById(projectId, generationId) }
                        }
                    }, "Android")
                    
                    Log.i(TAG, "🌐 Web panel JS interface registered - Android.loadProject() available")
                    wv.loadUrl(BuildConfig.DASHBOARD_URL)
                }
            },
            PanelRegistration(R.layout.ui_example) {
                config {
                    width = 1.2f
                    height = 1.2f
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
                    
                    // Configure WebView settings for proper JavaScript interface support
                    wv.settings.apply {
                        javaScriptEnabled = true
                        domStorageEnabled = true
                        javaScriptCanOpenWindowsAutomatically = false
                        allowFileAccess = true
                        allowContentAccess = true
                    }
                    
                    // Enable remote debugging for WebView (helps diagnose issues)
                    WebView.setWebContentsDebuggingEnabled(true)
                    
                    // JS interface enables Android.confirm() / Android.retry() from confirmation HTML
                    wv.addJavascriptInterface(ConfirmationInterface(), "Android")
                    dashboardWebView = wv
                    Log.i(TAG, "✅ dashboardWebView assigned successfully with enhanced settings")

                    // If a voice command finished before the panel was ready, show it now
                    val queued = pendingConfirmationText
                    if (queued != null) {
                        pendingConfirmationText = null
                        val queuedPhase = when (voiceState) {
                            VoiceState.CONFIRMING_TEXT2 -> 2
                            VoiceState.CONFIRMING_REFINE -> PHASE_REFINE
                            else -> 1
                        }
                        Log.i(TAG, "📋 Panel now ready — displaying queued confirmation (phase $queuedPhase): '$queued'")
                        loadConfirmationHtml(queued, queuedPhase)
                    } else {
                        loadIdleHtml(wv)
                    }
                }
            },
            PanelRegistration(R.layout.review_image_panel) {
                config {
                    width = REVIEW_PANEL_SIZE
                    height = REVIEW_PANEL_SIZE
                    layoutDpi = 300
                }
                panel {
                    val wv = rootView?.findViewById<WebView>(R.id.review_web_view) ?: return@panel
                    wv.settings.javaScriptEnabled = false
                    wv.settings.domStorageEnabled = false
                    wv.setBackgroundColor(android.graphics.Color.BLACK)
                    reviewImageWebView = wv
                    Log.i(TAG, "🖼️ Review image panel ready")
                    pendingReviewImageUrl?.let { loadReviewImageHtml(it) }
                }
            },
            PanelRegistration(R.layout.image_panel) {
                config {
                    width = 1.2f
                    height = 1.2f
                    layoutDpi = 300
                }
                panel {
                    val wv = rootView?.findViewById<WebView>(R.id.image_web_view) ?: return@panel
                    wv.settings.javaScriptEnabled = false
                    wv.settings.domStorageEnabled = false
                    wv.setBackgroundColor(android.graphics.Color.BLACK)
                    walkingImageWebView = wv
                    Log.i(TAG, "🖼️ Walking image panel ready")
                    currentImageUrl?.let { loadWalkingImageHtml(it) }
                }
            },
            PanelRegistration(R.layout.house_sign) {
                config {
                    width = HOUSE_SIGN_WIDTH
                    height = HOUSE_SIGN_HEIGHT
                    layoutDpi = 300
                }
                panel {
                    val wv = rootView?.findViewById<WebView>(R.id.house_sign_web_view) ?: return@panel
                    wv.settings.javaScriptEnabled = false
                    wv.setBackgroundColor(android.graphics.Color.TRANSPARENT)
                    houseSignWebView = wv
                    loadHouseSignHtml()
                }
            },
            PanelRegistration(R.layout.room_label) {
                config {
                    width = 0.8f
                    height = 0.4f
                    layoutDpi = 300
                }
                panel {
                    val wv = rootView?.findViewById<WebView>(R.id.label_web_view) ?: return@panel
                    wv.settings.javaScriptEnabled = false
                    wv.setBackgroundColor(android.graphics.Color.TRANSPARENT)
                    val info = pendingRoomLabels.poll() ?: return@panel
                    val sizeText = if (info.width > 0 && info.depth > 0) {
                        // RoomInfo is in scaled world metres; show the real size in feet.
                        val toFt = 1f / (HouseGenerator.SCALE * 0.3048f)
                        String.format("%.0f x %.0f ft", info.width * toFt, info.depth * toFt)
                    } else {
                        ""
                    }
                    // Room names come from the LLM.
                    val name = info.name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    val html = """
                        <!DOCTYPE html><html>
                        <body style="margin:0;padding:12px;background:rgba(20,20,40,0.85);
                            border-radius:12px;display:flex;flex-direction:column;
                            justify-content:center;align-items:center;height:100vh;
                            box-sizing:border-box;font-family:sans-serif;color:#fff;">
                          <p style="margin:0;font-size:28px;font-weight:bold;text-align:center;">
                            $name
                          </p>
                          <p style="margin:6px 0 0;font-size:20px;opacity:0.8;text-align:center;">
                            $sizeText
                          </p>
                        </body></html>
                    """.trimIndent()
                    wv.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
                }
            }
        )
    }
}
