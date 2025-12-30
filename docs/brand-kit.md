# music-cli Brand Kit

## Logo

The music-cli logo combines a **terminal cursor** (representing CLI/developer tools) with **sound wave bars** (representing music/audio). This visual metaphor captures the essence of the product: music for the command line.

### Logo Variants

| File | Usage |
|------|-------|
| `logo-full.svg` | Primary logo with mark + wordmark |
| `logo-mark.svg` | Icon only (social media, badges) |
| `logo-wordmark.svg` | Text only (documentation headers) |
| `logo-icon.svg` | Square app icon (512x512) |
| `favicon.svg` | Simplified favicon (32x32) |
| `logo-white.svg` | White version for dark backgrounds |
| `logo-black.svg` | Monochrome version |

### Logo Files Location

```
assets/logo/
├── logo-full.svg
├── logo-mark.svg
├── logo-wordmark.svg
├── logo-icon.svg
├── favicon.svg
├── logo-white.svg
└── logo-black.svg
```

## Colors

### Primary Palette

| Color | Hex | Usage |
|-------|-----|-------|
| **Indigo** | `#6366F1` | Primary brand color, logo, accents |
| **Indigo Light** | `#A5B4FC` | Secondary accent, hover states |
| **Zinc 900** | `#18181B` | Text, dark mode background |
| **White** | `#FFFFFF` | Backgrounds, reversed text |

### Tailwind CSS Config

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      colors: {
        'music-cli': {
          DEFAULT: '#6366F1',
          light: '#A5B4FC',
          dark: '#4F46E5',
        }
      }
    }
  }
}
```

### CSS Custom Properties

```css
:root {
  --color-primary: #6366F1;
  --color-primary-light: #A5B4FC;
  --color-primary-dark: #4F46E5;
  --color-text: #18181B;
  --color-background: #FFFFFF;
}
```

## Typography

### Primary Font

**Inter** - A modern, highly legible sans-serif typeface designed for screens.

```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
```

### Font Weights

| Weight | Usage |
|--------|-------|
| Regular (400) | Body text |
| Medium (500) | Subheadings |
| Semibold (600) | Logo wordmark, headings |
| Bold (700) | Emphasis |

### Monospace (for code/CLI)

```css
font-family: 'JetBrains Mono', 'Fira Code', 'SF Mono', Monaco, monospace;
```

## Design Rationale

### Why Indigo?

- **Focus & Calm**: Indigo evokes focus and concentration, perfect for a productivity tool
- **Tech-Forward**: Modern tech brands (Linear, Vercel, Discord) use similar cool tones
- **Accessibility**: High contrast with both white and dark backgrounds
- **Differentiation**: Stands out from typical music app colors (green/Spotify, red/YouTube)

### Why This Symbol?

- **Terminal Cursor**: The vertical bar on the left represents the CLI cursor, establishing the developer tool identity
- **Sound Waves**: The equalizer bars represent music/audio visualization
- **Combined Meaning**: "Music from your terminal" - the core value proposition in one symbol
- **Scalability**: Simple geometric shapes work at any size (favicon to billboard)

### Typography Choice

- **Inter**: Clean, modern, excellent for UI and documentation
- **Semibold for logo**: Confident but not aggressive
- **Two-tone wordmark**: "music" in dark + "-cli" in brand color emphasizes the CLI aspect

## Usage Guidelines

### Do

- Use the logo with adequate whitespace (minimum: logo height on all sides)
- Use the white version on dark backgrounds
- Use the black version for monochrome printing
- Keep the logo proportions intact

### Don't

- Don't stretch or distort the logo
- Don't change the logo colors outside the approved palette
- Don't add effects (shadows, gradients, outlines)
- Don't place the logo on busy backgrounds
- Don't recreate the logo with different fonts

## Brand Personality

| Trait | Description |
|-------|-------------|
| **Technical** | Built for developers, CLI-first |
| **Focused** | Helps you concentrate and code |
| **Minimal** | Clean, no distractions |
| **Reliable** | Background daemon, just works |
| **Modern** | AI-powered, context-aware |

## Voice & Tone

- **Concise**: Short, clear commands and messages
- **Helpful**: Provide tips and suggestions
- **Technical but approachable**: Developer-friendly without being intimidating
- **Occasionally playful**: Inspirational quotes, friendly status messages
