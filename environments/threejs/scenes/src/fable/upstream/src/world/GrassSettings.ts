import { GRASS } from '../config';

export interface GrassSettings {
  densityMultiplier: number;
  heightMultiplier: number;
  widthMultiplier: number;
  coverageExponent: number;
  edgeDensityMultiplier: number;
  undergrowthMultiplier: number;
  instanceDensityCap: number;
  nearLodDistance: number;
  midLodDistance: number;
  renderDistance: number;
  colorContrast: number;
  colorVariation: number;
}

export const GRASS_DEFAULTS: Readonly<GrassSettings> = {
  densityMultiplier: GRASS.densityMultiplier,
  heightMultiplier: GRASS.heightMultiplier,
  widthMultiplier: GRASS.widthMultiplier,
  coverageExponent: GRASS.coverageExponent,
  edgeDensityMultiplier: GRASS.edgeDensityMultiplier,
  undergrowthMultiplier: GRASS.undergrowthMultiplier,
  instanceDensityCap: GRASS.instanceDensityCap,
  nearLodDistance: GRASS.nearLodDistance,
  midLodDistance: GRASS.midLodDistance,
  renderDistance: GRASS.renderDistance,
  colorContrast: GRASS.colorContrast,
  colorVariation: GRASS.colorVariation,
};

export function createGrassSettings(): GrassSettings {
  return { ...GRASS_DEFAULTS };
}
