import { Vector3, Quaternion } from 'three'
import RAPIER from '@dimforge/rapier3d'

import Experience from '../Experience.js'

/**
 * Benchmark build: invisible colliders that complete the physics of the baked environment.
 *
 * The rope fences of Environment.Merged are thin posts (0.52 tall) with ropes sagging to
 * 0.15-0.25 units above the ground, which a capsule character simply rides over. One box per
 * fence span (post to post, following the terrain) makes them solid. Post positions were
 * extracted from the connected components of the merged mesh (32-vertex pieces, 0.52 tall,
 * standing on the terrain); see src/cottage/README.md.
 */
const FENCES = [
    // east side of the front path
    [
        [0.57, 2.23],
        [0.24, 3.17],
        [-0.09, 4.51],
        [-0.15, 5.62],
        [-0.46, 6.53],
    ],
    // west side of the path, along the west wall, then along the stairs up to the well
    [
        [-0.99, 2.27],
        [-1.47, 1.37],
        [-1.47, 0.3],
        [-1.4, -1.23],
        [-1.52, -3.09],
        [-2.0, -4.45],
        [-3.19, -5.53],
        [-3.96, -6.38],
        [-4.82, -6.97],
        [-6.38, -6.91],
        [-7.44, -6.69],
        [-8.25, -6.8],
    ],
]
const FENCE_HEIGHT = 0.6 // top of the box above the highest adjacent walking surface
const FENCE_THICKNESS = 0.06
// collision group: membership bit 1 only, so the camera ray (which tests bit 0) ignores the
// invisible boxes while the player capsule (default groups) still collides with them
export const INVISIBLE_GROUPS = (0x0002 << 16) | 0xffff

export default class ExtraColliders {
    constructor() {
        this.experience = new Experience()
        this.physics = this.experience.physics
        this.terrain = this.experience.world.terrain

        this.colliders = []
        this.setFences()
    }

    // walking surface at (x, z): first physics hit below terrain + 1.5 (ignores tree canopies)
    groundAt(x, z) {
        const terrain = this.terrain.getElevationFromTerrain(x, z)
        const base = terrain === null || terrain === undefined ? 0 : terrain
        const ray = new RAPIER.Ray({ x, y: base + 1.5, z }, { x: 0, y: -1, z: 0 })
        const hit = this.physics.world.castRay(ray, 3.0, true)
        return hit ? base + 1.5 - hit.timeOfImpact : base
    }

    // ground range next to a post (samples around it, away from the post itself)
    groundRange(x, z, dx, dz) {
        let min = Infinity
        let max = -Infinity
        for (const [ox, oz] of [
            [dz, -dx],
            [-dz, dx],
            [dx, dz],
            [-dx, -dz],
        ]) {
            const y = this.groundAt(x + ox * 0.25, z + oz * 0.25)
            if (y < min) min = y
            if (y > max) max = y
        }
        return { min, max }
    }

    setFences() {
        const bodyDesc = RAPIER.RigidBodyDesc.fixed()
        this.body = this.physics.world.createRigidBody(bodyDesc)

        const xAxis = new Vector3(1, 0, 0)
        const dir = new Vector3()
        const quaternion = new Quaternion()
        this.chainColliders = []   // benchmark: colliders per fence chain
        // Review 2026-09-12: the rope fences are removed from the benchmark garden altogether (app/bugs.js
        // collapses their geometry) - they made walking miserable - so no fence boxes are created any more.
        if (!window.__COTTAGE_FENCES) return
        for (const chain of FENCES) {
            const chainList = []
            this.chainColliders.push(chainList)
            for (let i = 0; i + 1 < chain.length; i++) {
                const [x0, z0] = chain[i]
                const [x1, z1] = chain[i + 1]
                const len2d = Math.hypot(x1 - x0, z1 - z0)
                if (len2d > 2.5 || len2d < 0.05) continue // not a span (gap in the fence)
                const ux = (x1 - x0) / len2d
                const uz = (z1 - z0) / len2d
                const g0 = this.groundRange(x0, z0, ux, uz)
                const g1 = this.groundRange(x1, z1, ux, uz)
                // box from a little below the lowest ground to FENCE_HEIGHT above the highest
                const bottom0 = g0.min - 0.15
                const bottom1 = g1.min - 0.15
                const top0 = g0.max + FENCE_HEIGHT
                const top1 = g1.max + FENCE_HEIGHT
                const y0 = (bottom0 + top0) / 2
                const y1 = (bottom1 + top1) / 2
                const halfHeight = Math.max(top0 - y0, top1 - y1)
                dir.set(x1 - x0, y1 - y0, z1 - z0)
                const length = dir.length()
                dir.normalize()
                quaternion.setFromUnitVectors(xAxis, dir)
                const desc = RAPIER.ColliderDesc.cuboid(
                    length / 2 + 0.03,
                    halfHeight,
                    FENCE_THICKNESS / 2
                )
                    .setTranslation((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
                    .setRotation({ x: quaternion.x, y: quaternion.y, z: quaternion.z, w: quaternion.w })
                    .setCollisionGroups(INVISIBLE_GROUPS)
                const created = this.physics.world.createCollider(desc, this.body)
                this.colliders.push(created)
                chainList.push(created)
            }
        }
    }
}
