package com.byroncoughlin.vr_construction_quest

import android.util.Log
import androidx.core.net.toUri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Vector3
import com.meta.spatial.runtime.SceneMesh
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.SupportsLocomotion
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import org.json.JSONObject
import kotlin.math.sqrt

/**
 * Shared low-poly meshes drawn many times: plants (vr_plants.py) and furniture
 * (vr_furniture.py) arrive as a map of meshes, each a set of color groups, plus a
 * list of instances that name a mesh and give its position, scale and yaw. Each
 * color group becomes one "mesh://<prefix>/N" creator registered on the activity
 * and shared by every instance of the mesh; [clear] unregisters them. "models" are
 * .glb files made from photos (plant_model_service.py), loaded from the backend by
 * URL. Positions are metres, scaled by [HouseGenerator.SCALE] like the rest of the house.
 * [walkable] instances take the SDK's teleport (floor finishes: they lie over the floor
 * slab, so without it the teleport ray stops on them and finds nowhere to land).
 */
class MeshInstances(
    private val activity: AppSystemActivity,
    private val prefix: String,
    private val roughness: Float = 0.95f,
    private val walkable: Boolean = false,
) {
    companion object {
        private const val TAG = "MeshInstances"
        private const val SCALE = HouseGenerator.SCALE
    }

    private val meshUris = mutableListOf<String>()
    private val groupUris = mutableMapOf<String, List<String>>()
    private var meshSerial = 0

    /** How many distinct meshes have been registered since [clear]. */
    val meshCount: Int get() = groupUris.size

    /**
     * Build an instance of the mesh it names (registering the mesh the first time),
     * as an entity per color group. Returns the entities, for the caller to track.
     */
    fun buildInstance(instance: JSONObject, meshes: JSONObject): List<Entity> {
        val key = instance.optString("mesh")
        val uris = groupUris.getOrPut(key) {
            meshes.optJSONObject(key)?.let { register(it) } ?: emptyList()
        }
        if (uris.isEmpty()) return emptyList()
        val position = vector(instance.getJSONObject("position"), SCALE)
        val scale = vector(instance.getJSONObject("scale"), SCALE)
        val pose = Pose(t = position, q = yawAlong(instance.optDouble("yaw", 0.0).toFloat()))
        return uris.map { uri ->
            Entity.create().apply {
                setComponent(Mesh(mesh = uri.toUri()))
                setComponent(Transform(pose))
                setComponent(Scale(scale))
                setComponent(Visible(true))
                if (walkable) setComponent(SupportsLocomotion())
            }
        }
    }

    /** A model made from a photo: a .glb 1 m tall with its base on its origin. */
    fun buildModel(model: JSONObject): Entity? {
        val url = model.optString("url").takeIf { it.isNotEmpty() } ?: return null
        val full = if (url.startsWith("http")) url else BuildConfig.SERVER_URL + url
        val position = vector(model.getJSONObject("position"), SCALE)
        val size = model.optDouble("scale", 1.0).toFloat() * SCALE
        Log.i(TAG, "🌹 Photo model '${model.optString("name")}' from $full")
        return Entity.create().apply {
            setComponent(Mesh(mesh = full.toUri()))
            setComponent(Transform(Pose(t = position, q = yawAlong(model.optDouble("yaw", 0.0).toFloat()))))
            setComponent(Scale(Vector3(size, size, size)))
            setComponent(Visible(true))
        }
    }

    fun clear() {
        meshUris.forEach { activity.unregisterMeshCreator(it) }
        meshUris.clear()
        groupUris.clear()
    }

    /**
     * One mesh: a creator per color group. "positions" holds whole triangles
     * (xyz per corner, one winding); both windings and flat normals are added here,
     * so thin parts (leaves, panels) show from either side. Returns the groups' URIs.
     */
    private fun register(mesh: JSONObject): List<String> {
        val groups = mesh.optJSONArray("groups") ?: return emptyList()
        val uris = mutableListOf<String>()
        for (g in 0 until groups.length()) {
            val group = groups.getJSONObject(g)
            val src = group.getJSONArray("positions")
            val triangles = src.length() / 9
            if (triangles == 0) continue
            val positions = FloatArray(triangles * 18)
            val normals = FloatArray(triangles * 18)
            for (t in 0 until triangles) {
                val p = FloatArray(9) { src.getDouble(t * 9 + it).toFloat() }
                val ux = p[3] - p[0]; val uy = p[4] - p[1]; val uz = p[5] - p[2]
                val vx = p[6] - p[0]; val vy = p[7] - p[1]; val vz = p[8] - p[2]
                var nx = uy * vz - uz * vy
                var ny = uz * vx - ux * vz
                var nz = ux * vy - uy * vx
                val len = sqrt(nx * nx + ny * ny + nz * nz).takeIf { it > 1e-12f } ?: 1f
                nx /= len; ny /= len; nz /= len
                val o = t * 18
                // Front (a, b, c) then back (a, c, b) with the normal flipped.
                for ((slot, corner) in intArrayOf(0, 1, 2, 0, 2, 1).withIndex()) {
                    val sign = if (slot < 3) 1f else -1f
                    for (k in 0 until 3) positions[o + slot * 3 + k] = p[corner * 3 + k]
                    normals[o + slot * 3] = nx * sign
                    normals[o + slot * 3 + 1] = ny * sign
                    normals[o + slot * 3 + 2] = nz * sign
                }
            }
            val count = triangles * 6
            val uvs = FloatArray(count * 2)
            val colors = IntArray(count) { -1 } // opaque white: the material's color shows as-is
            val indices = IntArray(count) { it }
            val material = Material().apply {
                baseColor = color(group.getJSONObject("color"))
                roughness = this@MeshInstances.roughness
                unlit = false
            }
            val uri = "mesh://$prefix/${meshSerial++}"
            activity.registerMeshCreator(uri) { entity ->
                SceneMesh.meshWithMaterials(
                    positions, normals, uvs, colors, indices,
                    intArrayOf(0, indices.size),
                    arrayOf(material.generateSceneMaterial(entity, activity)),
                    false,
                )
            }
            meshUris.add(uri)
            uris.add(uri)
        }
        return uris
    }

    private fun color(json: JSONObject) = Color4(
        json.optDouble("r", 0.8).toFloat(),
        json.optDouble("g", 0.8).toFloat(),
        json.optDouble("b", 0.8).toFloat(),
        1.0f,
    )

    private fun vector(json: JSONObject, scale: Float) = Vector3(
        json.optDouble("x", 0.0).toFloat() * scale,
        json.optDouble("y", 0.0).toFloat() * scale,
        json.optDouble("z", 0.0).toFloat() * scale,
    )

    /** Same convention as HouseGenerator.yawAlong: backend degrees, atan2(dz, dx). */
    private fun yawAlong(degrees: Float) = Quaternion(0f, -degrees, 0f)
}
