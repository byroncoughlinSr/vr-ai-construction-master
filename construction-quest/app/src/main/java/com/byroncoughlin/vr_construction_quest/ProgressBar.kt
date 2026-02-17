package com.byroncoughlin.vr_construction_quest

import android.util.Log
import androidx.core.net.toUri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible

/**
 * VR Progress Bar for Quest 2
 *
 * Displays image generation progress as a 3D bar with:
 * - Background bar (gray)
 * - Fill bar (green, grows left to right)
 * - Percentage text entity (optional)
 * - Smooth animations
 */
class ProgressBar(
    private val width: Float = 1.0f,
    private val height: Float = 0.05f,
    private val depth: Float = 0.02f,
    private val position: Vector3 = Vector3(0f, 1.5f, -1.0f)
) {
    companion object {
        private const val TAG = "ProgressBar"
    }

    private var rootEntity: Entity? = null
    private var backgroundBar: Entity? = null
    private var fillBar: Entity? = null
    private var textEntity: Entity? = null

    private var currentProgress: Float = 0f
    private var isVisible: Boolean = false

    /**
     * Create the progress bar entities
     */
    fun create() {
        if (rootEntity != null) {
            Log.w(TAG, "⚠️ Progress bar already created")
            return
        }

        Log.i(TAG, "📊 Creating progress bar at position: $position")

        // Root container entity
        rootEntity = Entity.create().apply {
            setComponent(Transform(Pose(t = position)))
            setComponent(Visible(false)) // Start hidden
        }

        // Background bar (gray, full width)
        backgroundBar = Entity.create().apply {
            setComponent(Transform(Pose(t = Vector3(0f, 0f, 0f))))
            setComponent(Mesh(mesh = "mesh://box".toUri()))
            setComponent(com.meta.spatial.toolkit.Box(Vector3(width / 2f, height / 2f, depth / 2f)))
            setComponent(Material().apply {
                baseColor = Color4(0.3f, 0.3f, 0.3f, 0.8f) // Dark gray, semi-transparent
                unlit = true // Don't need lighting for UI
            })
            setComponent(Visible(true))
        }

        // Fill bar (green, grows from left)
        fillBar = Entity.create().apply {
            // Start at left edge, will expand rightward
            val initialOffset = -width / 2f
            setComponent(Transform(Pose(t = Vector3(initialOffset, 0f, depth / 2f + 0.001f))))
            setComponent(Mesh(mesh = "mesh://box".toUri()))
            setComponent(com.meta.spatial.toolkit.Box(Vector3(0.001f, height / 2f, depth / 2f)))
            setComponent(Material().apply {
                baseColor = Color4(0.2f, 0.8f, 0.3f, 1.0f) // Bright green
                unlit = true
            })
            setComponent(Visible(true))
        }

        Log.i(TAG, "✅ Progress bar created successfully")
    }

    /**
     * Show the progress bar
     */
    fun show() {
        if (rootEntity == null) {
            create()
        }

        rootEntity?.setComponent(Visible(true))
        isVisible = true
        Log.i(TAG, "👁️ Progress bar shown")
    }

    /**
     * Hide the progress bar
     */
    fun hide() {
        rootEntity?.setComponent(Visible(false))
        isVisible = false
        Log.i(TAG, "🙈 Progress bar hidden")
    }

    /**
     * Update progress (0.0 to 1.0)
     */
    fun setProgress(progress: Float) {
        if (fillBar == null) {
            Log.w(TAG, "⚠️ Fill bar not created, cannot update progress")
            return
        }

        // Clamp between 0 and 1
        val clampedProgress = progress.coerceIn(0f, 1f)
        currentProgress = clampedProgress

        // Calculate fill bar dimensions
        val fillWidth = width * clampedProgress

        // Position fill bar so it grows from left edge
        val fillOffset = -width / 2f + fillWidth / 2f

        // Update fill bar transform and scale
        fillBar?.let { bar ->
            bar.setComponent(Transform(Pose(t = Vector3(fillOffset, 0f, depth / 2f + 0.001f))))
            bar.setComponent(com.meta.spatial.toolkit.Box(Vector3(fillWidth / 2f, height / 2f, depth / 2f)))
        }

        Log.i(TAG, "📈 Progress updated: ${(clampedProgress * 100).toInt()}%")
    }

    /**
     * Update progress with percentage (0-100)
     */
    fun setProgressPercentage(percentage: Int) {
        setProgress(percentage / 100f)
    }

    /**
     * Reset progress to 0
     */
    fun reset() {
        setProgress(0f)
        Log.i(TAG, "🔄 Progress reset")
    }

    /**
     * Update progress bar color based on status
     */
    fun setColor(color: Color4) {
        fillBar?.let { bar ->
            val material = bar.tryGetComponent<Material>()
            material?.baseColor = color
            material?.let { bar.setComponent(it) }
        }
    }

    /**
     * Set color based on common states
     */
    fun setStateColor(state: ProgressState) {
        val color = when (state) {
            ProgressState.GENERATING -> Color4(0.2f, 0.8f, 0.3f, 1.0f) // Green
            ProgressState.PROCESSING -> Color4(0.3f, 0.6f, 1.0f, 1.0f) // Blue
            ProgressState.COMPLETE -> Color4(0.3f, 1.0f, 0.3f, 1.0f)   // Bright green
            ProgressState.ERROR -> Color4(1.0f, 0.3f, 0.3f, 1.0f)      // Red
            ProgressState.WARNING -> Color4(1.0f, 0.8f, 0.2f, 1.0f)    // Yellow
        }
        setColor(color)
    }

    /**
     * Destroy the progress bar and clean up
     */
    fun destroy() {
        Log.i(TAG, "💥 Destroying progress bar")
        fillBar?.destroy()
        backgroundBar?.destroy()
        textEntity?.destroy()
        rootEntity?.destroy()

        fillBar = null
        backgroundBar = null
        textEntity = null
        rootEntity = null

        currentProgress = 0f
        isVisible = false
    }

    /**
     * Reposition the progress bar in 3D space
     */
    fun setPosition(newPosition: Vector3) {
        rootEntity?.setComponent(Transform(Pose(t = newPosition)))
        Log.i(TAG, "📍 Progress bar repositioned to: $newPosition")
    }

    /**
     * Get current progress (0.0 to 1.0)
     */
    fun getProgress(): Float = currentProgress

    /**
     * Check if progress bar is currently visible
     */
    fun isVisible(): Boolean = isVisible

    enum class ProgressState {
        GENERATING,   // Normal generation (green)
        PROCESSING,   // Processing/transcription (blue)
        COMPLETE,     // Finished (bright green)
        ERROR,        // Error occurred (red)
        WARNING       // Warning state (yellow)
    }
}