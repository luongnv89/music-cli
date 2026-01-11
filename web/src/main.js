import './style.css';
import { stations, categories, moods, moodIcons, searchStations, getStationsByCategory, getStationsByMood } from './data/stations.js';
import audioManager from './services/AudioManager.js';
import youtubeManager from './services/YouTubeManager.js';

let currentMode = 'radio';
let activeCategory = null;
let activeMood = null;
let currentStation = null;

function init() {
  renderCategoryFilters();
  renderMoodFilters();
  renderStations(stations);
  setupEventListeners();
  setupAudioManager();
  setupYouTubePlayer();
}

function renderCategoryFilters() {
  const container = document.getElementById('category-filters');
  
  const allPill = document.createElement('button');
  allPill.className = 'filter-pill active';
  allPill.textContent = 'All';
  allPill.dataset.category = 'all';
  container.appendChild(allPill);
  
  categories.forEach(category => {
    const pill = document.createElement('button');
    pill.className = 'filter-pill';
    pill.textContent = category;
    pill.dataset.category = category;
    container.appendChild(pill);
  });
}

function renderMoodFilters() {
  const container = document.getElementById('mood-filters');
  
  moods.forEach(mood => {
    const pill = document.createElement('button');
    pill.className = 'filter-pill';
    pill.innerHTML = `<span class="pill-icon">${moodIcons[mood]}</span>${mood}`;
    pill.dataset.mood = mood;
    container.appendChild(pill);
  });
}

function renderStations(stationsToRender) {
  const grid = document.getElementById('stations-grid');
  grid.innerHTML = '';
  
  if (stationsToRender.length === 0) {
    grid.innerHTML = '<p style="color: var(--color-text-muted); text-align: center; grid-column: 1/-1;">No stations found</p>';
    return;
  }
  
  stationsToRender.forEach(station => {
    const card = document.createElement('div');
    card.className = 'station-card';
    if (currentStation?.id === station.id) {
      card.classList.add('playing');
    }
    card.dataset.stationId = station.id;
    
    card.innerHTML = `
      <div class="station-name">${station.name}</div>
      <div class="station-category">${station.category}</div>
    `;
    
    card.addEventListener('click', () => playStation(station));
    grid.appendChild(card);
  });
}

function playStation(station) {
  currentStation = station;
  
  document.querySelectorAll('.station-card').forEach(card => {
    card.classList.remove('playing');
    if (parseInt(card.dataset.stationId) === station.id) {
      card.classList.add('playing');
    }
  });
  
  updateNowPlaying(station.name, station.category);
  audioManager.play(station);
}

function updateNowPlaying(name, category = '') {
  document.getElementById('track-name').textContent = name;
  document.getElementById('track-category').textContent = category;
}

function setupEventListeners() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchMode(btn.dataset.mode));
  });
  
  document.getElementById('category-filters').addEventListener('click', (e) => {
    if (e.target.classList.contains('filter-pill')) {
      handleCategoryFilter(e.target);
    }
  });
  
  document.getElementById('mood-filters').addEventListener('click', (e) => {
    const pill = e.target.closest('.filter-pill');
    if (pill) {
      handleMoodFilter(pill);
    }
  });
  
  document.getElementById('search-input').addEventListener('input', (e) => {
    const query = e.target.value.trim();
    filterStations(query);
  });
  
  document.getElementById('play-pause-btn').addEventListener('click', togglePlayback);
  
  const volumeSlider = document.getElementById('volume-slider');
  volumeSlider.addEventListener('input', (e) => {
    const value = e.target.value;
    setVolume(value / 100);
    document.getElementById('volume-value').textContent = `${value}%`;
  });
  
  document.getElementById('youtube-play-btn').addEventListener('click', playYouTubeVideo);
  document.getElementById('youtube-url').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') playYouTubeVideo();
  });
}

function switchMode(mode) {
  currentMode = mode;
  
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
  
  document.querySelectorAll('.mode-section').forEach(section => {
    section.classList.toggle('active', section.id === `${mode}-mode`);
  });
  
  if (mode === 'youtube') {
    audioManager.stop();
  } else {
    youtubeManager.stop();
  }
}

