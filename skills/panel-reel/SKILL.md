---
name: panel-reel
description: >-
  Reel Studio's video tools: full-frame shots of the speaker in a rendered corner room fitted
  to each recording's camera angle, smooth skin and a light colour touch; cutting; blurring
  private text; Clapless recording; and a split-screen reel build (3D screen stage, head cut
  out above a face card, big short-lived headlines). If a `reel` skill is installed, that is
  the creator's own workflow: for their videos use `reel`, which calls these tools. Use this
  one to change or remove a background, to set up, start or stop recording their iPhone camera
  and Mac screen, for the split-screen build when asked for by name, or, where there is no
  `reel` skill, to edit a Clapless take, a ScreenKite recording (.skbundle), a screen
  recording with a talking head, a product demo or an app walkthrough. Not for copying the
  style of a new reference video.
---

# panel-reel: the creator's saved style

"They" below is the person whose taste this records, and the quotes are theirs. If someone
else is using this repository, treat those choices as starting points: ask, and put their
answers in `docs/PREFERENCES.md`.

Two ways to finish a video here, both on this Mac and free:

| What they recorded | What to run |
|---|---|
| Upright camera of them talking (a Clapless take or any 9:16 clip) | **Full frame**: `scripts/room_reel.py` |
| Screen recording plus face camera | **Split screen**: `plan.json` and `scripts/build.py` |

## The creator's own videos

Their whole workflow, screen recordings included, is a private skill called `reel`. When it
is installed and the video is theirs, read it and follow it; it uses the tools described here
(room, cutter, blur, Clapless). The split-screen build and its 3D screen stage are no longer
their choice (2026-11-27): use them when asked for by name, or for someone without a `reel`
skill. Their style stays private: do not add anything about it to this repository, and where
the skill is missing, ask what graphics should look like instead of making a style up.

## The three views

| View | When |
|---|---|
| **Split**: visuals or the interface above, speaker below | **Most of the video** |
| **Full face** | Now and then, when they are not explaining something with visuals |
| **Visuals only**: no speaker | Only when a point is really being stressed. Rarely |

Mark every part of the script as one of the three before building, and check the balance.

**What the split-screen build can do today:** the split view. Its full-face `solo` shots are
older code that was rejected (see below), its only visuals-only shots are the built-in 3D
card scenes, and a full-screen shot of the interface without the speaker is not built. When a
screen reel needs one of the other two views, say so and offer to build it.

## Find the repo first

A new thread usually starts somewhere else, and this folder is usually reached through a
symlink. Resolve it before anything:

```bash
SKILL="$(cd -P "<this skill's base directory>" && pwd)"
REPO="$(cd "$SKILL/../.." && pwd)"
PROJECTS="${REEL_PROJECTS:-$REPO/projects}"      # gitignored: footage-derived files stay here
```

Read `$REPO/docs/PREFERENCES.md` (their taste and hard rules) before any edit. Put each
project in `$PROJECTS/<slug>/` unless they name another folder. After a session that changes
the style, update this skill or the preferences, and add a dated entry to
`$REPO/docs/HISTORY.md`.

Requirements and first-time setup: `$REPO/SETUP.md`; check with `bash "$REPO/scripts/setup.sh"`.
No API keys or paid calls. The first cut-out downloads the Robust Video Matting model once
(107 MB from its GitHub release, GPL-3.0, cached in `~/.cache/panel-reel/models/`, never
committed or shipped here). Say so before the first run. Footage stays on the Mac.

## Full frame: the speaker in the fitted room

