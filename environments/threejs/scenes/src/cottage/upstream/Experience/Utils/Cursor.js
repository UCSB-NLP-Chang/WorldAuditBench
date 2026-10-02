import { Box3, Vector3, Raycaster } from 'three'

import Experience from '../Experience'

export default class Cursor {
    constructor() {
        this.experience = new Experience()
        this.controls = this.experience.controls
        this.camera = this.experience.camera.instance
        this.states = this.experience.states
        this.physics = this.experience.physics
        this.sfx = this.experience.sfx

        this.raycaster = new Raycaster()
        this.raycastObjects = null

        // Object involved with cursor interaction
        this.cottage = this.experience.world.cottage
        this.wallFront = this.cottage.physicsFront
        this.wallLeft = this.cottage.physicsLeft
        this.player = this.experience.world.player

        this.setCottageObjects()

        // Trigger events
        this.controls.on('pointerup', () => {
            const { start, end } = this.controls.pointer

            if (start.x === end.x && start.y === end.y)
                this.toggleCottageVisibility()
        })

        // Reduce raycasting by checking only when cursor moves
        this.controls.on('pointermove', () => {
            this.updateRaycastObjects()
        })
    }

    // Cursor styles
    openHand() {
        document.body.style.cursor = `url(${window.__resolveAsset ? window.__resolveAsset('icons/hand_open.svg') : '/icons/hand_open.svg'}), auto`
    }

    grabHand() {
        document.body.style.cursor = `url(${window.__resolveAsset ? window.__resolveAsset('icons/hand_closed.svg') : '/icons/hand_closed.svg'}), auto`
    }

    pointHand() {
        document.body.style.cursor = `url(${window.__resolveAsset ? window.__resolveAsset('icons/hand_point.svg') : '/icons/hand_point.svg'}), auto`
    }

    lookEye() {
        document.body.style.cursor = `url(${window.__resolveAsset ? window.__resolveAsset('icons/look_eye.svg') : '/icons/look_eye.svg'}), auto`
    }

    setCottageObjects() {
        // Wall Meshes
        this.frontObjects = [
            this.cottage.items.CottageFrontMerged,
            this.cottage.items.PhysicsCottageFrontMerged,
        ]
        this.leftObjects = [
            this.cottage.items.CottageLeftMerged,
            this.cottage.items.PhysicsCottageLeftMerged,
        ]
    }

    updateRaycastObjects() {
        this.raycaster.setFromCamera(
            this.controls.pointer.coordinate,
            this.camera
        )

        const intersects = this.raycaster.intersectObjects([
            ...this.frontObjects,
            ...this.leftObjects,
        ])

        this.raycastObjects = intersects[0]?.object || null
    }

    toggleCottageVisibility() {
        // benchmark build: the dollhouse toggle (click a wall to fade it out) is outside the agent's action
        // space and made the see-through cases ambiguous - the walls stay up
        if (!window.__COTTAGE_DOLLHOUSE) return
        if (!this.raycastObjects) {
            return
        }

        // Disable toggle if player is within cottage bounding box
        if (this.cottage.cottageArea.isInside(this.player.mesh)) {
            // console.log('Player is inside the cottage!')
            return
        }

        this.sfx.playSelectSound()

        // Toggle front cottage
        if (
            this.frontObjects.find(
                (item) => item.name === this.raycastObjects.name
            )
        ) {
            // console.log('Front cottage clicked')
            this.states.toggleFrontVisbility()
            this.updatePhysicsFront()
        }

        // Toggle left cottage
        if (
            this.leftObjects.find(
                (item) => item.name === this.raycastObjects.name
            )
        ) {
            // console.log('Left cottage clicked')
            this.states.toggleLeftVisbility()
            this.updatePhysicsLeft()
        }
    }

    // Benchmark build: the wall trimesh and its extra colliders (door panel, window glass)
    // are removed / re-created together
    setWallPhysics(wall, visible) {
        const parts = [wall, ...(wall.extras || [])]
        if (!visible) {
            for (const part of parts) {
                if (part.collider) this.physics.world.removeCollider(part.collider)
                part.collider = null
            }
        } else {
            for (const part of parts) {
                if (part.collider) continue
                part.collider = this.physics.world.createCollider(
                    part.colliderDesc,
                    wall.rigidBody
                )
            }
        }
    }

    updatePhysicsLeft() {
        this.setWallPhysics(this.wallLeft, this.states.instance.leftVisibility)
    }

    updatePhysicsFront() {
        this.setWallPhysics(this.wallFront, this.states.instance.frontVisibility)
    }

    update() {
        if (!this.raycastObjects) {
            if (this.controls.pointer.down) {
                // console.log('dragging')
                this.grabHand()
            } else {
                this.openHand()
            }
            return
        }

        // Disable cursor changes when player inside cottage boundary box
        if (this.cottage.cottageArea.isInside(this.player.mesh)) {
            if (this.controls.pointer.down) {
                // console.log('dragging')
                this.grabHand()
            } else {
                this.openHand()
            }
            return
        }

        /**
         * Cursor hovering over objects
         */
        if (
            this.frontObjects.find(
                (item) => item.name === this.raycastObjects.name
            )
        ) {
            if (this.states.instance.frontVisibility) this.pointHand()
            else this.lookEye()
        }

        if (
            this.leftObjects.find(
                (item) => item.name === this.raycastObjects.name
            )
        ) {
            if (this.states.instance.leftVisibility) this.pointHand()
            else this.lookEye()
        }
    }
}
