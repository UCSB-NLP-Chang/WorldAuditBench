import {
    Vector3,
    Group,
    Box3,
    AnimationMixer,
    LoopOnce,
    MathUtils,
} from 'three'
import RAPIER from '@dimforge/rapier3d'

import Experience from '../Experience.js'
import { CyclesSettings } from '../Constants.js'
import CameraThirdPerson from '../CameraThirdPerson.js'
import Boundary from '../Utils/Boundary.js'

/**
 * The player: a kinematic Rapier ball collider driven by PlayerController, visualised with the
 * CC0 "RobotExpressive" character (Tomás Laulhé) instead of the original capsule placeholder.
 * Animations: Idle / Walking / Running / Jump, chosen from the controller's velocity.
 */
export default class Player {
    constructor() {
        this.experience = new Experience()
        this.scene = this.experience.scene
        this.resources = this.experience.resources
        this.physics = this.experience.physics
        this.time = this.experience.time
        this.controls = this.experience.controls
        this.camera = this.experience.camera.instance
        this.debug = this.experience.debug
        this.cycle = this.experience.cycles
        this.sfx = this.experience.sfx
        this.overlay = this.experience.overlay

        // Interaction with other models
        this.terrain = this.experience.world.terrain
        this.cottage = this.experience.world.cottage

        this.options = {
            radius: 0.13, // physics capsule radius
            halfHeight: 0.21, // capsule half height (total height 0.68 ~ the character)
            characterHeight: 0.72, // world units, the capsule was 0.7
            initPosition: { x: -0.6, y: -0.35, z: 5 },
            color: CyclesSettings[this.cycle.currentCycle].playerColor,
        }

        this.setMesh()
        this.setCharacter()
        this.setBoundary()
        this.setDebug()

        // Physics
        this.setPhysics()

        // Third Person Camera
        this.cameraPOV = new CameraThirdPerson(this.mesh, this.debugFolder)

        this.soundReady = false
        this.overlay.on('enter', () => {
            this.soundReady = true
        })
    }

    setMesh() {
        // `mesh` is the object the rest of the game follows (physics, camera, coins, cursor)
        this.mesh = new Group()
        this.mesh.name = 'PLAYER'
        const { x, y, z } = this.options.initPosition
        this.mesh.position.set(x, y, z)
        this.scene.add(this.mesh)
    }

    setCharacter() {
        const gltf = this.resources.items.robotModel
        this.character = gltf.scene
        this.character.name = 'PLAYER_CHARACTER'

        // scale to the wanted height and put the feet at the bottom of the physics ball
        const box = new Box3().setFromObject(this.character)
        const size = box.max.y - box.min.y
        const scale = this.options.characterHeight / size
        this.character.scale.setScalar(scale)
        // mesh.y = body.y + 0.1 (physics offset); capsule bottom = body.y - (halfHeight + radius)
        this.character.position.y =
            -(0.1 + this.options.halfHeight + this.options.radius) - box.min.y * scale + 0.01

        this.materials = {}
        this.character.traverse((child) => {
            if (child.isMesh) {
                child.castShadow = true
                child.frustumCulled = false
                if (child.material && child.material.name)
                    this.materials[child.material.name] = child.material
            }
        })
        this.mesh.add(this.character)
        // the benchmark starts in first person: keep the character hidden until the chase view is chosen (V)
        if (this.cameraPOV && this.cameraPOV.firstPerson) this.character.visible = false

        // animations
        this.mixer = new AnimationMixer(this.character)
        this.actions = {}
        for (const clip of gltf.animations) {
            const action = this.mixer.clipAction(clip)
            this.actions[clip.name] = action
            if (clip.name === 'Jump') {
                action.setLoop(LoopOnce, 1)
                action.clampWhenFinished = true
            }
        }
        this.currentAction = 'Idle'
        this.actions.Idle?.play()
        this.jumping = false
        this.wasGrounded = true
        this.facing = Math.PI // model faces +z; start facing the camera
        this.character.rotation.y = this.facing

        this.mixer.addEventListener('finished', (event) => {
            if (event.action === this.actions.Jump) {
                this.jumping = false
                this.playAction(this.wasGrounded ? 'Idle' : 'Idle', 0.15)
            }
        })

        this.updateCycle()
    }