Approved on 2026-11-26 ("I love it, now we can have full frames our videos like we
intended"). Their light is kept; the wall is replaced; skin is smoothed; colour gets a light
touch.

```bash
python3 -I "$SKILL/scripts/room_reel.py" <take folder or video> "$PROJECTS/<slug>" --preview 2,12,24
python3 -I "$SKILL/scripts/room_reel.py" <take folder or video> "$PROJECTS/<slug>"
```

1. **Preview first** (about 2 minutes). Read `preview/*.png` beside the footage and
   `angle-check.png`: its white lines must lie on real upright edges and on the real table
   edge. If the room sits wrong, say what was measured and adjust `--window right|left` or
   edit `fit_room.py`; do not hand-place a room that ignores the recording.
2. **Render** in the background. The speaker is cut out and the room rendered at the same time,
   a few seconds apart (`--one-at-a-time` turns that off and needs a little less memory). On an
   M1 Pro a 30 s clip took about 4 minutes for those two steps and the checks, after about 2 minutes
   of setting up the room. A cut made by `cut.py` is used as it is, without converting it again.
   Every recording is measured afresh: roll from upright edges, table slope, eye height and
   the side the light comes from. What cannot be seen falls back to the approved room, and
   the report says so: pass that on.
3. **Check** the flicker scan it prints and look at every frame it names, then sample frames
   across the video, enlarged: ears, head edge, hands, shoulders, bottom edge. Say that the
   scan and samples are not the same as watching it. Fast hand movement can be flagged
   without any fault.

It outputs `room-vN.mp4` (1080×1920, 30 fps, the recording's own sound) and never overwrites.
`--trim 0.035` sets the strip cut from the bottom (default: sized to the real table edge, at
least 3.5%). `--look '{"skin": 0.7}'` changes retouch or colour. `--room style.json` recolours the room and lights
the speaker to match it, and can bring your own room script and moving background (format at the
top of the script); without it the room is as approved. The camera may move between
recordings but must stay still within one. It assumes a roughly level camera, and that the
whole recording is wanted: cut it first if only part is.

To cut a take first, `python3 -I "$SKILL/scripts/cut.py" <project> --plan` transcribes on this
Mac, and the same command without `--plan` cuts the ranges listed in the project's `reel.json`
(see the top of the script). It also cuts a take's screen recording at the same moments, and
accepts a single video in place of a take. Render the room from `work/face_cut.mp4` and keep
the project outside the repository. Graphics, captions and assembly are not part of this skill.

**Not built yet:** the screen recording together with this full-frame look. `build.py` still
uses its own footage framing for the split screen and its older `solo` full-screen shots. Say
so if asked, and offer to wire it in.

## The style rules

These came from the creator reviewing real edits. `build.py` enforces most of them.

1. **Big text only.** No small labels, badge pills, kickers, header bar, brand tag
   or section chips. Their complaint: small labels sat on screen for a very long
   time. A headline is at most two lines of 17 characters, stays **4 seconds at
   most**, then leaves. Speech captions are the only continuous text.
2. **Head out of the card.** The wall behind the speaker is removed above the card
   line, so their head (cap and all) stands free in front of the app, and the face
   camera is a card with **rounded top corners**. They asked for this from a
   reference frame. It is the default (`face.layout: "popout"`); the card holds
   still while the face zooms inside it. Never go back to a flat full-width
   rectangle unless the cut-out truly fails on the footage, and say so if it does.
   **The corners must survive TikTok.** Phones taller than 9:16 fill the screen by height
   and cut the sides (computed for a 390×844 iPhone: about 48 of 1080 px per side above
   TikTok's tab bar, 97 px full screen; wider on 20:9 Android). With a 64 px radius the
   rounding vanished after posting. The card stays **edge to edge**; the `radius` is **200**
   so the curve starts well inside what gets cut. **Never inset the card or add space at
   the sides**: that was tried and rejected ("I didn't mean add spaces on the sides"). The
   head cut-out is clipped to the same shape below the card line. Check one frame as is and
   one cropped by 48 px per side. Keep important text within x 100–980.
3. **Studio finish on the face camera.** They asked for it to look like a very
   expensive camera, lighting and set, with **smooth, clean skin**. It is the default
   (`face.look: "studio"`). Their wall is replaced by a **calm room that matches the
   grade, seen at an angle** (`face.backdrop: "set"`: see "The studio set"); the face
   gets a following key light and a thin edge light; skin is evened; then the
   **copper-gold grade** below, which they chose from a reference tutorial. Clean, not
   plastic: pores, eyes, brows, lips, beard and clothing stay sharp. The **screen
   recording is never graded**, so the app's colours stay true.
4. **Full frame is wanted**, with the fitted room (see "Full frame"). An earlier version
   was rejected because the cut-out and made room did not hold up on soft 1080p footage;
   with sharp, well-lit upright 4K and the room matched to the camera's angle it was
   approved. When the screen is the subject, use the split screen.
5. **Keep the interface 3D and moving.** The screen is a 3D object, never a flat card:
   - a **camera shot** each time the narration points somewhere new, roughly every
     3–8 seconds, with push-ins on the exact button, number or row being discussed;
   - the face punches in when big text lands and breathes slowly otherwise
     (automatic).
   These rules are for this build. The creator's own videos follow their `reel` skill.
6. **Fonts match the interface in every video.** Find proof, never guess: the app's
   source CSS or font config, its app bundle, or the live site's computed
   `font-family`. A Mac app using `-apple-system` means SF Pro
   (`/System/Library/Fonts/SFNS.ttf`, mono `SFNSMono.ttf`). Captions, headlines
   and scenes all use it. Put the evidence in `font.source`. If you cannot tell,
   ask. Take the accent, 3D palette and logo from the same product. Never commit
   font files; they are copied into the gitignored project. Check that a listed
   web font is really loaded: a stylesheet naming a font nobody ships renders in
   the fallback. If the interface sets highlighted words in a second face (say an
   orange italic serif), put that file in `font.accent` and `*word*` uses it.
7. **Numbers on screen must be real:** read them off the screen or take them from what was
   said. Do not invent statistics, availability ("available now") or claims.

## Recording with Clapless (iPhone camera, Mac screen and mic)

Their own apps (`$REPO/apps/clapless`, build steps in `SETUP.md`). Better than the phone as a
webcam (which saves 1920×1080): the iPhone records the face in 4K (2160×3840, 30 fps, HEVC,
ordinary colour), the Mac records the screen (with cursor, leaving Clapless out) and the
chosen microphone, and the camera file reaches the Mac by itself over an encrypted link.

```bash
CLI="${CLAPLESS:-$REPO/apps/clapless}/scripts/clapless"
"$CLI" status    # link, camera, screen, microphone, warnings and anything blocking a take
"$CLI" start     # returns once the iPhone confirms
"$CLI" stop      # returns once the screen and mic files are saved; the camera file follows
"$CLI" takes     # wait until the take is "ready" and its sync method is "sound"
```

**Before each take** (ask them to do these): lens wiped; iPhone unlocked with Clapless open,
on its stand, upright, framed from the waist up with the table edge in or near the bottom of
the picture; light on the face and no stray light casting shapes on them (the app shows a
live reading: ISO 800 or lower is good, above 1400 it warns); the right microphone showing.

- Never start a take without being asked: it records the person and their screen.
- iOS stops the camera if Clapless leaves the screen or the phone locks.
- The apps show the live picture mirrored. `camera.mov` is not mirrored and the reel must
  never be: writing on their clothes has to read correctly.
- A take is `~/Movies/Clapless/<date_time>/`: `camera.mov`, `screen.mp4`, `mic.m4a`,
  `take.json`. Use it only when `status` is `ready`, and read its `warnings`.
- `screen.mp4` and `mic.m4a` begin at the same moment, so screen time is mic time.
- `take.json` `screen.app` is set when only that app was recorded: `screen.mp4` is then already
  its window (any size, black where a resized or switched window does not fill it). Take
  `screen_vf` from real frames; do not reuse a whole-screen crop. Without `screen.app` it is
  the whole screen.
- `take.json` `sync` holds the match by sound, made by `sync_camera.py`: use `videoOffset`
  and `videoDrift` when `matchedBySound` is true. If it is `weak`, check lips against sound
  at the start and end before building. If `matchedBySound` is false, do not edit with the
  clock guess: say so, and ask for a clap or a new take. `driftMeasured` is false for takes
  under about a minute.
- 4K30 is about 340 MB a minute. The iPhone keeps its own copy of every take.
- Older takes without a screen file: record the screen with ScreenKite (without a camera)
  and match with `sync_camera.py` as below.

To match by hand (also prints how many points agreed, the worst disagreement and `weak`):

```bash
uv run --no-project --python 3.13 --with numpy==2.5.5 python -I "$SKILL/scripts/sync_camera.py" <take>/camera.mov <take>/mic.m4a
```

Plan source for a Clapless take (convert the mic first, as in "Look and transcribe"):

```json
"a": {"video": "<take>/camera.mov", "screen": "<take>/screen.mp4", "audio": "mic_a.wav",
      "video_offset": -0.256, "video_drift": 0.0, "...": "..."}
```

`audio` is required: the phone's sound only lines the clips up. A vertical 4K clip needs a
new face `vf`, for example `crop=2160:1772:0:<top>,scale=1080:886:flags=lanczos`: choose
`<top>` from real frames.

## Workflow

### 1. Look and transcribe

- `ffprobe` every source. Make frame sheets and **read them**. Find the product
  name, its interface and its font.
- **ScreenKite recordings** keep separate, time-aligned tracks under `media/`
  (camera `.mov`, `raw/screen_display_0.mp4`, microphone `.m4a`). Convert the mic
  first so its small start delay is kept:
  `ffmpeg -i mic.m4a -af aresample=48000:async=1:first_pts=0 -ac 1 mic_a.wav`.
- Transcribe on-device. Do not download a model. Do not use ScreenKite's CLI
  transcription (needs the app open) or its automatic provider (can spend credits).

```bash
swiftc -O "$SKILL/scripts/transcribe.swift" -o <project>/transcribe
ffmpeg -i mic_a.wav -ar 16000 a16.wav
<project>/transcribe a16.wav <project>/words_a.json en-US
```

- Fix mishearings in `word_fixes`. Check product names, versions and numbers against
  the pixels. If a greeting or sign-off is unintelligible, keep the audio, drop
  those captions and ask what was said.

### 2. Decide before building

Ask only what changes the edit, in one go:
- Several recordings: one video or several? (Continuations are usually one.)
- **Would publishing expose them?** Client or project names, file lists, an
  unpatched vulnerable site, credentials, emails. Name what you saw and ask.

### 3. Choose the story

- Find what the creator is trying to say; keep lines that **prove** it on screen.
- The opening makes sense with zero context. Never lift a hook from mid-sentence.
- Keep their questions to viewers, calls to action and course plugs. In a revision,
  never silently drop a section or visual.
- Cut waiting ("I'll come back when it's done"), failed actions, sign-ins and
  repeats. Sign-off lines go last, even if a plug was recorded after them.
- Cut on word boundaries using `silencedetect` (about −48 dB for a quiet lav, −40
  for a normal one). A word is captioned only if its midpoint is inside the segment.
- Word timings can fold a pause into a neighbouring word, so a clean-looking cut can
  slice speech. Once `plan.json` exists, run
  `python3 -I "$SKILL/scripts/check_cuts.py" <project>` **before cutting**. Fix every
  "may be cut off" that names a real word (fillers can stay cut). "Speech both
  sides" alone is often a fine cut between words in fast speech: do not widen it if
  that only brings back a stumble. Settle doubts by transcribing the cut piece from
  `build/voice_<id>.wav`. (On one edit this found three lost words that the captions
  did not reveal.)
- Then capture the screen at the middle of every chosen line. Aim shots from what
  those frames actually show, not from the transcript.

### 4. Write plan.json

Generate it from a small `make_plan.py` in the project so revisions stay readable.

```json
{
  "tail": 3.6,
  "font": {"ui": "/System/Library/Fonts/SFNS.ttf", "mono": "/System/Library/Fonts/SFNSMono.ttf",
           "accent": "optional file for *highlighted* words",
           "source": "app style.css uses -apple-system"},
  "theme": {"ground": "#0e0e17", "accent": "#9283f5", "palette": ["#7465df", "#6fb9a9", "#eca677"], "logo": "logo.png"},
  "voice_filter": "highpass=f=80,afftdn=nf=-30",
  "sources": {"a": {"video": "camera.mov", "screen": "screen_display_0.mp4", "audio": "mic_a.wav",
                    "words": "words_a.json",
                    "vf": "crop=1317:1080:474:0,scale=1080:886:flags=lanczos",
                    "screen_vf": "crop=2360:1764:608:124,scale=1920:1436:flags=lanczos"}},
  "segments": [{"id": "a1", "src": "a", "in": 1.05, "out": 5.35}],
  "word_fixes": {"a": [{"at": 12.12, "text": "tool"}, {"at": 9.9, "text": null}]},
  "shots": [{"at": 0, "focus": [960, 716, 1980], "tilt": [8, -16]},
            {"at": "a@8.9", "focus": [420, 320, 900]}],
  "headlines": [{"at": 0, "hold": 3.9, "lines": ["I built a disk", "*cleanup tool.*"]}],
  "scenes": []
}
```

- `"a@8.9"` is a time in source `a`'s recording, so moves land on the spoken word.
- `vf` frames the face to **1080×886** (popout; 1080×720 for `panel`). Keep the full
  source height so there is room above the head: the build stops if the size is
  wrong. Centre the crop on the speaker's usual head position.
- `face` is optional: `{"layout": "popout", "card": 1310, "radius": 200}` are the
  defaults. `card` is the frame y of the card's top edge. Aim it at about the brim
  or forehead, so the crown of the head clears it even when they duck: measure the
  head across the chosen lines, not on one frame. `theme.scene`, `solid`,
  `solid_hi` and `edge` recolour the 3D and the screen slab for non-purple apps.
- `face.studio` overrides the look; leave it out unless the test frames need it.
  Defaults: `blur` 11 (px), `wall` 0.36 (room exposure, lower is darker), `pool`
  0.85, `practical` 0.6, `warm` (taken from `theme.accent`) and `cool` as `[r,g,b]`
  0–1, `key` 0.26, `rim` 0.24, `bloom` 0.07, `grain` 1.1, `skin` 0.82 (0 turns the
  retouch off), `gold` 1.0 and `selective` 0.5 (see the grade below).
  `face.look: "natural"` leaves the footage as shot.
- `face.matte` is how they are cut out: `"rvm"` (default) or `"vision"` (see "The
  cut-out").
- `face.backdrop` is `"set"` (default), `"room"` (the real wall: lens blur, darker,
  pool behind the head; `wall`, `pool`, `blur`, `practical` apply only here) or a
  picture file. `face.set` tunes the render: `fstop` 4.2 (lower is blurrier),
  `exposure` 0.8, `light` 1.0, `samples` 220, `seed` 7 (leaves, books, stems).
- `screen_vf` crops to the **app window only**
  (no menu bar, widgets, dock, browser tabs or bookmarks) and keeps it large, about
  1920 px wide, so push-ins stay sharp.
- `shots.focus` is `[centre x, centre y, width]` in `screen_vf` output pixels. A
  width near the window's own width shows it all; about 900–1100 is a close-up.
  `tilt` is optional (automatic: strong on wide shots, gentle on close-ups).
- `*word*` colours a word with the accent.

`scenes` takes the built-in 3D card scenes below. They are visuals made for the video, so
leave the list empty unless the creator asks for them (see "The creator's own videos"). An entry
looks like `{"type": "donut", "from": "a3", "lines": ["It has AI", "*built in.*"], "logo": "App name"}`;
`"end_card": true` instead of `from` makes it the closing card. `tail` is the time that card
holds after the voice; without a closing card the video ends with the voice, so give the last
segment a little room.

| Scene | Fields | Use it for |
|---|---|---|
| `donut` | `lines`, `logo` | the idea or feature; the end card |
| `meter` | `lines`, `figure` "94.9%", `data.fraction` | how full, done or complete |
| `pie` | `lines`, `figure`, `data.slices [{value,color,hot}]` | one share of a total |
| `cards` | `lines`, `items [{big,text,color}]` (up to 3) | categories, options, platforms |
| `trash` | `lines`, `count` | deleting, cleaning up, removing, plans that die |
| `gather` | `lines`, `count`, `logo` | people, community, meeting up; an end card |
| `coins` | `lines`, `figure` "R150", `count` | a price, a payment, money committed |

A scene covers segments `from`…`to` (optionally starting `at` a word) and lasts
0.8–7 s. Headlines may not start inside a scene. When a story needs a visual these
seven cannot show, add a builder to `assets/stage.html`. It must draw purely from
time (the `hf-seek` event): no `requestAnimationFrame`, clocks or unseeded random.

Aiming shots: a headline covers roughly y 0–540, so keep the subject below it
while big text is up. With no headline, don't aim so high that the window's top edge
drops far down the stage and leaves a dead gap (keep focus y ≥ about 540 × width /
1040). Cut or jump the camera when the page changes: a lingering shot lands on a
loading screen or empty space.

This layout needs a face camera **and** a screen recording. For footage without
both, say so and extend `build.py`; do not bring back labels or flat cards.
Plans written for the earlier label-card version of this skill are rejected.

### Full-screen shots inside the split-screen build (`solo`)

Older code, rejected at the time on 1080p footage ("the full screen is not really that
good"): `"solo": [{"from": "s1"}, {"from": "s22", "to": "s23"}]` (whole segments, no
overlap with 3D scenes) plus a per-source `solo_vf` that outputs 1080×1188 with the eyes
522 px down. It uses Apple's per-frame cut-out and the older tall room. Do not use it for the
approved full-frame look until it is wired to `room_reel.py`'s room, matte and settings.

What was learned: a soft shadow over speaker **and** room hides the foot of the footage (a
rendered desk there "looks fake positionally"); full-screen captions sit in that shadow,
slightly larger; the camera pulls back while big text is up so it stays clear of their head.

### The cut-out

`scripts/rvm_matte.py` (Robust Video Matting) remembers earlier frames, so edges hold
through motion, blur and gaps between fingers. Its memory is cleared at every cut. It
runs about 3 frames a second on an M1 Pro with Core ML (about 25 minutes for a
2-minute reel), is cached in `build/outline.mp4`, and is redone only after a re-cut or
a change to the script. `face.matte: "vision"` uses Apple's per-frame mask: faster, no
download, but it wobbled in motion and kept hard pale edges.

- **Neither cut-out is enough alone; `studio.swift` combines them.** The video outline
  invented large patches of the old wall during hand movements, and broke a hand that
  the picture edge cut off from the body into ragged "smoke". So it counts only within
  `gateReach` (14 px) of Apple's per-frame mask, and Apple's mask fills in farther than
  `bodyMargin` (22 px) from the video outline's solid body. Anything `deepInside`
  (9 px) Apple's mask is always kept: without it, thin cracks opened across blurred
  hands where the two outlines failed to meet. A faint pale smear can remain on very
  fast swipes against a pale wall.
- **A body part that blinks out for a few frames** can be Apple's mask dropping it while
  the video outline has it: the gate then removes it. On a 1080x1920 upright frame,
  `--ratio` 0.35 gave a solid, clean outline (0.8 and 0.45 left an arm half transparent);
  check that the outline has no detached patches, then set `face.studio.gate: false`.
  Scan the finished video for pixels that change when the footage does not.
- **Check each side separately, in motion.** One side can be fine and the other bad. The
  weak side is where window light puts a bright rim on the cheek against a pale wall:
  both then look alike to any cut-out. The creator saw this on one side only.
- **Test the moments with the most hand movement, and scan every frame.** A setting
  that looked best on a quiet clip failed on hand gestures nobody had tested. Dump the
  alpha for the whole video, list the frames with detached or large half-transparent
  areas, and look at each beside the original (a detached area is often just a hand).
- `--ratio` 0.8 follows the cheek and brow much better than 0.5 and leaves less haze,
  but is above the model's recommended working size; that is what caused the patches,
  which the gate removes.
- For the next recording, ask for: distance from the wall, a plain background that
  contrasts with skin and clothing, and no bright light grazing one side of the face.

### Capture advice

- An iPhone used as a Mac webcam (Continuity Camera) offers at most 1920×1440, and a
  recorder may save 1920×1080 even at its "Maximum" quality. The iPhone's own Camera
  settings do not apply to it. Probe the saved file rather than trusting the label.
- Best quality: record the face in the iPhone Camera app (4K, 30 fps, HDR off, Auto
  FPS off, white balance and lens locked, phone upright, waist up) and the screen in
  the recorder, clap once at the start, and keep the original files. Aligning two
  separate recordings is done by `sync_camera.py` (above), so a clap is only the
  fallback.
- In ScreenKite check the bitrate and the **microphone** before recording: it can fall
  back to "Default" when the wireless receiver was used before. For the face, use
  Clapless (above), which never switches to another microphone by itself.

### The studio set

`scripts/studio_set.py` models and path-traces the room, so it costs nothing and uses
no stock or generated pictures. The `face` stage renders it once into
`build/backdrop.png` (under a minute on an M1 Pro) and reuses it until it or its
settings change. The grade is applied to room and speaker together, which is what makes
them match.

**What they approved:** the room seen **into a corner, at an angle**. A window wall runs
away on the left (dark glazing bars, soft late light, treetops and roofs far outside,
a plant and two books on a deep sill). It meets a plain wall carrying a wooden table
with a stone vase of dry stems, a few books and one lamp.

How it got there, so it is not undone:
- A busy set (wood slats, light strips, shelves, sound panels, tube light) was too
  much: "we want to go with a background that does not have so many things showing up".
- A plain wall square to the camera was calmer but "too convenient"; they asked for the
  angle that well-regarded tech creators use, with a window one side and a table with a
  few things the other.
- No computer or screen: it adds a second light that fights the grade.
- The table stands **behind** the speaker. Nothing goes in front: the footage cannot
  support it.

When they ask for "a background like creator X", **look at real frames of those
videos** (written guides were generic and useless), take the framing, depth and layout,
and design your own room in the grade's colours.

Only about the lower 610 px of the face frame show and the speaker hides the middle, so
what must be seen belongs in the side zones (the window left of column 300, the lamp
near column 900 of 1080). Keep the wall behind the head calmer and greyer than the
skin: a copper-brown wall turned red after the grade and swallowed the face. Look at
the bare render first, then composites. It suits a still camera; if the real camera
moves a lot, the room will not move with it: say so or use `"room"`.

### Fitting the room to the footage

`scripts/probe.swift` samples the recording (Apple Vision outline and eyes) and
`scripts/fit_room.py` turns it into `set_options.json`; `room_reel.py` runs both. The options,
also usable as `face.set` in a split-screen plan:

- `mirror: true` puts the window on the right and the table on the left, so the room's
  light and table run the same way as the footage.
- `roll` (degrees, positive turns the picture counterclockwise) matches leaning verticals.
- `table_toward` (default `[1.088, 2.55]`): a larger second number flattens the table edge
  (3.2 gives about 3.4 degrees before roll, against 7.3 by default).
- `props` `{"vase": 0.62, "books": 1.40, "lamp": 1.78}` are distances from the corner,
  chosen so the speaker does not hide them. An upright full frame uses `size` `[1080, 1920]`,
  `eye_row` on the speaker's eyes and `exposure` about 1.35.

`fit_room.py` repeats the room's corner and table height from `studio_set.py`: change both.

### When the footage is already well lit

If they say the lighting is fine and want only smooth skin and a light colour touch, keep
their light: `face.studio` `{"key": 0, "rim": 0, "relight": 0, "bloom": 0.03, "grain": 0.6,
"skin": 0.8, "gold": 0.25, "selective": 0.1}`. `relight: 0` stops the chest and side
darkening and only gently calms shine.

### The copper-gold grade

Rebuilt from a Photoshop tutorial the creator sent as the result they wanted
(`goldGrade` in `scripts/studio.swift`). Bottom layer first, over the whole picture:

| Layer | Blend, opacity | What it does |
|---|---|---|
| Gradient map "Copper 1" (stops sampled from the video) | soft light, 30% | warm copper tone |
| Black & white "Blue Filter" (R, Y, G 0; C, B, M 110) | luminosity, 30% | deeper, richer skin |
| Selective colour: reds C −50 Y +30; yellows C −20 Y −50; neutrals K +5 | relative, `selective` | copper-gold skin, cleaner pale clothing |
| Gradient map "Platinum", dark stop moved to 50% | luminosity, 20% | depth in the shadows |
| Curves | normal | lit side up, shaded side down |

Both luminosity layers use Blend If (underlying layer, white slider split down to
0 / 255): full strength in the shadows, fading evenly to nothing at white. That is why
highlights stay glossy. The tutorial turns layers down to suit each picture, so do the
same: `selective` 0.5 suits a well-lit face (1.0 turned it orange and the lips red);
raise it only for a dark, moody shot.

**A reference means its technique.** When they send a video as "the result I want",
take how it is graded and lit. Do not rebuild the presenter's room or props: that was
tried (curtain folds, coloured wall, a lamp in the blur) and rejected with "I meant
their techniques, not himself". A background they ask for in their own words is
different: design it for them, in their grade's colours. Read exact settings off the screen, not only the
captions, and sample gradient colours from full-size frames.

### 5. Build, check, render

```bash
python3 -I "$SKILL/scripts/build.py" <project> --stage cut      # then redact, face, comp (or all)
python3 -I "$SKILL/scripts/build.py" <project> --stage face --stills 3,36,71,112   # check the look first
python3 -I "$SKILL/scripts/build.py" <project> --stage face     # outline + look; ~15 min per footage minute
cd <project>/comp
npx --yes hyperframes@0.9.90 check                    # must report 0 errors
npx --yes hyperframes@0.9.90 snapshot . --at 0.1,…    # every headline, scene and distinct shot
npx --yes hyperframes@0.9.90 render . --output ../<slug>-v1.mp4
```

Run cutting and rendering in the background; large ScreenKite files decode slowly,
especially when the Mac is low on memory (check `sysctl vm.swapusage`).

Text stays out of the platform-UI zones (top 14%, bottom 26%); the template does
this, so keep new elements inside y 270–1420 unless they are footage. Never chain a
build into `head` or `tail` before rendering: that hides a failed build.

The face stage runs on this Mac and is free: Robust Video Matting for the outline,
Apple Vision for face landmarks and Core Image for the look (`scripts/studio.swift`;
`scripts/matte.swift` cuts out the head when the look is `natural`). In the studio pass
each frame carries its outline as alpha, so the graded video and the cut-out share one
edge and one set of colours. Rerun `face` after every re-cut, re-blur or settings change
(`comp` refuses a stale one). Test frames made before the outline exists use Apple's
quick mask: judge colour and layout on them, and edges only after the full stage.

**Judge the test frames before the full run**, beside the originals, on at least
four different poses, enlarged:
- edges: no pale fringe or halo, no missing cap or ears, no blurred patch of person;
- skin: marks evened but pores still there, not waxy; tone true, not orange or grey
  (very warm grades did that to deeper skin); hair, hairline and beard keep texture;
- pale clothing is not clipped or yellow; black clothing is not crushed flat;
- the room is darker than the speaker, and the card still reads against the stage.

It reshapes light and colour in real footage. It cannot add detail the camera did not
record, so say that rather than promising a different camera. Never use a paid or
upload-based enhancer on their face without asking.

After rendering, also look at the head edge on a full-size frame from the MP4, and at
the face where the cut-out strip ends: no step in colour, captions above the head.

Read the snapshot sheets. Frame 0.1 has content. Every close-up shows the thing
being talked about, with readable text and no empty slab. Headlines do not cover
the one thing the viewer needs. 3D objects are inside the frame.

### 6. Private text

Look for what the browser adds as well as the page: password-manager "save
credential" pop-ups and page footers have both exposed an e-mail address. A pop-up
over a static header can be covered for those segments with a clean patch from an
earlier frame (a per-segment `screen_vf` using `movie=patch.png[p];[in][p]overlay=x:y,…`),
which is exact and needs no OCR. Prove any scan works: run it on a short unpatched
clip and see it fire, because a half-visible address will not match a full pattern.

Crop first (rule above), then `redact` rules for what remains:
`"redact": {"step": 1, "hold": 16, "rules": [{"regex": "…", "pad": 44, "band": false}]}`.
Blurring runs on both videos, about 10 minutes per 2 minutes of footage.
`<project>/build/redact scan <final.mp4> rules.json` checks the render. A clean scan
is **not proof**: OCR misses motion blur and only finds what the rules name.

### 7. Verify and deliver

- Probe duration and size; loudness about −14 LUFS (the QA engine's target), true peak ≤ −1 dBFS.
- Read frames across the whole timeline, from the MP4.
- Transcribe the rendered audio again and compare with the captions. A second pass
  has caught a wrong place name before.
- Report: lines cut, on-screen text you wrote, unsure words, privacy items, and
  whether you watched it end to end.

New versions are new files. Delete working files or old versions only when asked,
and confirm the kept copy is identical first.
