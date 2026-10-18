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
import com.meta.spatial.toolkit.Sphere
import com.meta.spatial.toolkit.SupportsLocomotion
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds the outside of the house from the geometry's "exterior" object
 * (vr_exterior.py): roof meshes made of triangles, box and sphere "parts" for the
 * wall finish, ground, foundation and paving, and plants (vr_plants.py). Positions
 * are metres, scaled by [HouseGenerator.SCALE] like the rest of the house.
 *
 * Roofs and plants are custom meshes: each roof gets its own "mesh://exterior/N"
 * creator registered on the activity, removed again by [clear]; plants are
 * [MeshInstances] (a creator per color group, shared by every plant that uses the
 * mesh). The only files are "models": .glb plants made from photos
 * (plant_model_service.py), loaded from the backend by URL.
 */
class ExteriorBuilder(private val activity: AppSystemActivity) {
    companion object {
        private const val TAG = "ExteriorBuilder"
        private const val SCALE = HouseGenerator.SCALE
    }

    /** Every entity this builder created. */
    private val entities = mutableListOf<Entity>()
    /** Roof and wall finish: hidden with the walls in x-ray mode. */
    private val shell = mutableListOf<Entity>()
    private val meshUris = mutableListOf<String>()
    private var meshSerial = 0
    /** Plant meshes, shared by every plant that uses one. */
    private val instances = MeshInstances(activity, "exterior-plant")

    /** Color for exterior door frames, when the plan names a trim color. */
    var trimColor: Color4? = null
        private set

    fun build(exterior: JSONObject) {
        clear()
        trimColor = exterior.optJSONObject("trim_color")?.let { color(it) }

        val roof = exterior.optJSONArray("roof") ?: JSONArray()
        for (i in 0 until roof.length()) buildMesh(roof.getJSONObject(i))

        val parts = exterior.optJSONArray("parts") ?: JSONArray()
        for (i in 0 until parts.length()) buildPart(parts.getJSONObject(i))

        val plantMeshes = exterior.optJSONObject("plant_meshes") ?: JSONObject()
        val plants = exterior.optJSONArray("plants") ?: JSONArray()
        for (i in 0 until plants.length()) entities += instances.buildInstance(plants.getJSONObject(i), plantMeshes)

        val models = exterior.optJSONArray("models") ?: JSONArray()
        for (i in 0 until models.length()) instances.buildModel(models.getJSONObject(i))?.let { entities.add(it) }

        Log.i(
            TAG,
            "🏡 Exterior built: ${roof.length()} roof meshes, ${parts.length()} parts, " +
                "${plants.length()} plants (${instances.meshCount} meshes), ${models.length()} photo models",
        )
    }

    fun setShellVisible(visible: Boolean) {
        shell.forEach { it.setComponent(Visible(visible)) }
    }

    fun clear() {
        entities.forEach { it.destroy() }
        entities.clear()
        shell.clear()
        meshUris.forEach { activity.unregisterMeshCreator(it) }
        meshUris.clear()
        instances.clear()
        trimColor = null
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

    private fun buildPart(part: JSONObject) {
        val center = vector(part.getJSONObject("center"), SCALE)
        val size = vector(part.getJSONObject("size"), SCALE)
        val material = Material().apply {
            baseColor = color(part.getJSONObject("color"))
            roughness = 0.9f
            unlit = false
        }
        val entity = Entity.create()
        if (part.optString("shape") == "sphere") {
            // A unit-diameter sphere stretched to the part's size.
            entity.setComponent(Mesh(mesh = "mesh://sphere".toUri()))
            entity.setComponent(Sphere(0.5f))
            entity.setComponent(Scale(size))
        } else {
            entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
            entity.setComponent(centeredBox(size))
        }
        entity.setComponent(material)
        entity.setComponent(Transform(Pose(t = center, q = yawAlong(part.optDouble("yaw", 0.0).toFloat()))))
        if (part.optBoolean("walkable", false)) entity.setComponent(SupportsLocomotion())
        entity.setComponent(Visible(true))
        entities.add(entity)
        when (part.optString("kind")) {
            "wall", "roof" -> shell.add(entity)
        }
    }

    /**
     * A triangle mesh: "positions" and "normals" are flat xyz lists (metres),
     * "indices" one per vertex. The backend sends both windings, so it shows from
     * either side.
     */
    private fun buildMesh(mesh: JSONObject) {
        val pos = mesh.getJSONArray("positions")
        val nrm = mesh.getJSONArray("normals")
        val count = pos.length() / 3
        if (count < 3) return
        val positions = FloatArray(count * 3) { pos.getDouble(it).toFloat() * SCALE }
        val normals = FloatArray(count * 3) { nrm.optDouble(it, 0.0).toFloat() }
        val uvs = FloatArray(count * 2)
        val colors = IntArray(count) { -1 } // opaque white: the material's color shows as-is
        val indices = IntArray(count) { it }
        val material = Material().apply {
            baseColor = color(mesh.getJSONObject("color"))
            roughness = 0.85f
            unlit = false
        }

        val uri = "mesh://exterior/${meshSerial++}"
        activity.registerMeshCreator(uri) { entity ->
            SceneMesh.meshWithMaterials(
                positions, normals, uvs, colors, indices,
                intArrayOf(0, indices.size),
                arrayOf(material.generateSceneMaterial(entity, activity)),
                false,
            )
        }
        meshUris.add(uri)

        val entity = Entity.create()
        entity.setComponent(material)
        entity.setComponent(Mesh(mesh = uri.toUri()))
        entity.setComponent(Transform(Pose(t = Vector3(0f, 0f, 0f))))
        entity.setComponent(Visible(true))
        entities.add(entity)
        shell.add(entity)
    }
}
