# P7.1 — 2-Minute Judging Video Recording Plan

## Storyboard

| Time | Section | Content |
|------|---------|---------|
| 0:00–0:10 | Premiere | Show `dist/neon-rain/premiere.mp4` playing |
| 0:10–0:25 | Install | `pipx install music-cli[minimax,gmi]` + `mc studio doctor` |
| 0:25–0:45 | Constitution | Show `CHALLENGE.md` and the constitution/manifest |
| 0:45–1:10 | Play | Run `mc studio build examples/neon-rain.yaml` |
| 1:10–1:35 | Revise | Run `mc studio revise "make it more upbeat"` showing plan-diff |
| 1:35–1:50 | Diff/Rebuild | Show `git diff pre-minimax-week...main` and re-build |
| 1:50–2:00 | Repo/Install | Show GitHub compare link and pipx install line in README |

## Prerequisites

- Terminal with `zsh` or `bash`
- Screen recording tool (OBS, QuickTime, or similar)
- Clean terminal theme (dark mode recommended)
- Font size large enough to read commands

## Recording Steps

1. **Clean terminal**: `clear`
2. **Section 1 (Premiere)**: `open dist/neon-rain/premiere.mp4` — show video playing
3. **Section 2 (Install)**: Type and run:
   ```bash
   pipx install music-cli[minimax,gmi]
   mc studio doctor
   ```
4. **Section 3 (Constitution)**:
   ```bash
   cat CHALLENGE.md
   cat music_cli/studio/schemas.py | head -30
   ```
5. **Section 4 (Play)**:
   ```bash
   mc studio build examples/neon-rain.yaml
   ```
   (Use cached build — skip actual model calls if keys unavailable)
6. **Section 5 (Revise)**:
   ```bash
   mc studio revise "make it more upbeat"
   ```
7. **Section 6 (Diff)**:
   ```bash
   git diff pre-minimax-week...main --stat
   ```
8. **Section 7 (Repo)**:
   ```bash
   cat README.md | head -20
   open https://github.com/luongnv89/music-cli/compare/pre-minimax-week...main
   ```

## Post-Recording

- Trim to 1:55–2:05
- Add captions if needed
- Upload to YouTube/X/Loom (public)
- Update submission form with video URL

## Notes

- Use cached builds to avoid rate limits during recording
- If model calls fail, show the error gracefully and note "using cached output"
- Keep cursor visible and commands readable
- Record at 1080p or higher
