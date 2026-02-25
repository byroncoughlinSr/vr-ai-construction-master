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
 * NOTE: Meta Spatial SDK entities have no parent–child relationship, so
 * visibility must be set on each visual entity individually.
 * All positions are in world space.
 */
class ProgressBar(
    private val width: Float = 1.0f,
    private val height: Float = 0.05f,
    private val depth: Float = 0.02f,
    private var position: Vector3 = Vector3(0f, 1.5f, -1.0f)
) {
    companion object {
        private const val TAG = "ProgressBar"
    }

    private var backgroundBar: Entity? = null
    private var fillBar: Entity? = null

    private var currentProgress: Float = 0f
    private var isVisible: Boolean = false

    private fun ensureCreated() {
        if (backgroundBar != null) return

        Log.i(TAG, "📊 Creating progress bar at position: $position")

        // Background bar — full width, dark gray
        backgroundBar = Entity.create().apply {
            setComponent(Transform(Pose(t = position)))
            setComponent(Mesh(mesh = "mesh://box".toUri()))
            setComponent(com.meta.spatial.toolkit.Box(Vector3(width / 2f, height / 2f, depth / 2f)))
            setComponent(Material().apply {
                baseColor = Color4(0.3f, 0.3f, 0.3f, 0.8f)
                unlit = true
            })
            setComponent(Visible(false))
        }

        // Fill bar — starts at left edge with near-zero width, grows right
        fillBar = Entity.create().apply {
            setComponent(Transform(Pose(t = fillBarPosition(0f))))
            setComponent(Mesh(mesh = "mesh://box".toUri()))
            setComponent(com.meta.spatial.toolkit.Box(Vector3(0.001f, height / 2f, depth / 2f)))
            setComponent(Material().apply {
                baseColor = Color4(0.2f, 0.8f, 0.3f, 1.0f)
                unlit = true
            })
            setComponent(Visible(false))
        }

        Log.i(TAG, "✅ Progress bar entities created")
    }

    /** World-space centre of the fill bar for a given 0..1 progress. */
    private fun fillBarPosition(progress: Float): Vector3 {
        val fillWidth = width * progress
        val xOffset = -width / 2f + fillWidth / 2f
        return Vector3(position.x + xOffset, position.y, position.z + depth / 2f + 0.001f)
    }

    fun show() {
        ensureCreated()
        backgroundBar?.setComponent(Visible(true))
        fillBar?.setComponent(Visible(true))
        isVisible = true
        Log.i(TAG, "👁️ Progress bar shown")
    }

    fun hide() {
        backgroundBar?.setComponent(Visible(false))
        fillBar?.setComponent(Visible(false))
        isVisible = false
        Log.i(TAG, "🙈 Progress bar hidden")
    }

    fun setProgress(progress: Float) {
        ensureCreated()
        val clamped = progress.coerceIn(0f, 1f)
        currentProgress = clamped

        val fillWidth = maxOf(width * clamped, 0.002f) // keep a minimum so Box stays valid
        fillBar?.let { bar ->
            bar.setComponent(Transform(Pose(t = fillBarPosition(clamped))))
            bar.setComponent(com.meta.spatial.toolkit.Box(Vector3(fillWidth / 2f, height / 2f, depth / 2f)))
        }
        Log.i(TAG, "📈 Progress: ${(clamped * 100).toInt()}%")
    }

    fun setProgressPercentage(percentage: Int) = setProgress(percentage / 100f)

    fun reset() {
        setProgress(0f)
        Log.i(TAG, "🔄 Progress reset")
    }

    fun setColor(color: Color4) {
        ensureCreated()
        fillBar?.let { bar ->
            val m = bar.tryGetComponent<Material>() ?: Material()
            m.baseColor = color
            bar.setComponent(m)
        }
    }

    fun setStateColor(state: ProgressState) {
        val color = when (state) {
            ProgressState.GENERATING  -> Color4(0.2f, 0.8f, 0.3f, 1.0f) // green
            ProgressState.PROCESSING  -> Color4(0.3f, 0.6f, 1.0f, 1.0f) // blue
            ProgressState.COMPLETE    -> Color4(0.3f, 1.0f, 0.3f, 1.0f) // bright green
            ProgressState.ERROR       -> Color4(1.0f, 0.3f, 0.3f, 1.0f) // red
            ProgressState.WARNING     -> Color4(1.0f, 0.8f, 0.2f, 1.0f) // yellow
        }
        setColor(color)
    }

    fun setPosition(newPosition: Vector3) {
        position = newPosition
        backgroundBar?.setComponent(Transform(Pose(t = position)))
        fillBar?.setComponent(Transform(Pose(t = fillBarPosition(currentProgress))))
        Log.i(TAG, "📍 Progress bar repositioned to: $newPosition")
    }

    fun destroy() {
        Log.i(TAG, "💥 Destroying progress bar")
        fillBar?.destroy()
        backgroundBar?.destroy()
        fillBar = null
        backgroundBar = null
        currentProgress = 0f
        isVisible = false
    }

    fun getProgress(): Float = currentProgress
    fun isVisible(): Boolean = isVisible

    enum class ProgressState {
        GENERATING, PROCESSING, COMPLETE, ERROR, WARNING
    }
}
