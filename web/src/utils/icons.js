// Lucide icon SVGs as strings
export const lucideIcons = {
  github: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c2.6-.4 5.6-2 5.6-7 0-1.25-.45-2.4-1.2-3.2.15-.6.2-1.2.2-1.85 0-1-.3-2-1-3 -1-3-3-4-3-4s-1 0-2.6.6c-1.6-.2-3.4-.2-5 0C6 2 5 2 5 2s-2 1-3 4c-.7 1-.7 2-.7 3 0 .65.05 1.25.2 1.85-.75.8-1.2 1.95-1.2 3.2 0 5 3 6.6 5.6 7-1 .8-1 2-1.2 3.5V22"/><path d="M9 18c-4.51 2-5-2-7-2"/></svg>',
  globe: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.3 14.3 0 0 1 10 4.3M12 2a14.3 14.3 0 0 0-10 4.2M12 2v20m4.3-4.3a14.3 14.3 0 0 1 4.3-10M7.7 7.7a14.3 14.3 0 0 0 4.3 10M2 12h20M2 12a10 10 0 0 1 20 0"/></svg>',
  bot: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/><path d="M9 17v2M15 17v2"/></svg>',
  radio: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.9 19.1C3.7 17.4 3 15.3 3 13c0-5.5 4.5-10 10-10s10 4.5 10 10c0 2.3-.7 4.4-1.9 6.1"/><path d="M7.05 16.87c.79-1.21 1.97-2.11 3.45-2.37M16.95 16.87c-.79-1.21-1.97-2.11-3.45-2.37"/><circle cx="13" cy="13" r="1" fill="currentColor"/></svg>',
  play: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>',
  pause: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>',
  volume2: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a7 7 0 0 1 0 9.9M19.07 4.93a11 11 0 0 1 0 15.66"/></svg>',
  search: '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>'
};

export function createIconElement(iconName) {
  const svg = document.createElement('span');
  svg.innerHTML = lucideIcons[iconName] || '';
  svg.classList.add('lucide-icon');
  return svg;
}
