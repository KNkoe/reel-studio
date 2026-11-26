# Set up a new Mac

## What you need

- A Mac with Apple silicon on macOS 26 or later (built on an M1 Pro, macOS 27.2).
- Xcode (from the App Store), [Homebrew](https://brew.sh), and an iPhone for recording.
- Claude Code or Codex, signed in with your own plan.
- About 5 GB for tools, plus room for footage (4K takes about 340 MB a minute).

Versions this was last run with: Xcode 27.2, ffmpeg 8.1.2, uv 0.12.16, Node 26.7.0,
Blender 5.2.1, Python 3.13 (through uv), numpy 2.5.5, onnxruntime 1.32.0. The scripts pin
the Python packages; Homebrew installs the newest of the rest, so test after installing.

## 1. Get the code

```bash
git clone --recurse-submodules <this repository's address> ~/reel-studio
cd ~/reel-studio
```

Both repositories are private: sign in to GitHub first (`gh auth login`).
Keep the folder where you cloned it, or run `--link` again after moving it.

## 2. Editing tools

```bash
bash scripts/setup.sh --install   # ffmpeg, uv, node, Blender
bash scripts/setup.sh --link      # makes the skill visible to Claude Code and Codex
bash scripts/setup.sh             # everything should say ok
bash scripts/setup.sh --test      # compiles the tools and renders the room once
```

Downloaded on first use, then kept:
- the cut-out model, Robust Video Matting (107 MB, GPL-3.0, from its GitHub release, checked
  against a fixed checksum) into `~/.cache/panel-reel/models/`;
- numpy and onnxruntime through uv;
- for split-screen reels, HyperFrames through `npx`; its page also loads GSAP and three.js
  from public CDNs, so rendering one needs a connection;
- Apple's speech assets for on-device transcription, if macOS asks.

Fonts are the system's (SF Pro) or come from the product being shown; none are stored here.

## 3. Clapless (iPhone camera and Mac recorder)

Its own instructions are in `apps/clapless/README.md`. In short:

```bash
cd apps/clapless
scripts/setup.sh    # writes your signing team into Config/Local.xcconfig (never committed)
scripts/mac.sh      # builds the Mac app into ~/Applications and opens it
scripts/phone.sh    # builds the iPhone app and installs it
swift test
```

On the iPhone: turn on Developer Mode, trust the Mac, trust your developer certificate, and
allow camera, microphone and local network. On the Mac: allow Screen Recording and the
microphone. With a free Apple developer account the iPhone app expires after 7 days: run
`scripts/phone.sh` again. Pair once; both screens show the same six digits.

## 4. Check it works

Record a 10-second take, then:

```bash
python3 -I skills/panel-reel/scripts/room_reel.py ~/Movies/Clapless/<take> projects/first --preview 2,6
```

Open `projects/first/angle-check.png` (white lines should sit on real upright edges and the
table edge) and the pictures in `projects/first/preview/`.

## What will differ on another set-up

The room is measured from each recording, so a new desk or camera angle is handled, within
limits: the camera must be roughly level and still during a take, and the recording upright
9:16. The room itself is designed around a speaker about an arm's length away. Results on a
different Mac, iPhone, room or light have not been tested.

## Moving your preferences and old work

`docs/PREFERENCES.md` travels with the repository. Recordings, renders and project folders do
not: copy `~/Movies/Clapless` and `projects/` yourself if you want them.
