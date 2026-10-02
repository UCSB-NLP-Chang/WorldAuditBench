FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY player.js socket_player.js ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 GRADIO_ANALYTICS_ENABLED=False NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,video,display
RUN apt-get update && apt-get install -y --no-install-recommends libvulkan1 vulkan-tools libegl1 libgl1 libx11-6 libxrandr2 libxi6 libxcursor1 libxinerama1 libasound2 libnss3 libglib2.0-0 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY nvidia_icd.json /etc/vulkan/icd.d/nvidia_icd.json
COPY 10_nvidia.json /usr/share/glvnd/egl_vendor.d/10_nvidia.json
RUN useradd -m -u 1000 user
WORKDIR /home/user/app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
USER user
ENV HOME=/home/user WAB_ASSET_DIR=/home/user/unreal WAB_RUNTIME_CONFIG=/home/user/unreal/runtime.json
COPY --chown=user:user assets.json bootstrap.py ./
RUN python -c "from bootstrap import restore; restore()" && rm -rf /home/user/.cache/huggingface
COPY --chown=user:user . .
COPY --from=frontend --chown=user:user /build/node_modules ./node_modules
COPY --from=frontend --chown=user:user /build/static/player.js ./static/player.js
EXPOSE 7860
CMD ["python", "bootstrap.py"]
