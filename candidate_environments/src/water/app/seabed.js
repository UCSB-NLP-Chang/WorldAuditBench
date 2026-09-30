// Sandy seabed (two-resolution height mesh with a PBR sand material + caustics), lights and plankton.
import * as THREE from 'three';
import { seabedHeight } from '../upstream/scene/environment.js';
import { pbr } from './assets.js';
import { applyUnderwater } from './caustics.js';

const INNER = 110;      // detailed patch (metres)
const OUTER = 440;      // far floor
const INNER_SEGS = 220;
const OUTER_SEGS = 88;  // 5 m cells so the patch edge lies on grid lines

function heightPlane(size, segments, cut = null) {
  const geo = new THREE.PlaneGeometry(size, size, segments, segments);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    pos.setY(i, seabedHeight(x, z));
    uv.setXY(i, x, z);   // metres, tiled by the material
  }
  if (cut) {
    const idx = geo.index.array;
    const kept = [];
    for (let i = 0; i < idx.length; i += 3) {
      let inside = true;
      for (let k = 0; k < 3; k++) {
        const x = pos.getX(idx[i + k]), z = pos.getZ(idx[i + k]);
        if (Math.abs(x) > cut + 0.01 || Math.abs(z) > cut + 0.01) inside = false;
      }
      if (!inside) kept.push(idx[i], idx[i + 1], idx[i + 2]);
    }
    geo.setIndex(kept);
  }
  pos.needsUpdate = true;
  geo.computeVertexNormals();
  return geo;
}

function createParticleTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 32;
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(16, 16, 0, 16, 16, 16);
  g.addColorStop(0, 'rgba(210,255,250,0.95)');
  g.addColorStop(0.28, 'rgba(116,223,225,0.72)');
  g.addColorStop(1, 'rgba(80,190,205,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 32, 32);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export async function createSeabed(scene, sunDirection, { shadowMapResolution = 2048 } = {}) {
  const sand = await pbr('coast_sand_01', 3.2, { roughness: 0.95, normalScale: 0.9, color: 0xd9cdb6 });
  applyUnderwater(sand, { strength: 1.1, scale: 0.42 });
  const sandFar = await pbr('coast_sand_01', 9.0, { roughness: 1, normalScale: 0.4, color: 0xc9bfa9 });
  applyUnderwater(sandFar, { strength: 0.6, scale: 0.42 });

  const inner = new THREE.Mesh(heightPlane(INNER, INNER_SEGS), sand);
  inner.receiveShadow = true;
  inner.name = 'SEABED';
  scene.add(inner);
  const outer = new THREE.Mesh(heightPlane(OUTER, OUTER_SEGS, INNER / 2), sandFar);
  outer.receiveShadow = true;
  outer.name = 'SEABED_FAR';
  scene.add(outer);

  // plankton motes (upstream)
  let randomState = 0x7f4a7c15;
  const rnd = () => { randomState = (Math.imul(randomState, 1664525) + 1013904223) >>> 0; return randomState / 4294967296; };
  const particleCount = 700;
  const particlePositions = new Float32Array(particleCount * 3);
  for (let i = 0; i < particleCount; i++) {
    const angle = rnd() * Math.PI * 2;
    const radius = Math.sqrt(rnd()) * 40;
    particlePositions[i * 3] = Math.cos(angle) * radius;
    particlePositions[i * 3 + 1] = -8 + rnd() * 8.5;
    particlePositions[i * 3 + 2] = Math.sin(angle) * radius;
  }
  const particleGeometry = new THREE.BufferGeometry();
  particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
  const particleMaterial = new THREE.PointsMaterial({
    map: createParticleTexture(), color: 0x70d9dd, size: 0.05, sizeAttenuation: true,
    transparent: true, opacity: 0, depthWrite: false, alphaTest: 0.015, blending: THREE.AdditiveBlending,
  });
  const particles = new THREE.Points(particleGeometry, particleMaterial);
  particles.frustumCulled = false;
  particles.renderOrder = 4;
  scene.add(particles);

  const hemisphereLight = new THREE.HemisphereLight(0x9ad7ff, 0x06373f, 1.65);
  scene.add(hemisphereLight);
  const ambientLight = new THREE.AmbientLight(0x2f8496, 0);
  scene.add(ambientLight);
  // Under water the sun refracts to a much steeper angle (Snell): light the reef from there,
  // otherwise the grazing evening sun leaves every up-facing surface in shadow.
  const hx = sunDirection.x / 1.333, hz = sunDirection.z / 1.333;
  const refracted = new THREE.Vector3(hx, Math.sqrt(Math.max(0.05, 1 - hx * hx - hz * hz)), hz).normalize();
  const sunLight = new THREE.DirectionalLight(0xffe2bc, 3.6);
  sunLight.position.copy(refracted).multiplyScalar(40);
  sunLight.castShadow = true;
  let currentShadowMapResolution = shadowMapResolution;
  sunLight.shadow.mapSize.set(shadowMapResolution, shadowMapResolution);
  const sc = sunLight.shadow.camera;
  sc.left = -30; sc.right = 30; sc.top = 30; sc.bottom = -30; sc.near = 1; sc.far = 90;
  sunLight.shadow.bias = -0.0004;
  sunLight.shadow.normalBias = 0.03;
  scene.add(sunLight);

  return {
    underwaterObjects: [inner, outer],
    meshes: { inner, outer },
    requestShadowUpdate() {},
    setShadowMapResolution(resolution) {
      const next = Math.max(512, Math.round(resolution));
      if (next === currentShadowMapResolution) return;
      currentShadowMapResolution = next;
      sunLight.shadow.mapSize.set(next, next);
      sunLight.shadow.map?.dispose();
      sunLight.shadow.map = null;
    },
    getDiagnostics() { return { shadowMapResolution: currentShadowMapResolution }; },
    update(time, underwaterMix) {
      hemisphereLight.intensity = THREE.MathUtils.lerp(1.65, 2.1, underwaterMix);
      hemisphereLight.color.setHex(underwaterMix > 0.5 ? 0x8fd8ee : 0x9ad7ff);
      hemisphereLight.groundColor.setHex(underwaterMix > 0.5 ? 0x1d6a6e : 0x06373f);
      ambientLight.intensity = underwaterMix * 0.7;
      sunLight.intensity = THREE.MathUtils.lerp(3.6, 2.8, underwaterMix);
      particleMaterial.opacity = underwaterMix * 0.5;
      particles.visible = underwaterMix > 0.015;
      particles.rotation.y = time * 0.0025;
      particles.position.y = Math.sin(time * 0.12) * 0.1;
    },
  };
}
