/**
 * Camera Orbit around the Player
 * Based on CameraThirdPerson by Bruno Simon in Infinite World
 * (https://github.com/brunosimon/infinite-world/blob/master/sources/Game/State/CameraThirdPerson.js)
 *
 * Benchmark build additions: pointer-lock mouse look (click the canvas), a first-person mode
 * (key V, or camera distance below 1) that hides the character, and snap() for scripted views.
 */
import { Vector3, Quaternion, Matrix4 } from 'three'
import Experience from './Experience'
import Slider from './Components/Slider'

export default class CameraThirdPerson {
    constructor(player, debug = null) {
        this.experience = new Experience()
        this.camera = this.experience.camera.instance
        this.pointer = this.experience.controls.pointer
        this.sizes = this.experience.sizes
        this.debug = this.experience.debug
        this.canvas = this.experience.canvas

        this.player = player
        this.target = new Vector3()
        this.position = new Vector3()
        this.quaternion = new Quaternion()
        this.forward = new Vector3()

        this.debugFolder = debug

        this.distance = 4 // how far the camera stays from the player
        this.phi = Math.PI * 0.45 // vertical angle (elevation)
        this.theta = -Math.PI * 0.25 // horizontal angle (azimuth)
        this.aboveOffset = 0.5 // how much above the player the camera looks
        this.eyeHeight = 0.83 // first-person eye height above the player origin: ~1.27 above the ground, just under the 1.3-unit door lintel
        this.phiLimits = { min: 0.1, max: Math.PI - 0.1 }
        this.up = new Vector3(0, 1, 0) // Camera +y up-axis

        this.smoothFactor = 0.1 // smooth camera movement
        this.smoothCameraPosition = new Vector3()

        // benchmark convention: every environment starts in first person (V toggles the chase view)
        this.firstPerson = true
        this.thirdPersonDistance = this.distance
        this.distance = 0

        // UI
        this.ui = new Slider(this)

        this.setPointerLock()
        this.setDebug()
    }

    setPointerLock() {
        this.canvas.addEventListener('click', () => {
            if (document.pointerLockElement !== this.canvas) {
                try {
                    this.canvas.requestPointerLock?.()
                } catch {
                    /* ignore */
                }
            }
        })
        window.addEventListener('keydown', (event) => {
            if (event.code === 'KeyV' && !event.repeat) this.setFirstPerson(!this.firstPerson)
        })
    }

    setFirstPerson(on) {
        this.firstPerson = !!on
        const character = this.player.getObjectByName('PLAYER_CHARACTER')
        if (character) character.visible = !this.firstPerson
        if (this.firstPerson) {
            this.thirdPersonDistance = this.distance
            if (this.phi > Math.PI * 0.75) this.phi = Math.PI * 0.75
        } else {
            this.distance = Math.max(1, this.thirdPersonDistance)
        }
        this.snap()
    }

    // Move the camera immediately (no smoothing) - used after teleports and by scripted views
    snap() {
        this.computePose()
        this.smoothCameraPosition.copy(this.position)
        this.camera.position.copy(this.position)
        this.camera.quaternion.copy(this.quaternion)
    }

    computePose() {
        // 🧮 Spherical Coordinate → camera position
        const sinPhiRadius = Math.sin(this.phi) * this.distance
        const sphericalOffset = new Vector3(
            sinPhiRadius * Math.sin(this.theta),
            Math.cos(this.phi) * this.distance,
            sinPhiRadius * Math.cos(this.theta)
        )

        if (this.firstPerson) {
            this.position.set(
                this.player.position.x,
                this.player.position.y + this.eyeHeight,
                this.player.position.z
            )
            // look along the orbit direction reversed (same forward as the third-person view)
            this.forward
                .set(
                    -Math.sin(this.phi) * Math.sin(this.theta),
                    -Math.cos(this.phi),
                    -Math.sin(this.phi) * Math.cos(this.theta)
                )
                .normalize()
            this.target.copy(this.position).add(this.forward)
        } else {
            // 🎯 Look at player
            this.target.set(
                this.player.position.x,
                this.player.position.y + this.aboveOffset,
                this.player.position.z
            )

            // Camera position = player position + spherical offset, pulled in when a wall,
            // roof or the terrain sits between the player and the camera (physics ray cast)
            let distance = this.distance
            const physics = this.experience.physics
            const player = this.experience.world && this.experience.world.player
            if (physics && physics.world && player && player.collider) {
                const len = sphericalOffset.length() || 1
                const dir = { x: sphericalOffset.x / len, y: sphericalOffset.y / len, z: sphericalOffset.z / len }
                const ray = new physics.RAPIER.Ray(this.target, dir)
                // filter groups: membership bit 0 / filter bit 0 -> skips the invisible benchmark colliders
                const hit = physics.world.castRay(ray, distance + 0.2, true, undefined, (0x0001 << 16) | 0x0001, player.collider)
                if (hit && hit.timeOfImpact < distance) {
                    distance = Math.max(0.35, hit.timeOfImpact - 0.15)
                }
            }
            this.position.copy(this.target).addScaledVector(sphericalOffset, distance / (sphericalOffset.length() || 1))
        }

        // Camera quaternion (eye, target, up)
        const targetMatrix = new Matrix4()
        targetMatrix.lookAt(this.position, this.target, this.up)
        this.quaternion.setFromRotationMatrix(targetMatrix)

        // ⛰️ Clamp Camera to Stay Above Terrain
        const terrain = this.experience.world && this.experience.world.terrain
        if (terrain && !this.firstPerson) {
            const elevation = terrain.getElevationFromTerrain(
                this.position.x,
                this.position.z
            )
            if (elevation !== null && this.position.y < elevation + 0.2) {
                this.position.y = elevation + 0.2
            }
        }
    }

    update() {
        // 🌀 Mouse-based Orbiting: drag, or free look while the pointer is locked
        const locked = document.pointerLockElement === this.canvas
        if (this.pointer.down || locked) {
            // for consistent movement speed across different screen sizes
            const normalisedPointer = this.sizes.normalise(this.pointer.delta)

            this.phi -= normalisedPointer.y * 2.0
            this.theta -= normalisedPointer.x * 2.0

            // Clamp phi to avoid flipping camera upside down
            if (this.phi < this.phiLimits.min) this.phi = this.phiLimits.min
            if (this.phi > this.phiLimits.max) this.phi = this.phiLimits.max
        }

        // camera distance below 1 means first person
        if (!this.firstPerson && this.distance < 1) this.setFirstPerson(true)

        this.computePose()

        // Lerping OFF when pointer is down to prevent jittering
        if (this.pointer.down || locked || this.firstPerson) this.smoothFactor = 1.0
        else this.smoothFactor = 0.1

        //  🕹️ Smooth Camera Movement
        this.smoothCameraPosition.lerp(this.position, this.smoothFactor)

        // Update camera position and rotation
        this.camera.position.copy(this.smoothCameraPosition)
        this.camera.quaternion.copy(this.quaternion)
    }

    setDebug() {
        if (!this.debug.active) return

        const name = '📹 Camera Third Person'
        if (this.debugFolder)
            this.debugFolder = this.debugFolder.addFolder(name).close()
        else this.debugFolder = this.debug.ui.addFolder(name).close()

        this.debugFolder
            .add(this, 'distance', 0, 20.0, 0.01)
            .name('Camera Distance')
    }
}
