package com.byroncoughlin.vr_construction_quest

import android.util.Log
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.GrabbableType
import com.meta.spatial.toolkit.SupportsLocomotion
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds the furniture from the geometry's "furniture" object (vr_furniture.py):
 * "meshes" (low-poly pieces in metres, base on the floor, front toward +z), "pieces"
 * that place them in the rooms, and "models" (.glb pieces made from photos). It is
 * drawn like the plants, through [MeshInstances]; [clear] removes it all.
 *
 * A piece with a "ref" (which item of the plan it is) can be picked up and put down:
 * its first color group holds the [Grabbable] and the others follow it. [poll], each
 * frame, notices one being let go, stands it upright on its floor and reports where
 * it is through [onMoved] (world metres, the geometry's yaw), to be saved.
 */
class FurnitureBuilder(activity: AppSystemActivity) {
    companion object {
        private const val TAG = "FurnitureBuilder"
        private const val SCALE = HouseGenerator.SCALE
    }

    private class Movable(val entity: Entity, val ref: JSONObject, val floorY: Float) {
        var held = false
    }

    private val entities = mutableListOf<Entity>()
    private val movable = mutableListOf<Movable>()
    private val instances = MeshInstances(activity, "furniture", roughness = 0.8f)

    /** Called on the UI thread when a piece is put down: (its ref, x, z, yaw). */
    var onMoved: ((JSONObject, Float, Float, Float) -> Unit)? = null

    fun build(furniture: JSONObject) {
        clear()
        val meshes = furniture.optJSONObject("meshes") ?: JSONObject()
        val pieces = furniture.optJSONArray("pieces") ?: JSONArray()
        for (i in 0 until pieces.length()) {
            val piece = pieces.getJSONObject(i)
            val parts = instances.buildInstance(piece, meshes)
            // A rug lies on the floor: the teleport ray stops on it, so it must take the teleport.
            if (piece.optString("type") == "rug") parts.forEach { it.setComponent(SupportsLocomotion()) }
            entities += parts
            movableFrom(piece, parts)
        }
        val models = furniture.optJSONArray("models") ?: JSONArray()
        for (i in 0 until models.length()) {
            val model = models.getJSONObject(i)
            instances.buildModel(model)?.let {
                entities.add(it)
                movableFrom(model, listOf(it))
            }
        }
        Log.i(
            TAG,
            "🛋️ Furniture built: ${pieces.length()} pieces (${instances.meshCount} meshes), " +
                "${models.length()} photo models, ${movable.size} movable",
        )
    }

    private fun movableFrom(json: JSONObject, parts: List<Entity>) {
        val ref = json.optJSONObject("ref") ?: return
        val handle = parts.firstOrNull() ?: return
        handle.setComponent(Grabbable(enabled = true, type = GrabbableType.PIVOT_Y))
        for (part in parts.drop(1)) {
            part.setComponent(Transform(Pose()))
            part.setComponent(TransformParent(handle))
        }
        val floorY = json.optJSONObject("position")?.optDouble("y", 0.0)?.toFloat() ?: 0f
        movable += Movable(handle, ref, floorY * SCALE)
    }

    /** Once a frame: a piece let go since the last frame is set upright on its floor and reported. */
    fun poll() {
        for (m in movable) {
            if (m.entity.tryGetComponent<Grabbable>()?.isGrabbed == true) {
                m.held = true
                continue
            }
            if (!m.held) continue
            m.held = false
            val pose = m.entity.tryGetComponent<Transform>()?.transform ?: continue
            val yaw = pose.q.toEuler().y
            m.entity.setComponent(Transform(Pose(Vector3(pose.t.x, m.floorY, pose.t.z), Quaternion(0f, yaw, 0f))))
            Log.i(TAG, "🛋️ ${m.ref.optString("room")} item ${m.ref.optInt("item")} put down at (${pose.t.x}, ${pose.t.z})")
            // The geometry's yaw is the SDK's negated (HouseGenerator.yawAlong).
            onMoved?.invoke(m.ref, pose.t.x / SCALE, pose.t.z / SCALE, -yaw)
        }
    }

    fun clear() {
        entities.forEach { it.destroy() }
        entities.clear()
        movable.clear()
        instances.clear()
    }
}
