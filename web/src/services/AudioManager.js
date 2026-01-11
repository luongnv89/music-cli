class AudioManager {
  constructor() {
    this.audio = new Audio();
    this.audio.crossOrigin = 'anonymous';
    this.isPlaying = false;
    this.currentStation = null;
    this.volume = 0.8;
    this.onStateChange = null;
    this.onError = null;

    this.audio.addEventListener('play', () => this._notifyStateChange('playing'));
    this.audio.addEventListener('pause', () => this._notifyStateChange('paused'));
    this.audio.addEventListener('ended', () => this._notifyStateChange('ended'));
    this.audio.addEventListener('waiting', () => this._notifyStateChange('loading'));
    this.audio.addEventListener('canplay', () => {
      if (this.isPlaying) this._notifyStateChange('playing');
    });
    this.audio.addEventListener('error', (e) => {
      this._notifyStateChange('error');
      if (this.onError) this.onError(e);
    });
  }

  _notifyStateChange(state) {
    if (this.onStateChange) {
      this.onStateChange(state, this.currentStation);
    }
  }

  play(station) {
    if (this.currentStation?.url === station.url && this.isPlaying) {
      return;
    }

    this.currentStation = station;
    this.audio.src = station.url;
    this.audio.volume = this.volume;
    this._notifyStateChange('loading');
    
    return this.audio.play()
      .then(() => {
        this.isPlaying = true;
        return true;
      })
      .catch((error) => {
        console.error('Playback failed:', error);
        this._notifyStateChange('error');
        return false;
      });
  }

  pause() {
    if (this.isPlaying) {
      this.audio.pause();
      this.isPlaying = false;
    }
  }

  resume() {
    if (!this.isPlaying && this.currentStation) {
      return this.audio.play()
        .then(() => {
          this.isPlaying = true;
          return true;
        })
        .catch(() => false);
    }
    return Promise.resolve(false);
  }

  stop() {
    this.audio.pause();
    this.audio.src = '';
    this.isPlaying = false;
    this.currentStation = null;
    this._notifyStateChange('stopped');
  }

  setVolume(value) {
    this.volume = Math.max(0, Math.min(1, value));
    this.audio.volume = this.volume;
  }

  getVolume() {
    return this.volume;
  }

  toggle() {
    if (this.isPlaying) {
      this.pause();
    } else {
      this.resume();
    }
  }

  getState() {
    return {
      isPlaying: this.isPlaying,
      currentStation: this.currentStation,
      volume: this.volume,
    };
  }
}

export const audioManager = new AudioManager();
export default audioManager;
