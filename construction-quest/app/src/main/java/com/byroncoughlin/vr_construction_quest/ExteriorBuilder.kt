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
import kotlin.math.sqrt

/**
 * Builds the outside of the house from the geometry's "exterior" object
 * (vr_exterior.py): roof meshes made of triangles, box and sphere "parts" for the
 * wall finish, ground, foundation and paving, and plants (vr_plants.py). Positions
 * are metres, scaled by [HouseGenerator.SCALE] like the rest of the house.
 *
 * Roofs and plants are custom meshes: each gets its own "mesh://exterior/N" creator
 * registered on the activity, removed again by [clear]. A plant mesh is a set of
 * color groups, each one creator shared by every plant that uses the mesh. The only
 * files are "models": .glb plants made from photos (plant_model_service.py), loaded
 * from the backend by URL.
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
        val groupUris = mutableMapOf<String, List<String>>()
        for (i in 0 until plants.length()) {
            val plant = plants.getJSONObject(i)
            val key = plant.optString("mesh")
            val uris = groupUris.getOrPut(key) {
                plantMeshes.optJSONObject(key)?.let { registerPlantMesh(it) } ?: emptyList()
            }
            buildPlant(plant, uris)
        }

        val models = exterior.optJSONArray("models") ?: JSONArray()
        for (i in 0 until models.length()) buildModel(models.getJSONObject(i))

        Log.i(
            TAG,
            "🏡 Exterior built: ${roof.length()} roof meshes, ${parts.length()} parts, " +
                "${plants.length()} plants (${groupUris.size} meshes), ${models.length()} photo models",
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
     * One plant mesh: a creator per color group. "positions" holds whole triangles
     * (xyz per corner, one winding); both windings and flat normals are added here,
     * so leaves show from either side. Returns the groups' mesh URIs.
     */
    private fun registerPlantMesh(mesh: JSONObject): List<String> {
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
                roughness = 0.95f
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
            uris.add(uri)
        }
        return uris
    }

    /** One plant: an entity per color group, all with the plant's pose and size. */
    private fun buildPlant(plant: JSONObject, uris: List<String>) {
        if (uris.isEmpty()) return
        val position = vector(plant.getJSONObject("position"), SCALE)
        val scale = vector(plant.getJSONObject("scale"), SCALE)
        val pose = Pose(t = position, q = yawAlong(plant.optDouble("yaw", 0.0).toFloat()))
        for (uri in uris) {
            val entity = Entity.create()
            entity.setComponent(Mesh(mesh = uri.toUri()))
            entity.setComponent(Transform(pose))
            entity.setComponent(Scale(scale))
            entity.setComponent(Visible(true))
            entities.add(entity)
        }
    }

    /** A plant made from a photo: a .glb 1 m tall with its base on its origin. */
    private fun buildModel(model: JSONObject) {
        val url = model.optString("url").takeIf { it.isNotEmpty() } ?: return
        val full = if (url.startsWith("http")) url else BuildConfig.SERVER_URL + url
        val position = vector(model.getJSONObject("position"), SCALE)
        val size = model.optDouble("scale", 1.0).toFloat() * SCALE
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = full.toUri()))
        entity.setComponent(Transform(Pose(t = position, q = yawAlong(model.optDouble("yaw", 0.0).toFloat()))))
        entity.setComponent(Scale(Vector3(size, size, size)))
        entity.setComponent(Visible(true))
        entities.add(entity)
        Log.i(TAG, "🌹 Photo model '${model.optString("name")}' from $full")
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
