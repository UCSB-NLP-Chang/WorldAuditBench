export interface HackMenuState {
  timeOfDay: number;
  weather: string;
  autoWeather: boolean;
  cycleScale: number;
  cloudCover: number;
  cloudDark: number;
  rain: number;
  windStrength: number;
  windDirection: number;
  fogScale: number;
  lightScale: number;
  exposure: number;
  grassDensity: number;
  grassHeight: number;
  grassWidth: number;
  grassCoverage: number;
  grassEdgeDensity: number;
  undergrowthDensity: number;
}

export interface HackMenuHandlers {
  weatherOptions: readonly string[];
  getState(): HackMenuState;
  setTime(value: number): void;
  setCycleScale(value: number): void;
  setWeather(value: string): void;
  setAutoWeather(value: boolean): void;
  setCloudCover(value: number): void;
  setCloudDark(value: number): void;
  setRain(value: number): void;
  setWindStrength(value: number): void;
  setWindDirection(value: number): void;
  setFogScale(value: number): void;
  setLightScale(value: number): void;
  setExposure(value: number): void;
  setGrassDensity(value: number): void;
  setGrassHeight(value: number): void;
  setGrassWidth(value: number): void;
  setGrassCoverage(value: number): void;
  setGrassEdgeDensity(value: number): void;
  setUndergrowthDensity(value: number): void;
  randomize(): void;
  reset(): void;
}

/** Minimal HUD: FPS, seed, quality, interaction, and live world controls. */
export class Hud {
  readonly promptEl: HTMLElement;
  readonly messageEl: HTMLElement;
  private fpsEl: HTMLElement;
  private seedEl: HTMLElement;
  private qualityEl: HTMLElement;
  private statusEl: HTMLElement;
  private startOverlay: HTMLElement;
  private underwaterEl: HTMLElement;
  private chromeEl: HTMLElement;
  private loadingScreen: HTMLElement;
  private hackMenu: HTMLElement;
  private chromeTimer: number | null = null;
  private hackHandlers: HackMenuHandlers | null = null;

  constructor() {
    this.fpsEl = document.getElementById('fps')!;
    this.seedEl = document.getElementById('seed')!;
    this.qualityEl = document.getElementById('quality')!;
    this.statusEl = document.getElementById('status')!;
    this.promptEl = document.getElementById('interact-prompt')!;
    this.messageEl = document.getElementById('interact-message')!;
    this.startOverlay = document.getElementById('start-overlay')!;
    this.underwaterEl = document.getElementById('underwater-overlay')!;
    this.chromeEl = document.getElementById('hud-chrome')!;
    this.loadingScreen = document.getElementById('loading-screen')!;
    this.hackMenu = document.getElementById('hack-menu')!;
  }

  /**
   * Reveal the HUD chrome (stats + control hints) and auto-hide it again after
   * 5 seconds. Pressing T calls this to peek the HUD back into view.
   */
  revealChrome(): void {
    this.chromeEl.classList.remove('hidden');
    if (this.chromeTimer !== null) window.clearTimeout(this.chromeTimer);
    this.chromeTimer = window.setTimeout(() => {
      this.chromeEl.classList.add('hidden');
      this.chromeTimer = null;
    }, 5000);
  }

  /** Switch the loading screen to its "ready" state; click enters the world. */
  loadingReady(onEnter: () => void): void {
    this.loadingScreen.classList.add('ready');
    const enter = (): void => {
      this.loadingScreen.removeEventListener('click', enter);
      this.loadingScreen.classList.add('dismissed');
      onEnter();
    };
    this.loadingScreen.addEventListener('click', enter);
  }

  /** Drop the loading screen immediately (used by ?noui screenshot mode). */
  dismissLoading(): void {
    this.loadingScreen.classList.add('dismissed');
  }

  /** Time-of-day clock + weather + fly indicator. */
  setStatus(timeOfDay: number, weather: string, flying: boolean, swimming: boolean): void {
    const minutes = Math.floor(timeOfDay * 24 * 60);
    const hh = String(Math.floor(minutes / 60)).padStart(2, '0');
    const mm = String(minutes % 60).padStart(2, '0');
    const movement = flying ? ' \u00b7 FLYING' : swimming ? ' \u00b7 SWIMMING' : '';
    this.statusEl.textContent = `${hh}:${mm} \u00b7 ${weather}${movement}`;
  }

  setUnderwater(under: boolean): void {
    this.underwaterEl.classList.toggle('visible', under);
  }

  setSeed(seed: number): void {
    this.seedEl.textContent = `Seed: ${seed}`;
  }

  setQuality(label: string): void {
    this.qualityEl.textContent = `Quality: ${label}`;
  }

  setFps(fps: number): void {
    this.fpsEl.textContent = `FPS: ${Math.round(fps)}`;
  }

  onStartClick(handler: () => void): void {
    this.startOverlay.addEventListener('click', handler);
  }

  hideStartOverlay(): void {
    this.startOverlay.classList.add('hidden');
  }

  showStartOverlay(): void {
    this.startOverlay.classList.remove('hidden');
  }

