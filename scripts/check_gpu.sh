#!/bin/bash
# Headless-Chromium render-backend self-check: tries vulkan / gl-egl / swiftshader,
# printing the renderer string and env0 fps. SwiftShader/llvmpipe = software rendering.
cd "$(dirname "$0")/.."
exec .venv/bin/python -m harness.bridge --check-gpu "$@"
