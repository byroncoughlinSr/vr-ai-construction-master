package com.byroncoughlin.vr_construction_quest

import android.util.Log
import androidx.core.net.toUri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.Box
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.SupportsLocomotion
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.pow
import kotlin.math.sqrt

data class RoomInfo(val name: String, val centerX: Float, val centerZ: Float, val ceilingY: Float)

/**
 * HouseGenerator loads project data from the backend API and generates
 * walkable VR geometry for Meta Quest devices.
 */
class HouseGenerator(private val serverUrl: String) {
    companion object {
        private const val TAG = "HouseGenerator"
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val roomEntities = mutableListOf<Entity>()
    private val doorEntities = mutableListOf<Entity>()
    private val windowEntities = mutableListOf<Entity>()
    private val wallCeilingEntities = mutableListOf<Entity>()
    private val roomInfoList = mutableListOf<RoomInfo>()
    private var spawnPosition = Vector3(0f, 1.6f, -3.0f)

    /**
     * Fetch VR geometry JSON from the backend for a project.
     * Must be called from an IO/background thread.
     * Returns the geometry JSONObject, or null on failure.
     */
    fun fetchVRGeometry(projectId: Int): JSONObject? {
        return try {
            Log.i(TAG, "🏗️ Fetching VR geometry for project $projectId...")
            val request = Request.Builder()
                .url("$serverUrl/api/v1/projects/$projectId/generate-vr")
                .get()
                .build()
            val response = httpClient.newCall(request).execute()
            if (!response.isSuccessful) {
                Log.e(TAG, "❌ Failed to fetch geometry: HTTP ${response.code}")
                return null
            }
            val json = JSONObject(response.body?.string() ?: "{}")
            if (!json.optBoolean("success", false)) {
                Log.e(TAG, "❌ Backend returned success=false for geometry")
                return null
            }
            json.optJSONObject("geometry")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to fetch VR geometry", e)
            null
        }
    }

    /**
     * Build VR entities from a geometry JSONObject.
     * Must be called from the main/UI thread.
     * Returns the spawn position where the player should start.
     */
    fun buildFromGeometry(geometry: JSONObject): Vector3 {
        val projectName = geometry.optString("project_name", "Unknown Project")
        Log.i(TAG, "📐 Building VR geometry for: $projectName")

        clearAllEntities()

        val spawnJson = geometry.optJSONObject("spawn_position")
        if (spawnJson != null) {
            spawnPosition = Vector3(
                spawnJson.optDouble("x", 0.0).toFloat(),
                spawnJson.optDouble("y", 1.6).toFloat(),
                spawnJson.optDouble("z", -3.0).toFloat()
            )
        }

        val rooms = geometry.getJSONArray("rooms")
        for (i in 0 until rooms.length()) {
            generateRoom(rooms.getJSONObject(i))
        }

        val doors = geometry.optJSONArray("doors")
        if (doors != null) {
            for (i in 0 until doors.length()) generateDoor(doors.getJSONObject(i))
        }

        val windows = geometry.optJSONArray("windows")
        if (windows != null) {
            for (i in 0 until windows.length()) generateWindow(windows.getJSONObject(i))
        }

        val roomCount = geometry.optJSONObject("metadata")?.optInt("total_rooms", 0) ?: 0
        Log.i(TAG, "✅ VR house built! Rooms: $roomCount | Doors: ${doorEntities.size} | Windows: ${windowEntities.size}")
        return spawnPosition
    }

    /**
     * Convenience wrapper: fetch geometry then build entities.
     * WARNING: makes a blocking HTTP call — must NOT be called on the main thread.
     * Prefer fetchVRGeometry() + buildFromGeometry() with proper thread switching.
     */
    fun loadProjectIntoVR(projectId: Int): Vector3? {
        val geometry = fetchVRGeometry(projectId) ?: return null
        return buildFromGeometry(geometry)
    }

    /**
     * Generate a complete room with walls, floor, and ceiling.
     */
    private fun generateRoom(roomJson: JSONObject) {
        val roomName = roomJson.optString("name", "Room")
        val position = roomJson.getJSONObject("position")
        val dimensions = roomJson.getJSONObject("dimensions")

        Log.d(TAG, "🏠 Generating room: $roomName")

        // Record room info for label beacons
        val centerX = position.optDouble("x", 0.0).toFloat()
        val centerZ = position.optDouble("z", 0.0).toFloat()
        val ceilingY = dimensions.optDouble("height", 9.0).toFloat()
        roomInfoList.add(RoomInfo(roomName, centerX, centerZ, ceilingY))

        // Generate floor
        val floor = roomJson.optJSONObject("floor")
        if (floor != null) {
            generateFloor(floor, roomName)
        }

        // Generate walls
        val walls = roomJson.optJSONArray("walls")
        if (walls != null) {
            for (i in 0 until walls.length()) {
                val wall = walls.getJSONObject(i)
                generateWall(wall, roomName)
            }
        }

        // Generate ceiling
        val ceiling = roomJson.optJSONObject("ceiling")
        if (ceiling != null) {
            generateCeiling(ceiling, roomName)
        }
    }

    /**
     * Generate a wall mesh.
     */
    private fun generateWall(wallJson: JSONObject, roomName: String) {
        val start = wallJson.getJSONObject("start")
        val end = wallJson.getJSONObject("end")
        val height = wallJson.optDouble("height", 9.0).toFloat()

        val startX = start.optDouble("x", 0.0).toFloat()
        val startY = start.optDouble("y", 0.0).toFloat()
        val startZ = start.optDouble("z", 0.0).toFloat()

        val endX = end.optDouble("x", 0.0).toFloat()
        val endY = end.optDouble("y", 0.0).toFloat()
        val endZ = end.optDouble("z", 0.0).toFloat()

        // Calculate wall dimensions and position
        val dx = endX - startX
        val dz = endZ - startZ
        val length = sqrt(dx.pow(2) + dz.pow(2))

        val centerX = (startX + endX) / 2
        val centerY = height / 2
        val centerZ = (startZ + endZ) / 2

        // Create wall entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(Box(Vector3(length / 2, height / 2, 0.1f)))
        entity.setComponent(Material().apply {
            baseColor = Color4(0.95f, 0.95f, 0.95f, 1.0f)
            roughness = 0.8f
            unlit = false
        })

        // Calculate rotation angle
        val angle = Math.atan2(dz.toDouble(), dx.toDouble()).toFloat()
        val quat = com.meta.spatial.core.Quaternion(0f, angle, 0f)

        entity.setComponent(Transform(Pose(
            t = Vector3(centerX, centerY, centerZ),
            q = quat
        )))
        entity.setComponent(Visible(true))

        roomEntities.add(entity)
        wallCeilingEntities.add(entity)
    }

    /**
     * Generate a floor mesh.
     */
    private fun generateFloor(floorJson: JSONObject, roomName: String) {
        val vertices = floorJson.getJSONArray("vertices")
        val material = floorJson.optString("material", "carpet")

        // Calculate center and dimensions from vertices
        val v0 = vertices.getJSONObject(0)
        val v2 = vertices.getJSONObject(2)

        val x1 = v0.optDouble("x", 0.0).toFloat()
        val z1 = v0.optDouble("z", 0.0).toFloat()
        val x2 = v2.optDouble("x", 0.0).toFloat()
        val z2 = v2.optDouble("z", 0.0).toFloat()

        val centerX = (x1 + x2) / 2
        val centerZ = (z1 + z2) / 2
        val width = Math.abs(x2 - x1)
        val depth = Math.abs(z2 - z1)

        // Create floor entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(Box(Vector3(width / 2, 0.05f, depth / 2)))
        entity.setComponent(Material().apply {
            baseColor = getMaterialColor(material)
            roughness = 0.7f
            unlit = false
        })
        entity.setComponent(Transform(Pose(t = Vector3(centerX, 0f, centerZ))))
        entity.setComponent(SupportsLocomotion())
        entity.setComponent(Visible(true))

        roomEntities.add(entity)
    }

    /**
     * Generate a ceiling mesh.
     */
    private fun generateCeiling(ceilingJson: JSONObject, roomName: String) {
        val vertices = ceilingJson.getJSONArray("vertices")
        val material = ceilingJson.optString("material", "drywall")

        // Calculate center and dimensions from vertices
        val v0 = vertices.getJSONObject(0)
        val v2 = vertices.getJSONObject(2)

        val x1 = v0.optDouble("x", 0.0).toFloat()
        val y = v0.optDouble("y", 9.0).toFloat()
        val z1 = v0.optDouble("z", 0.0).toFloat()
        val x2 = v2.optDouble("x", 0.0).toFloat()
        val z2 = v2.optDouble("z", 0.0).toFloat()

        val centerX = (x1 + x2) / 2
        val centerZ = (z1 + z2) / 2
        val width = Math.abs(x2 - x1)
        val depth = Math.abs(z2 - z1)

        // Create ceiling entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(Box(Vector3(width / 2, 0.05f, depth / 2)))
        entity.setComponent(Material().apply {
            baseColor = getMaterialColor(material)
            roughness = 0.8f
            unlit = false
        })
        entity.setComponent(Transform(Pose(t = Vector3(centerX, y, centerZ))))
        entity.setComponent(Visible(true))

        roomEntities.add(entity)
        wallCeilingEntities.add(entity)
    }

    /**
     * Generate a door opening.
     */
    private fun generateDoor(doorJson: JSONObject) {
        val position = doorJson.getJSONObject("position")
        val width = doorJson.optDouble("width", 3.0).toFloat()
        val height = doorJson.optDouble("height", 6.67).toFloat()
        val rotation = doorJson.optInt("rotation", 0)

        val x = position.optDouble("x", 0.0).toFloat()
        val y = position.optDouble("y", 0.0).toFloat()
        val z = position.optDouble("z", 0.0).toFloat()

        // Create door frame entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(Box(Vector3(width / 2, height / 2, 0.1f)))
        entity.setComponent(Material().apply {
            baseColor = Color4(0.4f, 0.3f, 0.2f, 1.0f) // Brown wood color
            roughness = 0.6f
            unlit = false
        })
        entity.setComponent(Transform(Pose(t = Vector3(x, height / 2, z))))
        entity.setComponent(Visible(true))

        doorEntities.add(entity)
    }

    /**
     * Generate a window.
     */
    private fun generateWindow(windowJson: JSONObject) {
        val position = windowJson.getJSONObject("position")
        val width = windowJson.optDouble("width", 4.0).toFloat()
        val height = windowJson.optDouble("height", 5.0).toFloat()

        val x = position.optDouble("x", 0.0).toFloat()
        val y = position.optDouble("y", 3.0).toFloat()
        val z = position.optDouble("z", 0.0).toFloat()

        // Create window entity (semi-transparent blue)
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(Box(Vector3(width / 2, height / 2, 0.05f)))
        entity.setComponent(Material().apply {
            baseColor = Color4(0.7f, 0.9f, 1.0f, 0.3f) // Light blue glass
            roughness = 0.1f
            metallic = 0.1f
            unlit = false
        })
        entity.setComponent(Transform(Pose(t = Vector3(x, y, z))))
        entity.setComponent(Visible(true))

        windowEntities.add(entity)
    }

    /**
     * Get material color based on material type.
     */
    private fun getMaterialColor(materialType: String): Color4 {
        return when (materialType.lowercase()) {
            "wood" -> Color4(0.7f, 0.5f, 0.3f, 1.0f)
            "concrete" -> Color4(0.6f, 0.6f, 0.6f, 1.0f)
            "metal" -> Color4(0.8f, 0.8f, 0.9f, 1.0f)
            "glass" -> Color4(0.7f, 0.9f, 1.0f, 0.5f)
            "carpet" -> Color4(0.7f, 0.6f, 0.5f, 1.0f)
            "tile" -> Color4(0.9f, 0.85f, 0.8f, 1.0f)
            "drywall" -> Color4(0.95f, 0.95f, 0.95f, 1.0f)
            else -> Color4(0.8f, 0.8f, 0.8f, 1.0f)
        }
    }

    /**
     * Clear all generated entities.
     */
    fun clearAllEntities() {
        roomEntities.forEach { it.destroy() }
        doorEntities.forEach { it.destroy() }
        windowEntities.forEach { it.destroy() }
        roomEntities.clear()
        doorEntities.clear()
        windowEntities.clear()
        wallCeilingEntities.clear()  // entities already destroyed above
        roomInfoList.clear()
    }

    /**
     * Get the total number of rooms generated.
     */
    fun getRoomCount(): Int = roomEntities.size / 6  // Each room has ~6 entities (4 walls + floor + ceiling)

    /**
     * Get the spawn position for the player.
     */
    fun getSpawnPosition(): Vector3 = spawnPosition

    /**
     * Toggle x-ray vision — hides/shows walls and ceilings so floors remain visible.
     */
    fun setXRayEnabled(enabled: Boolean) {
        wallCeilingEntities.forEach { it.setComponent(Visible(!enabled)) }
        Log.i(TAG, "${if (enabled) "🔍 X-ray ON" else "🔒 X-ray OFF"} | ${wallCeilingEntities.size} entities")
    }

    /**
     * Get room info list for spawning label beacons.
     */
    fun getRoomInfoList(): List<RoomInfo> = roomInfoList.toList()
}
