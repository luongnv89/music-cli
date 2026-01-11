/**
 * Radio stations data for music-cli web
 * Extracted from the Python CLI's default radio stations
 */

export const stations = [
  // ========== ENGLISH ==========
  // Chill/Lo-fi
  { id: 1, name: 'ChillHop', url: 'https://streams.ilovemusic.de/iloveradio17.mp3', category: 'Chill/Lo-fi', language: 'English', moods: ['focus', 'relaxed', 'peaceful'] },
  { id: 2, name: 'Groove Salad [SomaFM]', url: 'http://ice1.somafm.com/groovesalad-128-mp3', category: 'Chill/Lo-fi', language: 'English', moods: ['relaxed', 'peaceful'] },
  { id: 3, name: 'Drone Zone [SomaFM]', url: 'http://ice1.somafm.com/dronezone-128-mp3', category: 'Chill/Lo-fi', language: 'English', moods: ['peaceful', 'melancholic'] },
  { id: 4, name: 'Space Station Soma', url: 'http://ice1.somafm.com/spacestation-128-mp3', category: 'Chill/Lo-fi', language: 'English', moods: ['focus', 'peaceful'] },
  { id: 5, name: 'Hirschmilch Chillout', url: 'http://hirschmilch.de:7000/chillout.mp3', category: 'Chill/Lo-fi', language: 'English', moods: ['relaxed', 'peaceful'] },

  // Electronic
  { id: 6, name: 'Deep House', url: 'https://streams.ilovemusic.de/iloveradio14.mp3', category: 'Electronic', language: 'English', moods: ['energetic', 'happy'] },
  { id: 7, name: 'DEF CON Radio [SomaFM]', url: 'http://ice1.somafm.com/defcon-128-mp3', category: 'Electronic', language: 'English', moods: ['energetic', 'focus'] },
  { id: 8, name: 'Beat Blender [SomaFM]', url: 'http://ice1.somafm.com/beatblender-128-mp3', category: 'Electronic', language: 'English', moods: ['focus', 'energetic'] },

  // Pop/Hits
  { id: 9, name: 'Top Hits', url: 'https://streams.ilovemusic.de/iloveradio1.mp3', category: 'Pop/Hits', language: 'English', moods: ['happy', 'excited'] },
  { id: 10, name: '80s Hits', url: 'https://streams.ilovemusic.de/iloveradio4.mp3', category: 'Pop/Hits', language: 'English', moods: ['happy', 'energetic'] },

  // Rock
  { id: 11, name: 'Rock Radio', url: 'https://streams.ilovemusic.de/iloveradio3.mp3', category: 'Rock', language: 'English', moods: ['energetic', 'excited'] },
  { id: 12, name: 'Metal [SomaFM]', url: 'http://ice1.somafm.com/metal-128-mp3', category: 'Rock', language: 'English', moods: ['energetic', 'excited'] },

  // Synthwave/Retrowave
  { id: 13, name: 'Nightride FM', url: 'https://stream.nightride.fm/nightride.mp3', category: 'Synthwave', language: 'English', moods: ['focus', 'energetic'] },
  { id: 14, name: 'Chillsynth FM', url: 'https://stream.nightride.fm/chillsynth.mp3', category: 'Synthwave', language: 'English', moods: ['relaxed', 'focus'] },
  { id: 15, name: 'Darksynth FM', url: 'https://stream.nightride.fm/darksynth.mp3', category: 'Synthwave', language: 'English', moods: ['energetic', 'focus'] },
  { id: 16, name: 'Datawave FM', url: 'https://stream.nightride.fm/datawave.mp3', category: 'Synthwave', language: 'English', moods: ['focus', 'peaceful'] },
  { id: 17, name: 'Spacesynth FM', url: 'https://stream.nightride.fm/spacesynth.mp3', category: 'Synthwave', language: 'English', moods: ['focus', 'peaceful'] },

  // Jazz
  { id: 18, name: 'Jazz [SomaFM]', url: 'http://ice1.somafm.com/secretagent-128-mp3', category: 'Jazz', language: 'English', moods: ['relaxed', 'focus'] },

  // Classical
  { id: 19, name: 'Classical', url: 'http://stream.srg-ssr.ch/m/rsc_de/mp3_128', category: 'Classical', language: 'English', moods: ['peaceful', 'focus'] },
  { id: 20, name: 'BBC Radio 3', url: 'http://stream.live.vc.bbcmedia.co.uk/bbc_radio_three', category: 'Classical', language: 'English', moods: ['peaceful', 'relaxed'] },

  // ========== FRENCH ==========
  { id: 21, name: 'FIP Radio', url: 'http://icecast.radiofrance.fr/fip-midfi.mp3', category: 'French', language: 'French', moods: ['relaxed', 'happy'] },
  { id: 22, name: 'France Inter', url: 'http://icecast.radiofrance.fr/franceinter-midfi.mp3', category: 'French', language: 'French', moods: ['focus'] },
  { id: 23, name: 'France Musique', url: 'http://icecast.radiofrance.fr/francemusique-midfi.mp3', category: 'French', language: 'French', moods: ['peaceful', 'relaxed'] },
  { id: 24, name: 'FIP Rock', url: 'http://icecast.radiofrance.fr/fiprock-midfi.mp3', category: 'French', language: 'French', moods: ['energetic'] },
  { id: 25, name: 'FIP Jazz', url: 'http://icecast.radiofrance.fr/fipjazz-midfi.mp3', category: 'French', language: 'French', moods: ['relaxed', 'focus'] },
  { id: 26, name: 'FIP Electro', url: 'http://icecast.radiofrance.fr/fipelectro-midfi.mp3', category: 'French', language: 'French', moods: ['energetic', 'focus'] },
  { id: 27, name: 'Mouv', url: 'http://icecast.radiofrance.fr/mouv-midfi.mp3', category: 'French', language: 'French', moods: ['energetic', 'happy'] },

  // ========== SPANISH ==========
  { id: 28, name: 'Salsa Radio', url: 'http://157.230.221.44:2002/stream/1/', category: 'Spanish', language: 'Spanish', moods: ['happy', 'energetic'] },
  { id: 29, name: 'Tropical 100 Salsa', url: 'http://tropical100.net:8008/stream/1/', category: 'Spanish', language: 'Spanish', moods: ['happy', 'excited'] },
  { id: 30, name: 'SalsaMexico', url: 'http://colombiawebs.com.co:8106/stream/1/', category: 'Spanish', language: 'Spanish', moods: ['happy', 'energetic'] },
  { id: 31, name: 'Los 40 Principales', url: 'https://playerservices.streamtheworld.com/api/livestream-redirect/LOS40.mp3', category: 'Spanish', language: 'Spanish', moods: ['happy', 'excited'] },
  { id: 32, name: 'Radio Maria Spain', url: 'http://dreamsiteradiocp.com:8060/stream/1/', category: 'Spanish', language: 'Spanish', moods: ['peaceful'] },
  { id: 33, name: 'Cadena SER', url: 'https://playerservices.streamtheworld.com/api/livestream-redirect/CADENASER.mp3', category: 'Spanish', language: 'Spanish', moods: ['focus'] },

  // ========== ITALIAN ==========
  { id: 34, name: 'Radio Italia', url: 'http://radioitalia.net/stream/1/', category: 'Italian', language: 'Italian', moods: ['happy'] },
  { id: 35, name: 'RTL 102.5', url: 'http://streamingp.shoutcast.com/RTL1025?lang=*', category: 'Italian', language: 'Italian', moods: ['happy', 'energetic'] },
  { id: 36, name: 'Radio 105', url: 'https://icecast.unitedradio.it/Radio105.mp3', category: 'Italian', language: 'Italian', moods: ['energetic', 'happy'] },
  { id: 37, name: 'Virgin Radio Italy', url: 'https://icecast.unitedradio.it/Virgin.mp3', category: 'Italian', language: 'Italian', moods: ['energetic'] },
  { id: 38, name: 'Radio Deejay', url: 'https://icecast.unitedradio.it/RadioDeejay.mp3', category: 'Italian', language: 'Italian', moods: ['happy', 'energetic'] },
  { id: 39, name: 'RDS Radio', url: 'http://stream.rds.it:8000/rds64k.mp3', category: 'Italian', language: 'Italian', moods: ['relaxed'] },
  { id: 40, name: 'Radio Capital', url: 'https://icecast.unitedradio.it/Capital.mp3', category: 'Italian', language: 'Italian', moods: ['relaxed', 'focus'] },
];