function handleCategoryFilter(pill) {
  document.querySelectorAll('#category-filters .filter-pill').forEach(p => p.classList.remove('active'));
  pill.classList.add('active');
  
  const category = pill.dataset.category;
  activeCategory = category === 'all' ? null : category;
  activeMood = null;
  document.querySelectorAll('#mood-filters .filter-pill').forEach(p => p.classList.remove('active'));
  
  applyFilters();
}

function handleMoodFilter(pill) {
  const isActive = pill.classList.contains('active');
  
  document.querySelectorAll('#mood-filters .filter-pill').forEach(p => p.classList.remove('active'));
  
  if (!isActive) {
    pill.classList.add('active');
    activeMood = pill.dataset.mood;
  } else {
    activeMood = null;
  }
  
  activeCategory = null;
  document.querySelectorAll('#category-filters .filter-pill').forEach(p => {
    p.classList.toggle('active', p.dataset.category === 'all');
  });
  
  applyFilters();
}

function filterStations(query) {
  if (query) {
    renderStations(searchStations(query));
  } else {
    applyFilters();
  }
}

function applyFilters() {
  let filtered = stations;
  
  if (activeCategory) {
    filtered = getStationsByCategory(activeCategory);
  } else if (activeMood) {
    filtered = getStationsByMood(activeMood);
  }
  
  renderStations(filtered);
}

function setupAudioManager() {
  audioManager.onStateChange = (state, station) => {
    const playPauseBtn = document.getElementById('play-pause-btn');
    const visualizer = document.getElementById('visualizer');
    
    playPauseBtn.disabled = !station;
    
    if (state === 'playing') {
      playPauseBtn.classList.add('playing');
      visualizer.classList.add('playing');
    } else {
      playPauseBtn.classList.remove('playing');
      visualizer.classList.remove('playing');
    }
    
    if (state === 'error') {
      updateNowPlaying('Error loading stream', 'Try another station');
    }
  };
  
  audioManager.onError = () => {
    console.error('Audio playback error');
  };
}

function setupYouTubePlayer() {
  youtubeManager.initPlayer('youtube-player');
  
  youtubeManager.setOnStateChange((state, videoId) => {
    const playPauseBtn = document.getElementById('play-pause-btn');
    const visualizer = document.getElementById('visualizer');
    
    if (currentMode === 'youtube') {
      playPauseBtn.disabled = !videoId;
      
      if (state === 'playing') {
        playPauseBtn.classList.add('playing');
        visualizer.classList.add('playing');
      } else {
        playPauseBtn.classList.remove('playing');
        visualizer.classList.remove('playing');
      }
    }
  });
}

function playYouTubeVideo() {
  const input = document.getElementById('youtube-url');
  const url = input.value.trim();
  
  if (!url) return;
  
  if (!youtubeManager.isValidYouTubeUrl(url)) {
    input.classList.add('error-state');
    setTimeout(() => input.classList.remove('error-state'), 2000);
    return;
  }
  
  const videoId = youtubeManager.extractVideoId(url);
  document.getElementById('youtube-placeholder').classList.add('hidden');
  
  youtubeManager.playVideo(videoId);
  updateNowPlaying('YouTube Video', 'Playing from YouTube');
  currentStation = null;
  
  document.querySelectorAll('.station-card').forEach(card => card.classList.remove('playing'));
}

function togglePlayback() {
  if (currentMode === 'radio') {
    if (audioManager.isPlaying) {
      audioManager.pause();
    } else {
      audioManager.resume();
    }
  } else {
    if (document.getElementById('play-pause-btn').classList.contains('playing')) {
      youtubeManager.pause();
    } else {
      youtubeManager.resume();
    }
  }
}

function setVolume(value) {
  if (currentMode === 'radio') {
    audioManager.setVolume(value);
  } else {
    youtubeManager.setVolume(value);
  }
}

document.addEventListener('DOMContentLoaded', init);
