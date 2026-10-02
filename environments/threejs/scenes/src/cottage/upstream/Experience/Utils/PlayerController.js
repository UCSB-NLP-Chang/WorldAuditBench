/**
 * Based on Rapier's Character Controller
 * (https://github.com/dimforge/rapier.js/blob/master/testbed3d/src/demos/characterController.ts)
 */
import { Vector3 } from 'three'
import Experience from '../Experience'
import EventEmitter from './EventEmitter'

export default class PlayerController extends EventEmitter {
    constructor() {
        super()
        this.jumpEnabled = false   // benchmark build: same action space as the agent (move, turn, look), no jump
        this.experience = new Experience()
        this.camera = this.experience.camera.instance
        this.controls = this.experience.controls
        this.debug = this.experience.debug
        this.physics = this.experience.physics
        this.sfx = this.experience.sfx
        this.time = this.experience.time

        // Player
        this.player = this.experience.world.player
        this.rigidBody = this.player.rigidBody
        this.collider = this.player.collider
        this.mesh = this.player.mesh
        this.debugFolder = this.player.debugFolder

        // Interaction with other models
        this.terrain = this.experience.world.terrain
        this.cottage = this.experience.world.cottage

        // Movement settings
        this.speed = 1.05 // benchmark build: was 0.5 (~1.25 units/s); ~2.6 units/s (review 2026-09-12: still felt slow at 0.8)
        this.jumpStrength = 2.8 // benchmark build: was 5.0 (a jump of ~1.3 character heights)
        this.gravity = 0.1
        this.decaySpeed = 24

        // Camera direction
        this.cameraForward = new Vector3()
        this.cameraRight = new Vector3()
        this.cameraUp = new Vector3(0, 1, 0)

        // Movement state
        this.velocity = new Vector3()
        this.direction = new Vector3()

        this.setController()
        this.setDebug()
    }

    setController() {
        this.controller = this.physics.world.createCharacterController(0.02)
        // Benchmark build: the original step height (5 units) and slope limit (145°) let the
        // player walk over fences, low walls and the well; keep steps to knee height and
        // slopes to what a person can walk up.
        // 2026-09-12: with the rope fences gone the pond bank is reachable; its last step is ~0.45 high, so the
        // step height / slope limits are raised enough to climb back out (still below the picnic table and the well)
        this.controller.enableAutostep(0.5, 0.08, true)
        this.controller.enableSnapToGround(0.15)
        this.controller.slideEnabled(true)
        this.controller.setMaxSlopeClimbAngle((70 * Math.PI) / 180)
        this.controller.setMinSlopeSlideAngle((74 * Math.PI) / 180)
        this.controller.setApplyImpulsesToDynamicBodies(false)
    }

    update() {
        // Forward is based on camera direction
        this.camera.getWorldDirection(this.cameraForward)
        this.cameraForward.y = 0 // Ignore vertical direction
        this.cameraForward.normalize()
        // console.log(this.cameraForward)

        // Friction - movement decay to a stop slowly
        this.velocity.x -= this.velocity.x * this.decaySpeed * 0.01
        this.velocity.z -= this.velocity.z * this.decaySpeed * 0.01

        // Get right vector by rotating forward vector 90° counterclockwise
        this.cameraRight
            .crossVectors(this.cameraForward, this.cameraUp)
            .normalize()

        // Keys States
        const { forward, backward, left, right, jump } = this.controls.keys.down

        // Input direction
        this.direction.x = (left ? -1 : 0) + (right ? 1 : 0)
        this.direction.y = 0
        this.direction.z = (forward ? 1 : 0) + (backward ? -1 : 0)
        this.direction.normalize()

        // Rotate movement direction to match camera orientation
        const moveDir = new Vector3()
        moveDir
            .addScaledVector(this.cameraForward, this.direction.z)
            .addScaledVector(this.cameraRight, this.direction.x)
            .normalize()

        // Apply acceleration
        this.velocity.x += moveDir.x * this.speed * 0.01
        this.velocity.z += moveDir.z * this.speed * 0.01

        this.handleSFX()

        // Player is grounded
        if (this.controller.computedGrounded()) {
            if (jump && this.jumpEnabled) {
                // ⛰️ Jump only if player is on the ground (benchmark build: jumpEnabled = false, no jump key)
                this.sfx.playJumpSound()
                this.jumpRequested = true
                this.velocity.y = this.jumpStrength * 0.01
            } else {
                // Reset vertical velocity when grounded
                // ⭐️ Prevents controller from getting stuck with small obstacles
                this.velocity.y = 0
            }
        } else {
            // Apply gravity if in air
            this.velocity.y -= this.gravity * 0.01
        }

        // console.log('velocity', this.velocity)
        this.updateController()
    }

    handleSFX() {
        const { forward, backward, left, right, jump } = this.controls.keys.down

        // moving any direction
        const isMoving = forward || backward || left || right

        if (isMoving) {
            this.trigger('playerMoving')
            if (this.controller.computedGrounded()) {
                // this.sfx.playWalkingSound()
                if (this.cottage.cottageArea.isInside(this.mesh)) {
                    this.sfx.stopWalkingSound()
                    this.sfx.stopSwimSound()
                    this.sfx.playWalkOnWoodSound()
                } else if (this.terrain.pondArea.isInside(this.mesh)) {
                    this.sfx.stopWalkingSound()
                    this.sfx.stopWalkOnWoodSound()
                    this.sfx.playSwimSound()
                } else {
                    this.sfx.stopWalkOnWoodSound()
                    this.sfx.stopSwimSound()
                    this.sfx.playWalkingSound()
                }
            }
        } else {
            this.sfx.stopWalkOnWoodSound()
            this.sfx.stopSwimSound()
            this.sfx.stopWalkingSound()
        }
    }

    updateController() {
        // benchmark build: the velocity is a per-frame displacement tuned for 60 fps; scale the horizontal part by the
        // real frame time so walking speed does not depend on the frame rate (headless runs at ~30 fps)
        const k = Math.min(3, Math.max(0.25, (this.time.delta || 1 / 60) / (1 / 60)))
        this.controller.computeColliderMovement(
            this.collider, // The collider we would like to move.
            { x: this.velocity.x * k, y: this.velocity.y, z: this.velocity.z * k }
        )

        let movement = this.controller.computedMovement()
        let newPos = this.rigidBody.translation()
        newPos.x += movement.x
        newPos.y += movement.y
        newPos.z += movement.z
        this.rigidBody.setNextKinematicTranslation(newPos)
    }

    setDebug() {
        if (!this.debug.active) return

        const name = '🕹️Player Controller'
        if (this.debugFolder)
            this.debugFolder = this.debugFolder.addFolder(name).close()
        else this.debugFolder = this.debug.ui.addFolder(name).close()

        this.debugFolder.add(this, 'speed', 0, 2.0, 0.01).name('Speed')
        this.debugFolder.add(this, 'gravity', 0, 2.0, 0.01).name('Gravity')
        this.debugFolder
            .add(this, 'jumpStrength', 0, 10, 0.01)
            .name('Jump Strength')
    }
}
