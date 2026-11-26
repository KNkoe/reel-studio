# Reel Studio

Record with my own camera apps, finish vertical videos on the Mac with an AI agent. Footage
never leaves the machine and nothing here needs a paid API.

| Part | Where | What it does |
|---|---|---|
| Editing style | [`skills/panel-reel/`](skills/panel-reel/SKILL.md) | The skill Claude Code or Codex follows, and its scripts |
| Full-frame look | `skills/panel-reel/scripts/room_reel.py` | Fits the studio room to the camera's angle, cuts me out, smooths skin |
| Split-screen reels | `skills/panel-reel/scripts/build.py` | Screen plus face: cuts, captions, headlines, camera moves, 3D scenes |
| Taste and rules | [`docs/PREFERENCES.md`](docs/PREFERENCES.md) | What I want from an edit |
| Why it is this way | [`docs/HISTORY.md`](docs/HISTORY.md) | What was tried, approved and rejected |
| Camera apps | `apps/clapless` | iPhone camera and Mac recorder (its own repository, linked here) |

## Start

On a new Mac, follow [SETUP.md](SETUP.md). Then, in any Claude Code or Codex thread:

> Edit my latest Clapless take in my style.

Or by hand:

```bash
python3 -I skills/panel-reel/scripts/room_reel.py ~/Movies/Clapless/<take> projects/<name> --preview 2,12
python3 -I skills/panel-reel/scripts/room_reel.py ~/Movies/Clapless/<take> projects/<name>
```

## What is not in here

Recordings, renders, project folders, the downloaded cut-out model, signing settings and
keys. Back those up separately: cloning this repository does not bring back old videos.

## Not built yet

- Cutting, captions and the screen recording together with the full-frame look.
- Editing inside the Clapless app (check `apps/clapless` for its current state).
