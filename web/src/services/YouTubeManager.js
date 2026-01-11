let player = null;
let isReady = false;
let pendingPlay = null;
let onStateChange = null;
let currentVideoId = null;

function loadYouTubeAPI() {
  return new Promise((resolve) => {
    if (window.YT && window.YT.Player) {
      resolve();
      return;
    }

    const tag = document.createElement('script');
    tag.src = 'https://www.youtube.com/iframe_api';
    const firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

    window.onYouTubeIframeAPIReady = () => {
      resolve();
    };
  });
}

function extractVideoId(url) {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\s?]+)/,
    /^([a-zA-Z0-9_-]{11})$/,
  ];

  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match) return match[1];
  }
  return null;
}

function initPlayer(containerId) {
  return loadYouTubeAPI().then(() => {
    return new Promise((resolve) => {
      player = new window.YT.Player(containerId, {
        height: '100%',
        width: '100%',
        playerVars: {
          autoplay: 0,
          controls: 1,
          modestbranding: 1,
          rel: 0,
          fs: 0,
          playsinline: 1,
        },
        events: {
          onReady: () => {
            isReady = true;
            if (pendingPlay) {
              playVideo(pendingPlay);
              pendingPlay = null;
            }
            resolve(player);
          },
          onStateChange: (event) => {
            const states = {
              [-1]: 'unstarted',
              [0]: 'ended',
              [1]: 'playing',
              [2]: 'paused',
              [3]: 'buffering',
              [5]: 'cued',
            };
            const state = states[event.data] || 'unknown';
            if (onStateChange) {
              onStateChange(state, currentVideoId);
            }
          },
          onError: (event) => {
            console.error('YouTube player error:', event.data);
            if (onStateChange) {
              onStateChange('error', currentVideoId);
            }
          },
        },
      });
    });
  });
}

function playVideo(urlOrId) {
  const videoId = extractVideoId(urlOrId) || urlOrId;
  
  if (!isReady) {
    pendingPlay = videoId;
    return false;
  }

  if (player && player.loadVideoById) {
    currentVideoId = videoId;
    player.loadVideoById(videoId);
    return true;
  }
  return false;
}

function pause() {
  if (player && player.pauseVideo) {
    player.pauseVideo();
  }
}

function resume() {
  if (player && player.playVideo) {
    player.playVideo();
  }
}

function stop() {
  if (player && player.stopVideo) {
    player.stopVideo();
    currentVideoId = null;
  }
}

function setVolume(value) {
  if (player && player.setVolume) {
    player.setVolume(Math.round(value * 100));
  }
}

function getVolume() {
  if (player && player.getVolume) {
    return player.getVolume() / 100;
  }
  return 0.8;
}

function setOnStateChange(callback) {
  onStateChange = callback;
}

function isValidYouTubeUrl(url) {
  return extractVideoId(url) !== null;
}

function getVideoThumbnail(videoId) {
  return `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
}

export const youtubeManager = {
  initPlayer,
  playVideo,
  pause,
  resume,
  stop,
  setVolume,
  getVolume,
  setOnStateChange,
  isValidYouTubeUrl,
  extractVideoId,
  getVideoThumbnail,
  isReady: () => isReady,
  getCurrentVideoId: () => currentVideoId,
};

export default youtubeManager;