  isHackMenuOpen(): boolean {
    return this.hackMenu.classList.contains('visible');
  }

  toggleHackMenu(force?: boolean): boolean {
    const open = force ?? !this.isHackMenuOpen();
    this.hackMenu.classList.toggle('visible', open);
    if (open) {
      this.hideStartOverlay();
      this.syncHackMenu();
    } else if (!document.pointerLockElement) {
      this.showStartOverlay();
    }
    return open;
  }

  bindHackMenu(handlers: HackMenuHandlers): void {
    this.hackHandlers = handlers;
    const weather = document.getElementById('hack-weather') as HTMLSelectElement;
    for (const name of handlers.weatherOptions) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      weather.appendChild(option);
    }
    const custom = document.createElement('option');
    custom.value = 'custom';
    custom.textContent = 'custom';
    custom.disabled = true;
    weather.appendChild(custom);

    const bindRange = (id: string, setter: (value: number) => void) => {
      const input = document.getElementById(id) as HTMLInputElement;
      input.addEventListener('input', () => {
        setter(Number(input.value));
        this.syncHackMenu();
      });
    };
    bindRange('hack-time', handlers.setTime);
    bindRange('hack-cycle', handlers.setCycleScale);
    bindRange('hack-cloud', handlers.setCloudCover);
    bindRange('hack-cloud-dark', handlers.setCloudDark);
    bindRange('hack-rain', handlers.setRain);
    bindRange('hack-wind', handlers.setWindStrength);
    bindRange('hack-wind-dir', handlers.setWindDirection);
    bindRange('hack-fog', handlers.setFogScale);
    bindRange('hack-light', handlers.setLightScale);
    bindRange('hack-exposure', handlers.setExposure);
    bindRange('hack-grass-density', handlers.setGrassDensity);
    bindRange('hack-grass-height', handlers.setGrassHeight);
    bindRange('hack-grass-width', handlers.setGrassWidth);
    bindRange('hack-grass-coverage', handlers.setGrassCoverage);
    bindRange('hack-grass-edge-density', handlers.setGrassEdgeDensity);
    bindRange('hack-undergrowth-density', handlers.setUndergrowthDensity);

    weather.addEventListener('change', () => {
      handlers.setWeather(weather.value);
      this.syncHackMenu();
    });
    const autoWeather = document.getElementById('hack-auto-weather') as HTMLInputElement;
    autoWeather.addEventListener('change', () => handlers.setAutoWeather(autoWeather.checked));
    document.getElementById('hack-randomize')!.addEventListener('click', () => {
      handlers.randomize();
      this.syncHackMenu();
    });
    document.getElementById('hack-reset')!.addEventListener('click', () => {
      handlers.reset();
      this.syncHackMenu();
    });
    document.getElementById('hack-close')!.addEventListener('click', () => this.toggleHackMenu(false));
    this.syncHackMenu();
  }

  syncHackMenu(): void {
    if (!this.hackHandlers) return;
    const state = this.hackHandlers.getState();
    const setRange = (id: string, value: number, text: string) => {
      (document.getElementById(id) as HTMLInputElement).value = String(value);
      const output = document.getElementById(`${id}-value`);
      if (output) output.textContent = text;
    };
    const minutes = Math.floor(state.timeOfDay * 24 * 60);
    const time = `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;
    setRange('hack-time', state.timeOfDay, time);
    setRange('hack-cycle', state.cycleScale, `${state.cycleScale.toFixed(1)}x`);
    setRange('hack-cloud', state.cloudCover, `${Math.round(state.cloudCover * 100)}%`);
    setRange('hack-cloud-dark', state.cloudDark, `${Math.round(state.cloudDark * 100)}%`);
    setRange('hack-rain', state.rain, `${Math.round(state.rain * 100)}%`);
    setRange('hack-wind', state.windStrength, `${state.windStrength.toFixed(2)}x`);
    setRange('hack-wind-dir', state.windDirection, `${Math.round(state.windDirection)}°`);
    setRange('hack-fog', state.fogScale, `${state.fogScale.toFixed(2)}x`);
    setRange('hack-light', state.lightScale, `${state.lightScale.toFixed(2)}x`);
    setRange('hack-exposure', state.exposure, state.exposure.toFixed(2));
    setRange('hack-grass-density', state.grassDensity, `${state.grassDensity.toFixed(2)}x`);
    setRange('hack-grass-height', state.grassHeight, `${state.grassHeight.toFixed(2)}x`);
    setRange('hack-grass-width', state.grassWidth, `${state.grassWidth.toFixed(2)}x`);
    setRange('hack-grass-coverage', state.grassCoverage, `${Math.round(state.grassCoverage * 100)}%`);
    setRange('hack-grass-edge-density', state.grassEdgeDensity, `${state.grassEdgeDensity.toFixed(2)}x`);
    setRange('hack-undergrowth-density', state.undergrowthDensity, `${state.undergrowthDensity.toFixed(2)}x`);
    const weather = document.getElementById('hack-weather') as HTMLSelectElement;
    weather.value = state.weather;
    (document.getElementById('hack-auto-weather') as HTMLInputElement).checked = state.autoWeather;
  }
}
