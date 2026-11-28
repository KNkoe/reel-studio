# History

What was built, what was rejected and why. Newest last. Paths in old entries refer to the
folder this work started in; the skill now lives in `skills/panel-reel/`. These are notes from
the author's own edits, kept so the reasons travel with the code.

## 2026-11-24 — Repoji demo reel (reference-style clone)
- Cut a 15-min vertical demo (already split screen/face, burned-in captions) down to a 37s reel in the style of an IG reel: dark graphic panel over cropped face, cream mono captions on the seam, orange outline-highlight cards, two full-screen takeovers.
- Built with ffmpeg EDL (12 word-boundary cuts) + one HyperFrames comp; verified on the rendered MP4 (37.3s, -16.7 LUFS, -1.5 dBFS TP).
- Lesson: the source render already had burned-in captions at the bottom of the face panel, so the face had to be cropped above them (softer, tighter than the reference); a raw camera track would avoid it.
- Not done: ElevenLabs SFX/music (no key), review-canvas publish (no here.now credentials).
- v2 (same day): extended to 66s with 5 more beats (game idea, Claude limits, free ChatGPT images + visuals, Gemini file edits); added the brand mark (cream tile on dark ground, since the mark's dark green vanishes on the dark panel) and switched accent to the mark's orange. v1 kept as its own file. Verified on render: 66.4s, -17.4 LUFS, -1.2 dBFS peak.
- v3/v4 (same day): v3 fixed a context-free opening (a hook cut from mid-sentence) by adding setup lines. v4 re-centred the story on the creator's actual point (use ChatGPT free even when out of usage limits) and made the real screen recordings the main content of the top panel, with graphics reduced to labels, highlights and 4 short cards. Lesson: pick the message from what the creator says they want, then choose cuts that PROVE it with their own screen footage; don't lead with a generic hook. Verified on render: 70.0s, -17.2 LUFS, -1.0 dBFS peak.

## 2026-11-24 — repoji reel v5

- Restored the multi-model / one-project section and connected-clients cards from v3; added both course asks and a held closing card; fixed the clipped last word. 123.0s, 1080x1920, -17.0 LUFS, -1.4 dBFS peak.
- Blurred a private document and project list visible in the opening screen recording (present unblurred in v4 and in the source render).
- Cut segments are now frame-exact with PCM audio per segment: concatenating per-segment AAC and unconstrained frame counts drifted audio against video by up to ~0.3s.
- Lessons: check cut ends against word timestamps and source loudness (several words were clipped); scan screen recordings for private data before first delivery.
- Verified from sampled frames, loudness and silence detection; not watched end to end.

## 2026-11-25 — saved the style as `panel-reel`; server incident reel v1

- New skill `panel-reel`: plan.json → frame-exact cuts, stereo loudness master, OCR blur of private on-screen text, graphic cards, captions. Footage layout and face + screen layout both pass the composition check. Linked into the user-level skill folders.
- v1: two handheld voice-over clips combined, 143.5s, 1080×1920, -13.6 LUFS (mastered before the stereo fix), -1.4 dBFS peak. Checked from sampled frames, an OCR scan and a re-transcript; not watched end to end.
- Lessons: Apple's on-device speech engine gives word timings with no model download. Handheld footage needs per-frame blur (every frame, long hold); digits garble in motion blur, so also anchor on an easier word on the same line. A mono voice measures about 3 LU quieter than the stereo render.

## 2026-11-25 — Reunion walkthrough reel (second `panel-reel` edit)

- ScreenKite recording (separate camera, screen and mic tracks) → 137.3s face + screen reel, v2, -16.6 LUFS, -1.3 dBFS peak. Per-section screen zooms framed out browser chrome and an email pop-up; the sign-in section was cut.
- `panel-reel` now accepts separate `screen` and `audio` files, blurs the screen video as well as the camera when rules exist, and no longer flickers between screen beats.
- Lesson: re-transcribing the render caught a wrong caption (a country name). Checked from sampled frames and an OCR scan; not watched end to end.

## 2026-11-25 — motion style; DiskBloom reel

- Creator feedback: no small labels or badges, big text only; more camera movement and 3D; fonts must match the interface. `panel-reel` was rebuilt around these: 3D screen stage with a shot list, face punch-ins, five three.js/CSS 3D scene types, interface font required with its source. Retired label-card plans are rejected.
- Delivered v3: two ScreenKite recordings, 197.6s, -14.9 LUFS, -1.4 dBFS peak. Local technical checks flag silences only (end card intended). Checked from sampled frames and a re-transcript; not watched end to end.
- Lessons: word timings can hide a pause and make a clean-looking cut drop a word (`check_cuts.py`). A failed composition build piped into `head` let a stale composition render over new footage; the build now deletes it first. The QA engine's frame check is paid and external, on by default when its key is in the environment: use `--skip-frames` unless approved (it ran twice unapproved here, about $0.02).

## 2026-11-25 — head-out-of-card layout; Reunion reel in the motion style

- Creator asked (with a reference frame) for the wall above their head to be removed and the face camera to be a card with rounded corners. `panel-reel` now does this by default (`face.layout: "popout"`): `scripts/matte.swift` (Apple Vision person segmentation, on-device) writes a transparent VP9 strip that HyperFrames layers over the rounded card; both share the punch-in zoom. `panel` keeps the old flat rectangle.
- Also new: `font.accent` for the interface's highlighted-word face, theme colours for the 3D and slab, `gather` and `coins` scenes, a stronger headline backing for light interfaces.
- Reunion v3: 138.4s, 1080×1920, -15.0 LUFS, -1.2 dBFS peak. Local checks flag the silent end card only (frame and Gemini checks skipped). Checked from sampled frames, an OCR scan for the private address and a re-transcript; not watched end to end.
- Lessons: the old cut had turned a country name into other words (`check_cuts.py` plus re-transcribing the piece found it). A browser save-password pop-up and the page footer both showed an e-mail; a static patch covers a pop-up over a fixed header, and a scan only counts once it has fired on an unpatched control. One cut ran into a loading screen.

## 2026-11-26 — studio look and copper-gold grade on the face camera

- Asked for colour grading, then "best studio quality, like an expensive camera and lighting",
  smooth clean skin, then sent a grading tutorial as the result wanted.
- New `panel-reel/scripts/studio.swift` (on-device, free): lens-blurred darker room, following key
  and edge light, skin retouch with eyes/brows/lips excluded, then the tutorial's five layers with
  settings read off its frames. One pass makes the graded video and the head cut-out.
- `build.py`: stage `matte` is now `face`; `--stills` previews it; `face.look` studio|natural;
  unknown settings are rejected; stale look or settings block `comp`; cut-out now tagged BT.709.
- Rejected on the way: strong ffmpeg warm grades (orange skin), and copying the presenter's set
  ("I meant their techniques, not himself"). A reference means its technique.
- Reunion v4 delivered: same cut and audio as v3, new look, opening caption "Keli December".

## 2026-11-26 (later) — studio set and full-screen moments (Reunion v5, v6)

- v5: a studio set modelled and path-traced in Blender (`panel-reel/scripts/studio_set.py`,
  on-device, free) replaces the wall, graded together with the speaker. First pass put the
  lamp and tube light under the card's zoom crop; moved inward.
- v6: asked for stretches showing only the speaker, with small camera moves. `plan.solo` +
  `solo_vf`; tall studio render, speaker as its own alpha layer, automatic camera moves.
- A rendered desk hiding the foot of the footage was rejected ("looks fake positionally").
  Replaced with a soft shadow over speaker and room. Full-screen captions sit in the shadow.
- Caught only by snapshots of the real composition (the check passed): a `.solo` CSS rule
  also hit captions and headlines and hid them all; a headline arriving 0.5 s after the last
  one did not pull the camera back. A hand-made mock-up showed neither.
- The recording is 1920x1080 and stops just below the shoulders: next time frame from the
  waist up, upright if the recorder allows.

## 2026-11-26 (later still) — calm angled room, video cut-out, no full screen (Reunion v7)

- Full-screen speaker moments rejected: at that size the cut-out and made room do not hold up.
  `plan.solo` stays in the code, off.
- The busy set was "so much". A flat wall was calmer but "too convenient". Approved after
  looking at real frames of well-known tech creators: a corner at an angle, window one side,
  table with a few things the other. No screens. Written guides were useless; frames were not.
- One side of the cut-out was bad in motion (window light rimming one cheek against a pale
  wall). Added `scripts/rvm_matte.py` (Robust Video Matting, Core ML, cached outline).
- Twice the first answer was wrong on moments nobody had tested: large wall patches, then
  hands broken where the picture edge cuts them off. `studio.swift` now gates the video
  outline by Apple's mask and lets Apple's mask fill in away from it. A third pass closed
  cracks that merging left in blurred hands. Lesson: test the biggest hand movements and
  scan the alpha of every frame, not a few quiet clips; re-scan after every merge change.
- After posting: TikTok cut off the card's rounded corners. First fix inset the card
  100 px: wrong, they wanted no side space, only a curve that starts early enough to
  survive the trim. Card stays edge to edge, radius 200 (was 64), cut-out clipped to match.
  Shown as one frame only (v7 footage); v7 was already posted and was not re-rendered.
- Recording setup: set the iPhone Camera settings and ScreenKite bitrate through screen
  control. Camera app settings do not apply to webcam recording.

## 2026-11-26 — recording on the iPhone's own camera

- iPhone Mirroring cannot use the camera, so it only served to set up Blackmagic Camera. Its
  HTTP Server gives a camera REST API (HTTPS 4444, no password) that can start and stop,
  set format and list clips, but offers no clip download.
- ScreenKite ships a `screenkite recording` command line: no button clicking needed, and
  leaving the camera off avoids it taking the iPhone as a webcam.
- New `panel-reel/scripts/record.py`, `mics.swift`, `sync_camera.py`; `build.py` accepts
  `video_offset` / `video_drift`. Tested: camera reads and format change, screen start and
  stop (tiny area, no mic), sync on altered copies of one recording.
- First real joint take (`record.py take`, built-in Mac mic): phone clip 2160x3840 H.265,
  360 frames in 12.00s (83 MB), screen 3600x2338 for 14.0s, exposure back to Continuous.
  Not yet checked: the picture itself (clip still on the phone), whether the exposure lock
  showed, two-mic sync on real files, the wireless mic.


## 2026-11-26 — first Clapless take checked against earlier camera footage

- 45 s take: 2160x3840 H.265 at 45 Mbps, no dropped frames (earlier webcam route:
  1920x1080 at 6 Mbps). Not yet better to look at: softer and darker face at ISO ~1800,
  a haze over the lower frame. Not a like-for-like test (clothes, light and time differ).
- Built-in Mac mic used, -44 LUFS (earlier wireless takes -22 to -28). No screen file in
  the take folder. Sync was a clock estimate only; matching by sound gave 0.257 s against
  the app's 0.224 s.
- Lesson: check mic, screen file, ISO and lens before judging a recorder's picture.

## 2026-11-26 — second Clapless take, picture only

- ISO ~1170 (was ~1810): face brightness 128 against 80 on take 1 and 125 on an earlier
  webcam take; about 1.4x the webcam's pixels across the face. Screen file and sound sync
  now present. Warm face against a green-blue wall; dark band at the very bottom, outside
  the planned face crop (calculated, not rendered).
- Saved camera file is not mirrored. Mac preview mirrors the front camera only; the
  creator wants the back-camera preview to move the same way they do (mirror behaviour).

## 2026-11-26 — third Clapless take, lens wiped

- Clearly better: crisper skin, lashes and lettering; darkest 1% fell from 17 to 6 (0-255)
  at the same ISO (~1170), white balance and face brightness (128). Framing also changed
  (white edge gone), so not all of it is the lens.
- The square-edged patch on the collar was a real shadow: the creator had a light placed
  behind. My phone-processing guess was wrong; no app change needed. Phone then moved a bit
  further back; no take checked since.
- Lesson: wipe the lens first, and ask about the lighting set-up before blaming the camera.

## 2026-11-26 — Clapless take 13:30 with the corner room (full upright frame)

- New take: well lit, no square shadows. Delivered a 30 s 1080x1920 file with the room
  replaced, skin smoothed, light colour touch, no relighting; camera audio carried over.
- Room fitted to the footage: mirrored (window right, matching their key light and the
  rising table edge), 1.5 degree roll, flatter table. New `studio_set.py` options
  `mirror`, `roll`, `table_toward`, `props`; new `studio.swift` settings `relight`, `gate`.
- Caught only by a frame-to-frame scan: the right arm vanished for two frames, twice.
  Contact sheets looked fine. Cause was the Apple-mask gate; ratio 0.35 plus gate off.
- A sliver of real table cut badly at the bottom corner; removed with a 3.5% zoom.
- Done with a project render script, not `build.py`: that still assumes a split screen.

## 2026-11-26 — full frame approved, room fitted automatically, Reel Studio

- The corner-room take was approved ("I love it, now we can have full frames our videos like
  we intended"). Full frame is wanted again.
- The camera is not fixed, so `probe.swift` and `fit_room.py` now measure roll, table slope,
  eye height and light side per recording; `room_reel.py` does the whole full-frame render.
  Checked on four takes: the measured lines sat on the real door frame and table edge where
  those showed. A hidden table edge falls back to the approved angle.
- The flicker scan also flags fast hand movement; the flagged frames looked intact on sample.
- Editing moved into this repository with Clapless linked at `apps/clapless`. Nothing was
  copied from the third-party editing pack the work started in (it has no licence file).
- Tested from a fresh clone on the same Mac: tool tests and Clapless tests pass and the room
  preview matched. Not tested on a second machine; the iPhone build was not rebuilt.

## 2026-11-26 — published as open source

- Reel Studio and Clapless made public under the MIT licence, with the pages rewritten for
  readers other than the author. Third-party tools and models keep their own licences.

## 2026-11-26 — talk-only recording with 3D scenes

- Asked for lots of 3D animation because there was no screen recording. Built the scenes in
  Blender (EEVEE, about 1 s a frame on an M1 Pro) with one shared kit, above the face card or
  full screen, with the full-frame speaker between them. Compositing was a project script.
- Checking 16 moments per rendered scene found what single stills missed: seconds of empty
  stage, titles over photos, and photo captions that could mislabel people.
- The 3D kit, cutter and compositor were then moved to `skills/panel-reel/three/` for reuse,
  with a movement preview (19 scenes in about 3 minutes, against a first render that had to
  be partly repeated). At 80% size, two test scenes rendered about 27% faster.

## 2026-11-27 — three views, and two looks

- The creator set the views: split most of the time, full face now and then, visuals only when
  a point is really being stressed.
- Interfaces keep the 3D feel. Visuals made for a video now follow a style they keep private,
  outside this repository.
- The 3D explainer tools were removed because renders took too long; they remain in git
  history. The talk-only cutter stays, as `scripts/cut.py`.
- With no card scenes by default, a screen reel without a closing card showed a blank screen and
  no speaker after the voice. It now ends with the voice (checked on synthetic footage).

## 2026-11-27 — screen recordings follow the private style

- The creator found a 3D screen stage does not fit their style, so their screen recordings now
  follow the private style too. The split-screen build stays for others.
- The cutter now cuts a take's screen recording at the same moments as the voice, accepts a
  single video in place of a take, and crops other shapes to 9:16 instead of stretching them
  (screen cutting tried on one take and on synthetic footage; a single video on synthetic footage).

## 2026-11-27 — the room can be recoloured

- `room_reel.py --room` takes a style file that swaps the room's colours and puts the speaker
  under the same light (tinted shadows and clothes, edge light from window and lamp). Without it
  nothing changes, except that the walls now reach lower, hiding a pale patch under the window.
- A style file can also name its own room script and an animation script, and the room tool can
  play a looping video behind the speaker (tried on a 10 s clip).

## 2026-11-27 — a faster room render at the same settings

- The cut-out and the room render now run together: the cut-out writes 10-second parts and the
  room renderer follows. On a 30 s clip on an M1 Pro those steps and the flicker check took 239 s
  instead of 317 s. Not yet timed on a long video.
- A recording that is already upright 1080x1920, 30 fps, BT.709 H.264 is no longer converted
  again (this took 5 minutes on a 6-minute cut and cost a little quality).
- The flicker scan reads a few seconds at a time instead of both whole videos; it reported the
  same frames as before on two pairs.
- Found by comparing frames: the first version of the parts made macOS read one extra frame from
  the first part, so the outline ran a frame behind the whole way, and the parts did not split on
  time. With both fixed, parts and the finished outline gave identical frames, 900 of 900.
- Against the old tool the result differs slightly (the input is no longer converted first). A
  dark gap under the arm, which the old cut-out already switched between person and wall, now
  switches on slightly different frames.

## 2026-11-28 — cleaning the speech

- Edits kept every filler and stumble: the cutter only shortened pauses and dropped whole
  ranges. `tidy.py` now shows the kept speech as a script with likely repeats and false starts,
  and `cut.py` removes fillers and chosen words. The skill says what to remove and what to keep.
- Word timings from the transcriber often include the silence before a word and can be about
  0.2 s off, so cuts placed on them clipped neighbouring words. Each cut is now placed from the
  audio and checked by transcribing the join, trying other positions if a neighbour is lost.
- Tried on the sound of one 8-minute recording: 30 fillers and 38 stumbled words came out
  (about 49 s). A second transcription heard no fillers; two joins were flagged for a person to
  check. Nobody has listened to it yet, and picture jumps at these cuts have not been reviewed.