    playAction(name, fade = 0.25) {
        if (this.currentAction === name || !this.actions[name]) return
        const next = this.actions[name]
        const prev = this.actions[this.currentAction]
        next.reset()
        next.enabled = true
        next.setEffectiveWeight(1)
        if (prev && prev !== next) prev.crossFadeTo(next, fade, false)
        next.play()
        this.currentAction = name
    }

    setBoundary() {
        this.playerBox = new Boundary(this.mesh)
    }

    setPhysics() {
        const { x, y, z } = this.options.initPosition

        // Body
        let rigidBodyDesc = RAPIER.RigidBodyDesc.kinematicPositionBased()
        rigidBodyDesc.setTranslation(x, y, z)
        this.rigidBody = this.physics.world.createRigidBody(rigidBodyDesc)

        // Collider (vertical capsule)
        let colliderDesc = RAPIER.ColliderDesc.capsule(
            this.options.halfHeight,
            this.options.radius
        )
        this.collider = this.physics.world.createCollider(
            colliderDesc,
            this.rigidBody
        )

        // Physics update pipeline
        this.physics.addDynamicObject(this.mesh, this.rigidBody, 0.1)
    }

    /**
     * Character animation & facing, from the controller state
     */
    updateCharacter() {
        const controller = this.experience.world.playerController
        if (!controller || !this.mixer) return
        const delta = this.time.delta
        const v = controller.velocity
        const speed = Math.hypot(v.x, v.z) * 60 // per-frame units -> units/s (~1.25 at full speed)
        const grounded = controller.controller.computedGrounded()

        // face the movement direction
        if (speed > 0.08) {
            const target = Math.atan2(v.x, v.z)
            let diff = target - this.facing
            diff = Math.atan2(Math.sin(diff), Math.cos(diff))
            this.facing += diff * Math.min(1, delta * 12)
            this.character.rotation.y = this.facing
        }

        if (controller.jumpRequested) {
            controller.jumpRequested = false
            this.jumping = true
            this.playAction('Jump', 0.08)
        }
        if (!this.jumping) {
            if (speed > 1.05) this.playAction('Running', 0.2)
            else if (speed > 0.08) this.playAction('Walking', 0.2)
            else this.playAction('Idle', 0.3)
            const walk = this.actions.Walking
            if (walk) walk.timeScale = MathUtils.clamp(speed / 0.6, 0.6, 1.4)
        } else if (grounded && !this.wasGrounded && this.actions.Jump.time > 0.6) {
            // landed early: return to locomotion
            this.jumping = false
        }
        this.wasGrounded = grounded
        this.mixer.update(delta)
    }

    update() {
        /**
         * Camera Follow
         */
        if (this.cameraPOV) {
            this.cameraPOV.update()
        }

        this.updateCharacter()

        /**
         * Background Sound
         */
        if (this.soundReady) {
            if (this.cottage.cottageArea.isInside(this.mesh)) {
                this.sfx.stopInsectSound()
                this.sfx.stopUnderwaterSound()
                this.sfx.playJazzSound()
            } else if (this.terrain.pondArea.isInside(this.mesh)) {
                this.sfx.stopInsectSound()
                this.sfx.stopJazzSound()
                this.sfx.playUnderwaterSound()
            } else {
                this.sfx.stopJazzSound()
                this.sfx.stopUnderwaterSound()
                this.sfx.playInsectSound()
            }
        }

        /**
         * Player Box
         */
        if (this.playerBox) this.playerBox.update()
    }

    updateCycle() {
        // Tint the robot's main body with the cycle's player colour (kept from the original design)
        const main = this.materials && this.materials.Main
        if (main) {
            main.color.set(CyclesSettings[this.cycle.currentCycle].playerColor)
        }
    }

    setDebug() {
        if (!this.debug.active) return
        this.debugFolder = this.debug.ui.addFolder('🕴🏻Player').close()
        this.scene.add(this.playerBox.boxHelper)
    }
}