export const categories = [...new Set(stations.map(s => s.category))];
export const languages = [...new Set(stations.map(s => s.language))];
export const moods = ['focus', 'happy', 'sad', 'excited', 'relaxed', 'energetic', 'melancholic', 'peaceful'];

export const moodDescriptions = {
  focus: 'Concentrate on your work',
  happy: 'Upbeat and cheerful vibes',
  sad: 'Melancholic and emotional',
  excited: 'High energy and pumped',
  relaxed: 'Calm and laid back',
  energetic: 'Active and dynamic',
  melancholic: 'Thoughtful and introspective',
  peaceful: 'Serene and tranquil',
};

export const moodIcons = {
  focus: '🎯',
  happy: '😊',
  sad: '😢',
  excited: '🎉',
  relaxed: '😌',
  energetic: '⚡',
  melancholic: '🌙',
  peaceful: '🕊️',
};

/**
 * Get stations by category
 */
export function getStationsByCategory(category) {
  return stations.filter(s => s.category === category);
}

/**
 * Get stations by mood
 */
export function getStationsByMood(mood) {
  return stations.filter(s => s.moods.includes(mood));
}

/**
 * Get a random station for a mood
 */
export function getRandomStationForMood(mood) {
  const moodStations = getStationsByMood(mood);
  if (moodStations.length === 0) return stations[0];
  return moodStations[Math.floor(Math.random() * moodStations.length)];
}

/**
 * Search stations by name
 */
export function searchStations(query) {
  const q = query.toLowerCase();
  return stations.filter(s => 
    s.name.toLowerCase().includes(q) || 
    s.category.toLowerCase().includes(q)
  );
}
