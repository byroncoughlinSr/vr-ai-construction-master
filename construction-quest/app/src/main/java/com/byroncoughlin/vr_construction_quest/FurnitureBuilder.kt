package com.byroncoughlin.vr_construction_quest

import android.util.Log
import com.meta.spatial.core.Entity
import com.meta.spatial.toolkit.AppSystemActivity
import org.json.JSONArray
import org.json.JSONObject

/**
 * Builds the furniture from the geometry's "furniture" object (vr_furniture.py):
 * "meshes" (low-poly pieces in metres, base on the floor, front toward +z), "pieces"
 * that place them in the rooms, and "models" (.glb pieces made from photos). It is
 * drawn like the plants, through [MeshInstances]; [clear] removes it all.
 */
class FurnitureBuilder(activity: AppSystemActivity) {
    companion object {
        private const val TAG = "FurnitureBuilder"
    }

    private val entities = mutableListOf<Entity>()
    private val instances = MeshInstances(activity, "furniture", roughness = 0.8f)

    fun build(furniture: JSONObject) {
        clear()
        val meshes = furniture.optJSONObject("meshes") ?: JSONObject()
        val pieces = furniture.optJSONArray("pieces") ?: JSONArray()
        for (i in 0 until pieces.length()) entities += instances.buildInstance(pieces.getJSONObject(i), meshes)
        val models = furniture.optJSONArray("models") ?: JSONArray()
        for (i in 0 until models.length()) instances.buildModel(models.getJSONObject(i))?.let { entities.add(it) }
        Log.i(
            TAG,
            "🛋️ Furniture built: ${pieces.length()} pieces (${instances.meshCount} meshes), " +
                "${models.length()} photo models",
        )
    }

    fun clear() {
        entities.forEach { it.destroy() }
        entities.clear()
        instances.clear()
    }
}
