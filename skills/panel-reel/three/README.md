# Talk-only recordings: 3D explainer reels

For a recording of someone explaining something with no screen recording: the full-frame
speaker, 3D scenes above their face card (or full screen), big headlines and captions.

## A project

A folder outside this repository (footage and client material stay out of git):

```
my-reel/
  sources/take/      a Clapless take: camera.mov, mic.m4a, take.json
  photos/            pictures to show
  scenes.py          the 3D scenes (start from example/scenes.py)
  reel.json          what to keep, headlines, caption fixes
  work/              everything generated
  renders/           finished videos, numbered
```

`reel.json`:

```json
{"name": "my-reel", "accent": "#f86923", "lifts": {},
 "cut": {"take": "sources/take", "keep": [["hook", 1.45, 5.98]], "long": 0.62, "leave": 0.17, "tail": 2.4},
 "headlines": [[4.7, 8.0, ["TWO LINES", "AT MOST"]]],
 "fixes": {"3.90": "Spelled", "12.78": null}}
```

## The order

`T` is this folder; `P` is the project.

1. `python3 -I $T/cut.py $P --plan` transcribes on this Mac. Fill in `cut.keep`, run again,
   then without `--plan` to cut. Re-transcribe the cut voice to catch clipped words.
2. Agree a short scene list with the speaker: what appears during which words.
3. Start the face render in the background (about 12 minutes per minute of video on an M1 Pro):
   `python3 -I $T/../scripts/room_reel.py $P/work/face_cut.mp4 $P/work/room`
4. Write `scenes.py`. Times come from `work/words_edit.json`.
5. **Preview the movement:** `python3 -I $T/render.py $P --preview` (about 3 minutes for
   19 scenes). Read every sheet in `work/preview/`. Fix, preview again.
6. `python3 -I $T/render.py $P` renders (about 1 second a frame at full size). `--scale 80`
   is about a quarter faster and was hard to tell apart on stills; ask before using it if
   quality matters more than time.
7. `uv run --no-project --python 3.13 --with numpy==2.5.5 --with pillow==12.0.0 python -I $T/compose.py $P --stills 5,40`
   to check frames, then without `--stills` (about 15 minutes for 5 minutes of video).
8. Check the file: length, loudness, no black or frozen stretches, frames across the whole
   video, the layout changes, and the speech transcribed again.
9. When the video is approved: `python3 -I $T/render.py $P --pack`, then delete the large
   intermediates (`work/cut`, `work/face_cut*.mp4`, `work/room/face.mp4`).

## What is in the toolkit

| File | What it gives a scene |
|---|---|
| `kit.py` | the set, camera, lights, materials, shapes, text and motion; `scene`, `SPLIT`, `FULL` |
| `props.py` | titles, labels, shield, coins, documents, flags, photo prints, confetti, towers, magnifier, gears, trophies, record stacks, ticks and crosses |
| `geo.py` | real country outlines (`place`, `extrude`) and a dotted globe |
| `assets.py` | fetches fonts, outlines and studio lighting, checked against fixed checksums |

Set `props.SHIELD_WORD` and `props.COIN_FACE` from the scene file. Match fonts and colours to
the product being explained.

## Lessons

- Still frames miss empty stretches, titles over pictures and slow entrances: preview.
- Do not caption photos with claims about the particular people in them.
- Every number on screen must be said, or read from the speaker's own material.
