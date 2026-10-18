package com.byroncoughlin.vr_construction_quest

import android.util.Log
import androidx.core.net.toUri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Grabbable
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.SupportsLocomotion
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.Visible
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.pow
import kotlin.math.sqrt

data class RoomInfo(
    val name: String,
    val centerX: Float,
    val centerZ: Float,
    val ceilingY: Float,
    val width: Float = 0f,
    val depth: Float = 0f
)

/**
 * HouseGenerator loads project data from the backend API and generates
 * walkable VR geometry for Meta Quest devices.
 */
class HouseGenerator(private val serverUrl: String, activity: AppSystemActivity) {
    companion object {
        private const val TAG = "HouseGenerator"
        // World units per metre. 1: the house at its real size, so with the eyes at a
        // 6 ft person's height (ImmersiveActivity.EYE_HEIGHT_M) rooms, furniture and
        // the yard all look as they would in person. (It was 2, which made the house
        // look twice life size against the headset's sense of scale.)
        const val SCALE = 1.0f
        // Backend WALL_T (vr_geometry_service.py) is the HALF thickness in metres; walls
        // are centred on room edges, and floors/corners are extended by WALL_T to meet
        // their faces. Full thickness in world units is therefore 2 * WALL_T * SCALE.
        private const val WALL_HALF_THICKNESS_M = 0.1f
        private const val WALL_THICKNESS = 2 * WALL_HALF_THICKNESS_M * SCALE
        // The yard's surface, below the floors: vr_exterior.GROUND_TOP (metres).
        private const val GROUND_TOP_M = -0.10f
        // Must outlast the backend's planning budget (settings.planning_timeout_seconds,
        // 200 s) so the server's error, not a client timeout, reaches the user.
        private const val PLAN_CALL_TIMEOUT_S = 240L
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val longPlanClient = httpClient.newBuilder()
        .readTimeout(PLAN_CALL_TIMEOUT_S, TimeUnit.SECONDS)
        .callTimeout(PLAN_CALL_TIMEOUT_S, TimeUnit.SECONDS)
        .build()

    private val roomEntities = mutableListOf<Entity>()
    private val doorEntities = mutableListOf<Entity>()
    private val windowEntities = mutableListOf<Entity>()
    private val wallCeilingEntities = mutableListOf<Entity>()
    private val roomInfoList = mutableListOf<RoomInfo>()
    private val exterior = ExteriorBuilder(activity)
    /** Where there is floor (x0, x1, z0, z1, world units): rooms and bay bump-outs. */
    private val floorAreas = mutableListOf<FloatArray>()
    /** The height of the ground outside: the yard when the plan has one, else the floor's. */
    private var groundY = 0f
    private val furniture = FurnitureBuilder(activity)
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
            // use {} closes the response on every path; an unread error body would
            // otherwise leak its pooled connection.
            val json = httpClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.e(TAG, "❌ Failed to fetch geometry: HTTP ${response.code}")
                    return null
                }
                JSONObject(response.body?.string() ?: "{}")
            }
            if (!json.optBoolean("success", false)) {
                Log.e(TAG, "❌ Backend returned success=false for geometry")
                return null
            }
            val meta = json.optJSONObject("geometry")?.optJSONObject("metadata")
            Log.i(TAG, "✅ Geometry fetched: $meta")

            json.optJSONObject("geometry")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to fetch VR geometry", e)
            null
        }
    }

    /**
     * Fetch VR geometry JSON for a floor-plan prompt; the backend saves the house as a
     * project, and the geometry carries its project_id / project_name.
     * Used by the first voice prompt in the two-prompt flow (the floor-plan
     * description); imagePrompt optionally adds style grounding (the voice flow passes null).
     * Must be called from an IO/background thread.
     */
    fun fetchVRGeometryFromPrompt(prompt: String, imagePrompt: String?): JSONObject? {
        return try {
            Log.i(TAG, "🎯 Fetching VR geometry from prompt (imagePrompt=${imagePrompt != null})…")
            val body = JSONObject().apply {
                put("prompt", prompt)
                if (!imagePrompt.isNullOrBlank()) put("image_prompt", imagePrompt)
            }
            val request = Request.Builder()
                .url("$serverUrl/api/v1/planning/generate-vr-from-prompt")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()
            val json = longPlanClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.e(TAG, "❌ Failed to fetch prompt geometry: HTTP ${response.code}")
                    return null
                }
                JSONObject(response.body?.string() ?: "{}")
            }
            if (!json.optBoolean("success", false)) {
                Log.e(TAG, "❌ Backend returned success=false for prompt geometry")
                return null
            }
            Log.i(TAG, "✅ Prompt geometry fetched successfully")
            json.optJSONObject("geometry")
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to fetch VR geometry from prompt", e)
            null
        }
    }

    /**
     * Ask the backend to change project [projectId]'s floor plan as described in
     * [instruction] ("make the kitchen bigger"). The revision is saved as a new
     * floor-plan version; returns its geometry, or null on failure.
     * Must be called from an IO/background thread.
     */
    fun refineFloorPlan(projectId: Int, instruction: String): JSONObject? {
        return try {
            Log.i(TAG, "✏️ Refining floor plan of project $projectId: '$instruction'")
            val body = JSONObject().put("instruction", instruction)
            val request = Request.Builder()
                .url("$serverUrl/api/v1/projects/$projectId/floor-plan/refine")
                .post(body.toString().toRequestBody("application/json".toMediaType()))
                .build()
            longPlanClient.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.e(TAG, "❌ Floor plan refinement failed: HTTP ${response.code}")
                    return null
                }
                JSONObject(response.body?.string() ?: "{}").optJSONObject("geometry")
            }
        } catch (e: Exception) {
            Log.e(TAG, "❌ Failed to refine floor plan", e)
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
                spawnJson.optDouble("x", 0.0).toFloat() * SCALE,
                spawnJson.optDouble("y", 1.6).toFloat(),
                spawnJson.optDouble("z", -3.0).toFloat() * SCALE
            )
        }

        val rooms = geometry.getJSONArray("rooms")
        for (i in 0 until rooms.length()) {
            generateRoom(rooms.getJSONObject(i))
        }

        // If no spawn_position from backend, place player in the master bedroom (or first room)
        if (spawnJson == null && roomInfoList.isNotEmpty()) {
            val spawnRoom = roomInfoList.firstOrNull {
                it.name.lowercase().contains("master") && it.name.lowercase().contains("bed")
            } ?: roomInfoList[0]
            spawnPosition = Vector3(spawnRoom.centerX, 1.6f, spawnRoom.centerZ)
            Log.i(TAG, "📍 No spawn_position in JSON — using ${spawnRoom.name} center: (${spawnRoom.centerX}, 1.6, ${spawnRoom.centerZ})")
        }

        // Roof, wall finish and yard, when the plan describes the outside.
        geometry.optJSONObject("exterior")?.let {
            exterior.build(it)
            groundY = GROUND_TOP_M * SCALE
        }
        // Furniture in the rooms, when the plan has any.
        geometry.optJSONObject("furniture")?.let { furniture.build(it) }

        val doors = geometry.optJSONArray("doors")
        val doorCount = doors?.length() ?: 0
        if (doors != null) {
            for (i in 0 until doors.length()) generateDoor(doors.getJSONObject(i))
        }

        val windows = geometry.optJSONArray("windows")
        if (windows != null) {
            for (i in 0 until windows.length()) generateWindow(windows.getJSONObject(i))
        }

        val roomCount = geometry.optJSONObject("metadata")?.optInt("total_rooms", 0) ?: 0
        Log.i(TAG, "✅ VR house built! Rooms: $roomCount | Doors: $doorCount | Windows: ${windowEntities.size}")
        return spawnPosition
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
        val centerX = position.optDouble("x", 0.0).toFloat() * SCALE
        val centerZ = position.optDouble("z", 0.0).toFloat() * SCALE
        val ceilingY = dimensions.optDouble("height", 9.0).toFloat() * SCALE
        // Backend sends metres: "length" runs along X, "width" along Z.
        val roomWidth = dimensions.optDouble("length", 0.0).toFloat() * SCALE
        val roomDepth = dimensions.optDouble("width", 0.0).toFloat() * SCALE
        roomInfoList.add(RoomInfo(roomName, centerX, centerZ, ceilingY, roomWidth, roomDepth))
        floorAreas.add(floatArrayOf(
            centerX - roomWidth / 2, centerX + roomWidth / 2, centerZ - roomDepth / 2, centerZ + roomDepth / 2,
        ))

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

        // A bay window's walls come with the room's; its bump-out has its own floor and ceiling.
        roomJson.optJSONObject("bay_window")?.let { bay ->
            bay.optJSONArray("outline")?.let { outline ->
                if (outline.length() > 0) {
                    val xs = (0 until outline.length()).map { outline.getJSONObject(it).optDouble("x").toFloat() * SCALE }
                    val zs = (0 until outline.length()).map { outline.getJSONObject(it).optDouble("z").toFloat() * SCALE }
                    floorAreas.add(floatArrayOf(xs.min(), xs.max(), zs.min(), zs.max()))
                }
            }
            bay.optJSONObject("floor")?.let { generateFloor(it, roomName) }
            bay.optJSONObject("ceiling")?.let { generateCeiling(it, roomName) }
        }
    }

    /**
     * Generate a wall mesh. The backend splits walls around door and window
     * openings, so a piece may start above the floor: start.y is its base.
     */
    private fun generateWall(wallJson: JSONObject, roomName: String) {
        val start = wallJson.getJSONObject("start")
        val end = wallJson.getJSONObject("end")
        val height = wallJson.optDouble("height", 9.0).toFloat()

        val startX = start.optDouble("x", 0.0).toFloat() * SCALE
        val startY = start.optDouble("y", 0.0).toFloat() * SCALE
        val startZ = start.optDouble("z", 0.0).toFloat() * SCALE

        val endX = end.optDouble("x", 0.0).toFloat() * SCALE
        val endY = end.optDouble("y", 0.0).toFloat() * SCALE
        val endZ = end.optDouble("z", 0.0).toFloat() * SCALE

        val scaledHeight = height * SCALE

        // Calculate wall dimensions and position
        val dx = endX - startX
        val dz = endZ - startZ
        val length = sqrt(dx.pow(2) + dz.pow(2))

        val centerX = (startX + endX) / 2
        val centerY = startY + scaledHeight / 2
        val centerZ = (startZ + endZ) / 2

        // Create wall entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(centeredBox(Vector3(length, scaledHeight, WALL_THICKNESS)))
        entity.setComponent(Material().apply {
            baseColor = Color4(0.95f, 0.95f, 0.95f, 1.0f)
            roughness = 0.8f
            unlit = false
        })

        val quat = yawAlong(Math.toDegrees(Math.atan2(dz.toDouble(), dx.toDouble())).toFloat())

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

        val x1 = v0.optDouble("x", 0.0).toFloat() * SCALE
        val z1 = v0.optDouble("z", 0.0).toFloat() * SCALE
        val x2 = v2.optDouble("x", 0.0).toFloat() * SCALE
        val z2 = v2.optDouble("z", 0.0).toFloat() * SCALE

        val centerX = (x1 + x2) / 2
        val centerZ = (z1 + z2) / 2
        val width = Math.abs(x2 - x1)
        val depth = Math.abs(z2 - z1)

        // Create floor entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(centeredBox(Vector3(width, 0.05f, depth)))
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

        val x1 = v0.optDouble("x", 0.0).toFloat() * SCALE
        val y = v0.optDouble("y", 9.0).toFloat() * SCALE
        val z1 = v0.optDouble("z", 0.0).toFloat() * SCALE
        val x2 = v2.optDouble("x", 0.0).toFloat() * SCALE
        val z2 = v2.optDouble("z", 0.0).toFloat() * SCALE

        val centerX = (x1 + x2) / 2
        val centerZ = (z1 + z2) / 2
        val width = Math.abs(x2 - x1)
        val depth = Math.abs(z2 - z1)

        // Create ceiling entity
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(centeredBox(Vector3(width, 0.05f, depth)))
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
     * Generate a door frame around an opening the backend has already cut in the
     * walls: two jambs and a head, so the doorway stays open to walk through.
     */
    private fun generateDoor(doorJson: JSONObject) {
        val position = doorJson.getJSONObject("position")
        val width = doorJson.optDouble("width", 0.914).toFloat() * SCALE
        val height = doorJson.optDouble("height", 2.033).toFloat() * SCALE
        val rotationDeg = doorJson.optDouble("rotation", 0.0).toFloat()

        val x = position.optDouble("x", 0.0).toFloat() * SCALE
        val z = position.optDouble("z", 0.0).toFloat() * SCALE

        // Along-wall direction, same convention as generateWall's atan2(dz, dx).
        val rad = Math.toRadians(rotationDeg.toDouble())
        val dirX = Math.cos(rad).toFloat()
        val dirZ = Math.sin(rad).toFloat()
        val quat = yawAlong(rotationDeg)
        val doorType = doorJson.optString("door_type")
        val isExterior = doorType == "exterior" || doorType == "patio"
        val color = if (isExterior) {
            exterior.trimColor ?: Color4(0.25f, 0.18f, 0.12f, 1.0f)
        } else {
            Color4(0.4f, 0.3f, 0.2f, 1.0f)
        }

        // Deeper than the wall so the frame shows on both faces.
        val trim = 0.08f
        val depth = WALL_THICKNESS + 0.04f
        val jambOffset = width / 2 - trim / 2
        val parts = listOf(
            Vector3(x - dirX * jambOffset, height / 2, z - dirZ * jambOffset) to Vector3(trim, height, depth),
            Vector3(x + dirX * jambOffset, height / 2, z + dirZ * jambOffset) to Vector3(trim, height, depth),
            Vector3(x, height - trim / 2, z) to Vector3(width, trim, depth),
        )
        for ((center, size) in parts) {
            val entity = Entity.create()
            entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
            entity.setComponent(centeredBox(size))
            entity.setComponent(Material().apply {
                baseColor = color
                roughness = 0.6f
                unlit = false
            })
            entity.setComponent(Transform(Pose(t = center, q = quat)))
            entity.setComponent(Visible(true))
            doorEntities.add(entity)
        }
        if (doorType == "patio") {
            generateDoorLeaves(doorJson, x, z, width, height - trim, dirX, dirZ, rotationDeg, color)
        }
    }

    /**
     * The doors themselves for a door to the yard, left open so it can be walked
     * through: a sliding glass door's moving panel is slid across the fixed one;
     * French doors and a plain door stand swung out into the yard.
     */
    private fun generateDoorLeaves(
        doorJson: JSONObject, x: Float, z: Float, width: Float, height: Float,
        dirX: Float, dirZ: Float, rotationDeg: Float, frameColor: Color4,
    ) {
        val inner = width - 2 * 0.08f  // between the jambs
        // Which way is outside: the wall side the backend put the door on.
        val (outX, outZ) = when (doorJson.optString("side")) {
            "front" -> 0f to -1f
            "back" -> 0f to 1f
            "left" -> -1f to 0f
            "right" -> 1f to 0f
            else -> 0f to 0f
        }
        val glass = Color4(0.7f, 0.9f, 1.0f, 0.3f)
        when (doorJson.optString("style")) {
            "sliding_glass" -> {
                // Two panels on two tracks; the moving one is slid over the fixed one,
                // leaving the other half open.
                val panelW = inner / 2 + 0.04f
                val track = WALL_THICKNESS / 4
                val fixedAt = -inner / 4
                for ((along, depthOffset) in listOf(fixedAt to -track, fixedAt + 0.12f to track)) {
                    addLeaf(
                        x + dirX * along + outX * depthOffset, z + dirZ * along + outZ * depthOffset,
                        panelW, height, rotationDeg, glass, frameColor,
                    )
                }
            }
            "french" -> {
                // Two glass leaves, hinged at the jambs, swung out square to the wall.
                val leafW = inner / 2
                for (hinge in listOf(-1f, 1f)) {
                    val hx = x + dirX * hinge * inner / 2
                    val hz = z + dirZ * hinge * inner / 2
                    addLeaf(
                        hx + outX * (leafW / 2 + WALL_THICKNESS / 2), hz + outZ * (leafW / 2 + WALL_THICKNESS / 2),
                        leafW, height, rotationDeg + 90f, glass, frameColor,
                    )
                }
            }
            else -> {
                // A plain door, open square to the wall at one jamb.
                val hx = x - dirX * inner / 2
                val hz = z - dirZ * inner / 2
                addLeaf(
                    hx + outX * (inner / 2 + WALL_THICKNESS / 2), hz + outZ * (inner / 2 + WALL_THICKNESS / 2),
                    inner, height, rotationDeg + 90f, null, frameColor,
                )
            }
        }
    }

    /**
     * One door leaf [w] wide standing on the floor, centred on ([x], [z]) and running
     * along [rotationDeg]: a glass pane in a frame, or a solid leaf when [glass] is null.
     */
    private fun addLeaf(
        x: Float, z: Float, w: Float, h: Float, rotationDeg: Float, glass: Color4?, frameColor: Color4,
    ) {
        val rad = Math.toRadians(rotationDeg.toDouble())
        val ax = Math.cos(rad).toFloat()
        val az = Math.sin(rad).toFloat()
        val quat = yawAlong(rotationDeg)
        val stile = 0.06f
        val thick = 0.05f
        val boxes = if (glass == null) {
            listOf(Triple(Vector3(x, h / 2, z), Vector3(w, h, thick), frameColor))
        } else {
            listOf(
                Triple(Vector3(x, h / 2, z), Vector3(w - 2 * stile, h - 2 * stile, thick / 2), glass),
                Triple(Vector3(x - ax * (w - stile) / 2, h / 2, z - az * (w - stile) / 2), Vector3(stile, h, thick), frameColor),
                Triple(Vector3(x + ax * (w - stile) / 2, h / 2, z + az * (w - stile) / 2), Vector3(stile, h, thick), frameColor),
                Triple(Vector3(x, stile / 2, z), Vector3(w, stile, thick), frameColor),
                Triple(Vector3(x, h - stile / 2, z), Vector3(w, stile, thick), frameColor),
            )
        }
        for ((center, size, color) in boxes) {
            val entity = Entity.create()
            entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
            entity.setComponent(centeredBox(size))
            entity.setComponent(Material().apply {
                baseColor = color
                roughness = if (color === glass) 0.1f else 0.6f
                unlit = false
            })
            entity.setComponent(Transform(Pose(t = center, q = quat)))
            entity.setComponent(Visible(true))
            doorEntities.add(entity)
        }
    }

    /**
     * Generate a window.
     */
    private fun generateWindow(windowJson: JSONObject) {
        val position = windowJson.getJSONObject("position")
        val width = windowJson.optDouble("width", 4.0).toFloat() * SCALE
        val height = windowJson.optDouble("height", 5.0).toFloat() * SCALE
        val rotationDeg = windowJson.optDouble("rotation", 0.0).toFloat()

        val x = position.optDouble("x", 0.0).toFloat() * SCALE
        val y = position.optDouble("y", 3.0).toFloat() * SCALE
        val z = position.optDouble("z", 0.0).toFloat() * SCALE

        // Create window entity (semi-transparent blue)
        val entity = Entity.create()
        entity.setComponent(Mesh(mesh = "mesh://box".toUri()))
        entity.setComponent(centeredBox(Vector3(width, height, 0.05f)))
        entity.setComponent(Material().apply {
            baseColor = Color4(0.7f, 0.9f, 1.0f, 0.3f) // Light blue glass
            roughness = 0.1f
            metallic = 0.1f
            unlit = false
        })
        val windowQuat = yawAlong(rotationDeg)
        entity.setComponent(Transform(Pose(t = Vector3(x, y, z), q = windowQuat)))
        entity.setComponent(Visible(true))

        windowEntities.add(entity)
    }

    /**
     * Rotation that turns a box's local x axis to run along [degrees], measured the
     * backend's way: atan2(dz, dx), so 90 points along +z. The SDK's yaw turns +x
     * toward (cos θ, -sin θ), so the angle is negated. (At 0/90/180 the sign makes no
     * visible difference; the diagonal faces of a bay window need it.)
     */
    private fun yawAlong(degrees: Float) = com.meta.spatial.core.Quaternion(0f, -degrees, 0f)

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
        floorAreas.clear()
        groundY = 0f
        exterior.clear()
        furniture.clear()
    }

    /**
     * The height (world units) of what the player stands on at (x, z): a room's
     * floor (0) inside the house, the yard's ground outside it.
     */
    fun floorLevelAt(x: Float, z: Float): Float =
        if (floorAreas.any { x >= it[0] && x <= it[1] && z >= it[2] && z <= it[3] }) 0f else groundY

    /**
     * Toggle x-ray vision — hides/shows walls and ceilings so floors remain visible.
     */
    fun setXRayEnabled(enabled: Boolean) {
        wallCeilingEntities.forEach { it.setComponent(Visible(!enabled)) }
        exterior.setShellVisible(!enabled)
        Log.i(TAG, "${if (enabled) "🔍 X-ray ON" else "🔒 X-ray OFF"} | ${wallCeilingEntities.size} entities")
    }

    /**
     * Get room info list for spawning label beacons.
     */
    fun getRoomInfoList(): List<RoomInfo> = roomInfoList.toList()
}
