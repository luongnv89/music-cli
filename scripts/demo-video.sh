#!/usr/bin/env bash
# P7.1 Video Recording Demo Script
# Run each section in order for the video recording.
# Usage: ./scripts/demo-video.sh

set -euo pipefail
cd "$(dirname "$0")/.."

echo "═══════════════════════════════════════════════════════════"
echo "  MiniMax Week × GMI Cloud — Demo Script for Video Recording"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Section 1: Premiere
echo "▶ Section 1: Premiere (0:00–0:10)"
echo "   Show the premiere video:"
echo "   $ open dist/neon-rain/premiere.mp4"
ls -la dist/neon-rain/premiere.mp4 2>/dev/null || echo "   ⚠ premiere.mp4 not found — run 'mc studio build' first"
echo ""

# Section 2: Install
echo "▶ Section 2: Install (0:10–0:25)"
echo "   Commands to type:"
echo "   $ pipx install music-cli[minimax,gmi]"
echo "   $ mc studio doctor"
echo ""

# Section 3: Constitution
echo "▶ Section 3: Constitution (0:25–0:45)"
echo "   Commands to type:"
echo "   $ cat CHALLENGE.md"
echo "   $ head -30 music_cli/studio/schemas.py"
echo ""

# Section 4: Play
echo "▶ Section 4: Play (0:45–1:10)"
echo "   Commands to type:"
echo "   $ mc studio build examples/neon-rain.yaml"
echo ""

# Section 5: Revise
echo "▶ Section 5: Revise (1:10–1:35)"
echo "   Commands to type:"
echo "   $ mc studio revise \"make it more upbeat\""
echo ""

# Section 6: Diff
echo "▶ Section 6: Diff/Rebuild (1:35–1:50)"
echo "   Commands to type:"
echo "   $ git diff pre-minimax-week...main --stat"
echo ""

# Section 7: Repo
echo "▶ Section 7: Repo/Install (1:50–2:00)"
echo "   Commands to type:"
echo "   $ head -20 README.md"
echo "   $ open https://github.com/luongnv89/music-cli/compare/pre-minimax-week...main"
echo ""

echo "═══════════════════════════════════════════════════════════"
echo "  Recording tips:"
echo "  • Use dark terminal theme"
echo "  • Font size ≥ 14pt"
echo "  • Record at 1080p+"
echo "  • Trim to 1:55–2:05"
echo "═══════════════════════════════════════════════════════════"
