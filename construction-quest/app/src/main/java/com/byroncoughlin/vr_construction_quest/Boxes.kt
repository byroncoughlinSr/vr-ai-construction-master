package com.byroncoughlin.vr_construction_quest

import com.meta.spatial.core.Vector3
import com.meta.spatial.toolkit.Box

/**
 * A Box component of the given full size, centred on its entity's Transform.
 *
 * The SDK's constructor is Box(min, max): two corners in the entity's local space.
 * Passing a single vector sets only `min` (max defaults to the origin), which puts
 * the box beside its entity rather than around it. Every box should go through here.
 */
fun centeredBox(size: Vector3): Box {
    val half = Vector3(size.x / 2f, size.y / 2f, size.z / 2f)
    return Box(Vector3(-half.x, -half.y, -half.z), half)
}
