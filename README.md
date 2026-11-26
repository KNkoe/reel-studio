# Reel Studio

Open-source tools for recording yourself and finishing vertical videos on a Mac, with an AI
coding agent (Claude Code or Codex) as the editor. Record with the companion iPhone and Mac
apps, then ask for the edit in plain language.

The video processing runs on your own Mac and needs no paid video or image API.

## What is inside

| Part | Where | What it does |
|---|---|---|
| Editing skill | [`skills/panel-reel/`](skills/panel-reel/SKILL.md) | The instructions the agent follows, and the scripts it runs |
| Full-frame look | `skills/panel-reel/scripts/room_reel.py` | Replaces your wall with a rendered studio room fitted to the camera's angle, smooths skin, touches up colour |
| Split-screen reels | `skills/panel-reel/scripts/build.py` | Screen plus face: cuts, captions, headlines, camera moves, 3D scenes |
| Camera apps | [`apps/clapless`](https://github.com/KNkoe/clapless) | iPhone camera and Mac screen and mic recorder, matched without a clap |
| Taste and rules | [`docs/PREFERENCES.md`](docs/PREFERENCES.md) | What a good edit means here. Change it to yours |
| Why it is this way | [`docs/HISTORY.md`](docs/HISTORY.md) | What was tried, approved and rejected |

## Quick start

You need an Apple silicon Mac on macOS 26 or later, Xcode and [Homebrew](https://brew.sh).
An iPhone is only needed for the camera apps.

```bash
git clone --recurse-submodules https://github.com/KNkoe/reel-studio ~/reel-studio
cd ~/reel-studio
bash scripts/setup.sh --install   # ffmpeg, uv, node, Blender
bash scripts/setup.sh --link      # adds the skill to Claude Code and Codex
bash scripts/setup.sh --test      # compiles the tools and renders the room once
```

Then, in a new Claude Code or Codex thread:

> Edit my latest Clapless take in my style.

Or run it by hand on any upright 9:16 clip of someone talking:

```bash
python3 -I skills/panel-reel/scripts/room_reel.py <take folder or video> projects/<name> --preview 2,12
python3 -I skills/panel-reel/scripts/room_reel.py <take folder or video> projects/<name>
```

The first command makes preview pictures; the second renders the video. [SETUP.md](SETUP.md)
has the details, including how to build the apps.

## Make it yours

The defaults are one creator's taste, learned from real edits.

- Rewrite [`docs/PREFERENCES.md`](docs/PREFERENCES.md): the agent reads it before every edit.
- Change the room in `skills/panel-reel/scripts/studio_set.py`.
- Change how edits are made in [`skills/panel-reel/SKILL.md`](skills/panel-reel/SKILL.md).

## Status and limits

This is a young project, built and tested on one Mac (M1 Pro, macOS 27.2) with one camera,
desk and speaker. Expect to adjust it for yours.

- The full-frame look needs sharp, well-lit, upright footage and a roughly level camera that
  stays still during a take. It takes about 10 minutes per 30 seconds of video.
- It does not yet cut lines, add captions or bring in the screen recording. The split-screen
  builder does those, with its own layout.
- Editing inside the Clapless app is not built yet.

## Privacy and cost

Rendering, cut-out and transcription happen on your Mac. An AI agent is a separate matter:
whatever it reads, including preview frames and transcript text, goes to its provider under
your plan with them. Run the scripts by hand if that matters for your footage.

The first runs download tools and a cut-out model. Recordings, renders and project folders
are ignored by git and are not part of this repository.

## Contributing

Issues and pull requests are welcome, especially reports from other Macs, iPhones, rooms and
lighting. Run `bash scripts/setup.sh --test` after changing scripts, and never commit footage
of people, private screen content or keys.

## Licence

The code is [MIT](LICENSE): use it, change it and share it. Tools and assets it relies on keep
their own licences and are not covered by this one, among them the
[Robust Video Matting](https://github.com/PeterL1n/RobustVideoMatting) model (GPL-3.0,
downloaded on first use), Blender, ffmpeg, HyperFrames, GSAP and three.js. Check their terms
before shipping them as part of something else.
