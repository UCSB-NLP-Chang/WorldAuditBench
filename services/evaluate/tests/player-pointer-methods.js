    onRequestLock() {
        void this.videoElementParent.requestPointerLock();
    }
    onLockStateChange() {
        const pointerLockElement = document.pointerLockElement || document.mozPointerLockElement;
        if (pointerLockElement === this.videoElementParent) {
            lib_pixelstreamingcommon_ue5_6_1.Logger.Info('Pointer locked');
            document.addEventListener('mousemove', this.onMouseMoveListener);
        }
        else {
            lib_pixelstreamingcommon_ue5_6_1.Logger.Info('The pointer lock status is now unlocked');
            document.removeEventListener('mousemove', this.onMouseMoveListener);
            // If mouse loses focus, send a key up for all of the currently held-down keys
            // This is necessary as when the mouse loses focus, the windows stops listening for events and as such
            // the keyup listener won't get fired
            const activeKeys = this.activeKeys.getActiveKeys();
            activeKeys.forEach((key) => {
                this.streamMessageController.toStreamerHandlers.get('KeyUp')([key]);
            });
        }
    }

