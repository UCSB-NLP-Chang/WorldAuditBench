// @dimforge/rapier3d -> rapier3d-compat (wasm inlined); the app expects the module to be ready on import.
import RAPIER, { init } from '../../vendor/rapier.es.js';
await init();
export default RAPIER;
