#!/usr/bin/env python3
"""Build a motion reel (3D screen stage over a face camera) from plan.json.

    build.py <project-dir> [--stage cut|redact|face|comp|all]
    build.py <project-dir> --stage face --stills 3,36,71     (test frames of the look, in build/look/)

cut     frame-exact video segments + loudness-normalised voice (and the full-screen camera
        footage for plan.solo)
redact  blur private on-screen text (only when plan.redact is set)
face    the speaker's outline (Robust Video Matting), studio look (a rendered studio set
        behind the speaker, clean skin, grade) and the head cut-out that rises above the
        rounded face card
comp    captions, cards and HyperFrames composition in <project>/comp/
"""
import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "stage.html"
FPS, RATE = 30, 48000
W, H = 1080, 1920


def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True)


def ffmpeg(*cmd):
    run("ffmpeg", "-v", "error", "-y", *cmd)


# "popout": the speaker's head and cap stand free above a rounded card; the wall behind them
# is removed above the card line. "panel": the older flat rectangle, for footage that will not cut out.
FACE_LAYOUTS = {
    "popout": {"top": 1034, "card": 1310, "radius": 200, "stage_h": 1420, "stage_cy": 670, "cap_top": 900,
               "origin": "50% 75%", "wide": 1.035, "punch": 1.05, "held": 1.07},
    "panel": {"top": 1200, "card": 1200, "radius": 0, "stage_h": 1200, "stage_cy": 790, "cap_top": 1144,
              "origin": "50% 34%", "wide": 1.075, "punch": 1.11, "held": 1.14},
}


LOOKS = ("studio", "natural")   # "natural": the footage exactly as shot
STUDIO_KEYS = {"blur", "wall", "pool", "warm", "cool", "practical", "key", "rim", "bloom", "grain", "skin", "gold", "selective", "relight", "gate"}


SET_KEYS = {"fstop", "exposure", "light", "samples", "seed", "mirror", "roll", "table_toward", "props"}

# How the speaker is cut out. "rvm" (Robust Video Matting, GPL-3.0, fetched once, not shipped
# here) remembers earlier frames, so edges hold while the speaker moves. "vision" is Apple's
# per-frame person mask: nothing to download, but it wobbles where a lit edge meets a pale wall.
MATTES = ("rvm", "vision")
RVM_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50_fp32.onnx"
RVM_BYTES = 107_479_165
RVM_MODEL = Path.home() / ".cache" / "panel-reel" / "models" / "rvm_resnet50_fp32.onnx"


# The card runs edge to edge. Phones taller than 9:16 fill the screen by height and cut the sides
# off (about 48 of our 1080 px per side on a 390x844 iPhone above TikTok's tab bar, 97 px full
# screen), so the corner curve is made big enough to start well inside what gets cut.
def cut_clip(face) -> str:
    """CSS path for the head cut-out: free above the card line, held inside the card's own rounded
    shape below it, so a hand at the side cannot fill a corner in."""
    line, r, bottom = face["card"] - face["top"], face["radius"], H - face["top"]
    return f"M0 0H{W}V{line}H{W - r}A{r} {r} 0 0 1 {W} {line + r}V{bottom}H0V{line + r}A{r} {r} 0 0 1 {r} {line}H0Z"


def face_layout(options):
    name = options.get("layout", "popout")
    if name not in FACE_LAYOUTS:
        raise SystemExit(f"face.layout must be one of {sorted(FACE_LAYOUTS)}")
    face = {**FACE_LAYOUTS[name], **options, "layout": name}
    face.setdefault("look", "studio")
    if face["look"] not in LOOKS:
        raise SystemExit(f"face.look must be one of {list(LOOKS)}")
    unknown = set(face.get("studio", {})) - STUDIO_KEYS
    if unknown:   # a misspelt setting would otherwise be ignored without a word
        raise SystemExit(f"unknown face.studio settings: {sorted(unknown)}")
    # "set": a rendered studio replaces the wall; "room": the real wall, relit; or a picture of your own.
    if face["look"] == "studio":
        face.setdefault("backdrop", "set")
    elif face.get("backdrop"):
        raise SystemExit('face.backdrop needs face.look "studio"')
    face.setdefault("matte", "rvm")
    if face["matte"] not in MATTES:
        raise SystemExit(f"face.matte must be one of {list(MATTES)}")
    unknown = set(face.get("set", {})) - SET_KEYS
    if unknown:
        raise SystemExit(f"unknown face.set settings: {sorted(unknown)}")
    face["height"] = H - face["top"]
    if face["height"] % 2:
        raise SystemExit("face.top must be even")
    if not face["top"] <= face["card"] < H:
        raise SystemExit("face.card must sit between face.top and the bottom of the frame")
    # The cut-out only needs to reach below the card's rounded corners, including at full punch-in.
    face["rows"] = min(face["height"], (face["card"] - face["top"] + face["radius"] + 60) // 2 * 2)
    return face


# "solo": the speaker alone fills the frame, for lines said to camera while nothing on screen
# is being shown. The camera frame sits at rows top..top+height of a 1080x1920 studio, eyes on
# "eyes". A soft shadow falls over speaker and room alike and is solid by "floor", above where
# the footage ends, so the foot of the picture is never seen.
SOLO = {"top": 398, "height": 1188, "eyes": 920, "floor": 1570, "origin_y": 1300}
SOLO_MIN = 1.5


def video_size(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return tuple(int(v) for v in probe.stdout.strip().split(",")[:2])


class Plan:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.data = json.loads((self.root / "plan.json").read_text())
        self.face = face_layout(self.data.get("face", {}))
        self.segments, offset = [], 0.0
        seen = set()
        for seg in self.data["segments"]:
            if seg["id"] in seen:
                raise SystemExit(f"duplicate segment id {seg['id']}")
            seen.add(seg["id"])
            frames = round((seg["out"] - seg["in"]) * FPS)
            if frames < 1:
                raise SystemExit(f"segment {seg['id']} is empty")
            self.segments.append({**seg, "frames": frames, "start": offset, "dur": frames / FPS})
            offset += frames / FPS
        self.voice = offset
        # The footage ends with the voice. Only a closing card has anything to show after it.
        closing = any(scene.get("end_card") for scene in self.data.get("scenes", []))
        self.total = offset + (self.data.get("tail", 2.5) if closing else 0.0)
        self.by_id = {s["id"]: s for s in self.segments}
        self.solo = self.solo_windows()

    def solo_windows(self):
        windows, offset = [], 0.0
        ids = [s["id"] for s in self.segments]
        for item in self.data.get("solo", []):
            first, last = item["from"], item.get("to", item["from"])
            if first not in ids or last not in ids or ids.index(last) < ids.index(first):
                raise SystemExit(f"solo {item}: 'from' and 'to' must be segment ids, in order")
            run_of = self.segments[ids.index(first):ids.index(last) + 1]
            start, end = run_of[0]["start"], run_of[-1]["start"] + run_of[-1]["dur"]
            if end - start < SOLO_MIN:
                raise SystemExit(f"solo {first}..{last} lasts {end - start:.1f}s; shorter than {SOLO_MIN}s reads as a glitch")
            windows.append({"start": start, "end": end, "ids": [s["id"] for s in run_of]})
        windows.sort(key=lambda w: w["start"])
        for a, b in zip(windows, windows[1:]):
            if b["start"] < a["end"] - 0.01:
                raise SystemExit("solo windows overlap")
        if windows and (self.face["look"] != "studio" or self.face["backdrop"] == "room"):
            raise SystemExit('plan.solo needs the studio look with a studio set or a picture behind the speaker')
        for window in windows:   # where this window starts inside the joined solo footage
            window["offset"] = offset
            offset += window["end"] - window["start"]
        return windows

    def path(self, value) -> Path:
        p = Path(value).expanduser()
        return p if p.is_absolute() else self.root / p

    def at(self, ref, beat_start: float) -> float:
        """A number is seconds after the beat starts; "key@12.3" is a source timestamp."""
        if isinstance(ref, (int, float)):
            return beat_start + ref
        key, t = ref.split("@")
        t = float(t)
        for seg in self.segments:
            if seg["src"] == key and seg["in"] - 0.15 <= t <= seg["out"] + 0.05:
                return seg["start"] + max(0.0, t - seg["in"])
        raise SystemExit(f"timing {ref!r} is not inside any segment")


def camera_in(source, seg) -> float:
    """Where a segment starts in the camera file. A camera recorded on its own device (such as
    a Clapless take) has its own clock: sync_camera.py gives video_offset and video_drift."""
    offset, drift = source.get("video_offset", 0.0), source.get("video_drift", 0.0)
    if (offset or drift) and "audio" not in source:
        raise SystemExit("a source with video_offset needs its own 'audio' (the screen recording's microphone)")
    at = seg["in"] + offset + drift * seg["in"]
    if at < 0:
        raise SystemExit(f"segment {seg['id']} begins {-at:.2f}s before the camera started recording")
    return round(at, 4)


def concat(plan: Plan, work: Path, prefix: str, ext: str, out: Path):
    listing = work / f"{prefix}.txt"
    listing.write_text("".join(f"file '{prefix}_{s['id']}.{ext}'\n" for s in plan.segments))
    ffmpeg("-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", out)


def cut(plan: Plan):
    work = plan.root / "build"
    work.mkdir(exist_ok=True)
    has_screen = any("screen_vf" in s for s in plan.data["sources"].values())
    height = plan.face["height"]
    enc = ["-c:v", "libx264", "-crf", "14", "-preset", "fast", "-pix_fmt", "yuv420p", "-an"]
    for seg in plan.segments:
        source = plan.data["sources"][seg["src"]]
        seek = ["-hwaccel", "videotoolbox", "-ss", camera_in(source, seg), "-t", seg["dur"] + 0.5, "-i",
                plan.path(source["video"])]
        default = f"scale={W}:{height}:force_original_aspect_ratio=increase,crop={W}:{height}"
        tail = f",fps={FPS},tpad=stop_mode=clone:stop_duration=1,setsar=1"
        vf = seg.get("vf") or source.get("vf") or default
        ffmpeg(*seek, "-vf", vf + tail, "-frames:v", seg["frames"], *enc, work / f"lower_{seg['id']}.mp4")
        if has_screen:
            svf = seg.get("screen_vf") or source.get("screen_vf")
            if not svf:
                raise SystemExit(f"source {seg['src']} needs screen_vf because another source has one")
            screen_seek = ["-hwaccel", "videotoolbox", "-ss", seg["in"], "-t", seg["dur"] + 0.5, "-i", plan.path(source.get("screen", source["video"]))]
            ffmpeg(*screen_seek, "-vf", svf + tail, "-frames:v", seg["frames"], *enc, work / f"screen_{seg['id']}.mp4")
        samples = seg["frames"] * RATE // FPS
        af = (f"aresample={RATE},apad,atrim=end_sample={samples},"
              f"afade=t=in:d=0.012,afade=t=out:st={seg['dur'] - 0.012:.4f}:d=0.012")
        audio_seek = ["-ss", seg["in"], "-t", seg["dur"] + 0.5, "-i", plan.path(source.get("audio", source["video"]))]
        ffmpeg(*audio_seek, "-vn", "-ac", "1", "-af", af, "-c:a", "pcm_s16le", work / f"voice_{seg['id']}.wav")
    if plan.solo:
        cut_solo(plan, work, enc)
    concat(plan, work, "lower", "mp4", work / "lower.mp4")
    if video_size(work / "lower.mp4") != (W, height):
        raise SystemExit(f"face video is {video_size(work / 'lower.mp4')}, the {plan.face['layout']} layout needs "
                         f"{(W, height)}: end the face 'vf' with scale={W}:{height} (crop to the same shape first)")
    if has_screen:
        concat(plan, work, "screen", "mp4", work / "screen.mp4")
    concat(plan, work, "voice", "wav", work / "voice_raw.wav")
    master(plan, work)


def cut_solo(plan: Plan, work: Path, enc):
    """The same camera footage, framed for the full screen, for the solo windows only."""
    pieces = []
    for seg in (plan.by_id[i] for window in plan.solo for i in window["ids"]):
        source = plan.data["sources"][seg["src"]]
        vf = source.get("solo_vf")
        if not vf:
            raise SystemExit(f"source {seg['src']} needs solo_vf: scale the camera about 1.1x and crop to "
                             f"{W}x{SOLO['height']} with the head centred and the eyes {SOLO['eyes'] - SOLO['top']} px down")
        piece = work / f"solo_{seg['id']}.mp4"
        ffmpeg("-hwaccel", "videotoolbox", "-ss", camera_in(source, seg), "-t", seg["dur"] + 0.5, "-i",
               plan.path(source["video"]), "-vf", vf + f",fps={FPS},tpad=stop_mode=clone:stop_duration=1,setsar=1",
               "-frames:v", seg["frames"], *enc, piece)
        pieces.append(piece)
    listing = work / "solo.txt"
    listing.write_text("".join(f"file '{p.name}'\n" for p in pieces))
    ffmpeg("-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", work / "solo.mp4")
    if video_size(work / "solo.mp4") != (W, SOLO["height"]):
        raise SystemExit(f"solo footage is {video_size(work / 'solo.mp4')}; solo_vf must end at {(W, SOLO['height'])}")


def master(plan: Plan, work: Path):
    """Two-pass loudnorm so quiet phone recordings reach platform loudness cleanly."""
    # Measure and master in stereo: a mono voice reads about 3 LU louder once rendered.
    clean = "aformat=channel_layouts=stereo," + plan.data.get("voice_filter", "highpass=f=75")
    target = "loudnorm=I=-14:TP=-1.5:LRA=11"   # -14 LUFS, the usual social target
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(work / "voice_raw.wav"), "-af",
                            f"{clean},{target}:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True, check=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    second = (f"{target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
              f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    ffmpeg("-i", work / "voice_raw.wav", "-af", f"{clean},{second}", "-ar", RATE, "-c:a", "aac",
           "-b:a", "192k", work / "voice.m4a")


def redact(plan: Plan):
    rules = plan.data.get("redact")
    if not rules:
        print("no redact rules in plan; skipping")
        return
    work = plan.root / "build"
    binary = work / "redact"
    run("swiftc", "-O", HERE / "redact.swift", "-o", binary)
    (work / "rules.json").write_text(json.dumps(rules))
    for name in ("lower", "screen", "solo"):
        if (work / f"{name}.mp4").exists():
            run(binary, "render", work / f"{name}.mp4", work / "rules.json", work / f"{name}_redacted.mp4")


def face_source(plan: Plan) -> Path:
    return plan.root / "build" / ("lower_redacted.mp4" if plan.data.get("redact") else "lower.mp4")


def studio_settings(plan: Plan):
    settings = {}
    accent = plan.data.get("theme", {}).get("accent", "")
    if re.fullmatch(r"#[0-9a-fA-F]{6}", accent):   # the coloured practical light matches the interface
        settings["warm"] = [round(int(accent[i:i + 2], 16) / 255, 3) for i in (1, 3, 5)]
    return {**settings, **plan.face.get("studio", {})}


def digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


def backdrop_stamp(plan: Plan):
    """What the background is made from, so a changed set or picture makes the face video stale."""
    choice = plan.face.get("backdrop")
    if choice in (None, "room"):
        return choice
    if choice == "set":
        return {"set": {"size": [W, plan.face["height"]], **plan.face.get("set", {})},
                "script": digest(HERE / "studio_set.py")}
    picture = plan.path(choice)
    if not picture.is_file():
        raise SystemExit(f'face.backdrop must be "set", "room" or a picture file; not found: {picture}')
    return {"picture": digest(picture)}


def render_set(plan: Plan, work: Path, name: str, extra) -> Path:
    """Render one view of the studio set, or reuse it while its recipe is unchanged."""
    recipe = {"set": {**backdrop_stamp(plan)["set"], **extra}, "script": digest(HERE / "studio_set.py")}
    picture, record = work / f"{name}.png", work / f"{name}.json"
    if picture.exists() and record.exists() and json.loads(record.read_text()) == recipe:
        return picture
    blender = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
    if not Path(blender).exists():
        raise SystemExit('the studio set needs Blender (free, blender.org). Install it, or set face.backdrop '
                         'to "room" (the real wall, relit) or to a picture file')
    record.unlink(missing_ok=True)
    picture.unlink(missing_ok=True)
    (work / f"{name}_options.json").write_text(json.dumps(recipe["set"]))
    print(f"rendering the studio set: {name} (a few minutes)")
    run(blender, "--background", "--factory-startup", "--python-exit-code", "1", "--python", HERE / "studio_set.py",
        "--", picture, work / f"{name}_options.json")
    if not picture.exists():
        raise SystemExit("Blender did not write the studio set")
    record.write_text(json.dumps(recipe))
    return picture


def backdrop_file(plan: Plan, work: Path) -> str:
    """The picture that goes behind the speaker, rendering the studio set if it is not there yet."""
    choice = plan.face["backdrop"]
    if choice == "room":
        return ""
    if choice != "set":
        return str(plan.path(choice))
    return str(render_set(plan, work, "backdrop", {}))


def face_solo(plan: Plan, work: Path, binary: Path):
    """Layers for the full-screen shots: the graded studio and the speaker with alpha. Kept apart so the
    camera can move them by different amounts, which reads as real depth."""
    source = work / ("solo_redacted.mp4" if plan.data.get("redact") else "solo.mp4")
    if not source.exists():
        raise SystemExit(f"missing {source.name}: run --stage cut again, plan.solo needs its footage")
    if plan.face["backdrop"] == "set":
        bare = render_set(plan, work, "solo_set", {"size": [W, H]})
    else:   # your own tall picture
        bare = work / "solo_picture.png"
        ffmpeg("-i", plan.path(plan.face["backdrop"]), "-vf",
               f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", "-frames:v", "1", bare)
    settings = studio_settings(plan)
    # the room with nobody in it, through the very same grade
    empty, shots = work / "empty.mp4", work / "graded"
    shots.mkdir(exist_ok=True)
    ffmpeg("-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={FPS}", "-frames:v", "1", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", empty)
    (work / "graded.json").write_text(json.dumps({**settings, "backdrop": str(bare)}))
    run(binary, empty, work / "graded.json", "--stills", "0", shots)
    (shots / "studio_0.png").replace(work / "solo_bg.png")
    region = work / "solo_region.png"
    ffmpeg("-i", bare, "-vf", f"crop={W}:{SOLO['height']}:0:{SOLO['top']}", "-frames:v", "1", region)
    (work / "solo_studio.json").write_text(json.dumps({**settings, "backdrop": str(region)}))
    partial = work / "solo_person.partial.webm"
    cutter = subprocess.Popen([str(binary), str(source), str(work / "solo_studio.json")], stdout=subprocess.PIPE)
    encode = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{SOLO['height']}",
         "-r", str(FPS), "-i", "pipe:0", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuva420p",
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
         "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "22", "-g", str(FPS), "-deadline", "good", "-cpu-used", "4",
         "-row-mt", "1", "-auto-alt-ref", "0", str(partial)], stdin=cutter.stdout)
    cutter.stdout.close()
    if cutter.wait() or encode.returncode:
        raise SystemExit("full-screen speaker layer failed")
    partial.replace(work / "solo_person.webm")


def outline_stamp(plan: Plan, source: Path):
    info = source.stat()
    return {"source": [info.st_size, info.st_mtime_ns], "script": digest(HERE / "rvm_matte.py"),
            "cuts": [round(s["start"] * FPS) for s in plan.segments]}


def outline(plan: Plan, work: Path, source: Path, make=True) -> str:
    """The speaker's outline as a grey video, reused while the footage is unchanged. "" means
    the grading program should use Apple's per-frame mask instead."""
    if plan.face["matte"] != "rvm":
        return ""
    video, record = work / "outline.mp4", work / "outline.json"
    recipe = outline_stamp(plan, source)
    if video.exists() and record.exists() and json.loads(record.read_text()) == recipe:
        return str(video)
    if not make:
        return ""
    if not shutil.which("uv"):
        raise SystemExit('the video cut-out needs uv (docs.astral.sh/uv); or set face.matte to "vision"')
    if not RVM_MODEL.exists() or RVM_MODEL.stat().st_size != RVM_BYTES:
        print(f"downloading the cut-out model once ({RVM_BYTES / 1e6:.0f} MB, free) to {RVM_MODEL}")
        RVM_MODEL.parent.mkdir(parents=True, exist_ok=True)
        fetched = RVM_MODEL.with_suffix(".partial")
        run("curl", "-fL", "--retry", "3", "-sS", "-o", fetched, RVM_URL)
        if fetched.stat().st_size != RVM_BYTES:
            raise SystemExit("the cut-out model did not download completely")
        fetched.replace(RVM_MODEL)
    record.unlink(missing_ok=True)
    partial = work / "outline.partial.mp4"
    print(f"cutting out the speaker, {plan.voice * FPS:.0f} frames (about 3 a second on an M1 Pro)", flush=True)
    run("uv", "run", "--no-project", "--python", "3.13", "--with", "onnxruntime==1.32.0", "--with", "numpy==2.5.5", "python", "-I",
        HERE / "rvm_matte.py", RVM_MODEL, source, partial, "--cuts", ",".join(map(str, recipe["cuts"])))
    partial.replace(video)
    record.write_text(json.dumps(recipe))
    return str(video)


def face_stamp(plan: Plan):
    cut_out = ([plan.face["matte"], digest(HERE / "rvm_matte.py"), digest(HERE / "studio.swift")]
               if plan.face["look"] == "studio" else None)
    return {"matte": cut_out, "look": plan.face["look"], "rows": plan.face["rows"] if plan.face["layout"] == "popout" else 0,
            "studio": studio_settings(plan) if plan.face["look"] == "studio" else {},
            "backdrop": backdrop_stamp(plan),
            "solo": {"ids": [w["ids"] for w in plan.solo], "frame": SOLO} if plan.solo else None}


def face_video(plan: Plan) -> Path:
    return plan.root / "build" / "lower_studio.mp4" if plan.face["look"] == "studio" else face_source(plan)


def compile_swift(name: str, work: Path) -> Path:
    binary = work / f"{name}_bin"
    run("swiftc", "-O", "-suppress-warnings", HERE / f"{name}.swift", "-o", binary)
    return binary


def face(plan: Plan, stills=None):
    """The studio look on the face camera, plus the transparent strip that lets the head leave the card."""
    work, source = plan.root / "build", face_source(plan)
    if not source.exists():
        raise SystemExit(f"missing {source.name}: run --stage cut (and redact) before face")
    studio, popout = plan.face["look"] == "studio", plan.face["layout"] == "popout"
    settings = work / "studio.json"
    if studio:
        behind = backdrop_file(plan, work)
        made = outline(plan, work, source, make=not stills)
        settings.write_text(json.dumps({**studio_settings(plan), "backdrop": behind, "matte": made}))
    if stills:
        if not studio:
            raise SystemExit("--stills previews the studio look; face.look is natural")
        out = work / "look"
        out.mkdir(exist_ok=True)
        frames = ",".join(str(round(t * FPS)) for t in stills)
        run(compile_swift("studio", work), source, settings, "--stills", frames, out)
        print(f"test frames in {out}")
        if plan.face["matte"] == "rvm" and not made:
            print("these use the quick per-frame cut-out; judge edges after a full --stage face")
        return
    if not studio and not popout:
        return
    stamp = work / "face.json"
    stamp.unlink(missing_ok=True)
    height, rows = plan.face["height"], plan.face["rows"]
    colour = "scale=out_color_matrix=bt709:out_range=tv"   # say which matrix, so both layers decode alike
    tags = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    vp9 = ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "20", "-g", str(FPS), "-deadline", "good",
           "-cpu-used", "4", "-row-mt", "1", "-auto-alt-ref", "0"]
    full, strip = work / "lower_studio.partial.mp4", work / "cutout.partial.webm"
    if studio:   # one pass: every frame arrives with the speaker's outline as its alpha channel
        producer = [str(compile_swift("studio", work)), str(source), str(settings)]
        size, graph, outputs = f"{W}x{height}", [], []
        full_out = [*tags, "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-g", str(FPS), "-an", str(full)]
        if popout:
            graph = ["-filter_complex", f"[0:v]split=2[a][b];[a]{colour},format=yuv420p[full];"
                     f"[b]crop={W}:{rows}:0:0,{colour},format=yuva420p[cut]"]
            outputs = ["-map", "[full]", *full_out, "-map", "[cut]", *tags, *vp9, str(strip)]
        else:
            outputs = ["-vf", f"{colour},format=yuv420p", *full_out]
    else:
        producer = [str(compile_swift("matte", work)), str(source), str(rows)]
        size, graph = f"{W}x{rows}", []
        outputs = ["-vf", f"{colour},format=yuva420p", *tags, *vp9, str(strip)]
    cutter = subprocess.Popen(producer, stdout=subprocess.PIPE)
    encode = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", size,
                             "-r", str(FPS), "-i", "pipe:0", *graph, *outputs], stdin=cutter.stdout)
    cutter.stdout.close()
    if cutter.wait() or encode.returncode:
        raise SystemExit("face stage failed")
    if studio:
        full.replace(work / "lower_studio.mp4")
    if popout:
        strip.replace(work / "cutout.webm")
    if plan.solo:
        face_solo(plan, work, work / "studio_bin")
    stamp.write_text(json.dumps(face_stamp(plan)))


# ---------------------------------------------------------------------------
# Composition. The style rules the creator asked for are enforced here, so a
# future edit cannot quietly drift back: no labels or badges, big text that
# leaves quickly, interface-matched fonts, camera movement on every beat.
# ---------------------------------------------------------------------------
MAX_HOLD = 4.0       # seconds a big headline may stay up
MAX_LINE = 17        # characters per headline line at 104px
MAX_SCENE = 7.0
STAGE_CX, FIT_W = 540, 1040
RETIRED = {"beats", "badge", "kicker", "brand", "outro"}
SCENE_TYPES = {"donut", "meter", "pie", "cards", "trash", "gather", "coins"}


def esc(text: str) -> str:
    """HTML-escape, turning *word* into an accent span."""
    return re.sub(r"\*(.+?)\*", r"<em>\1</em>", html.escape(text, quote=False))


def visible(text: str) -> str:
    return text.replace("*", "")


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_keys(value)


def validate(plan: Plan):
    data = plan.data
    banned = RETIRED & set(walk_keys({k: v for k, v in data.items() if k != "sources"}))
    if banned:
        raise SystemExit(f"retired keys {sorted(banned)}: this style has no labels, badges, kickers or header. "
                         "Use headlines (big text) and scenes.")
    font = data.get("font", {})
    if not font.get("ui") or not font.get("source"):
        raise SystemExit("plan.font needs 'ui' (a font file) and 'source' (where you saw the interface use it)")
    if not data.get("shots"):
        raise SystemExit("plan.shots is empty: the screen needs camera moves")
    for item in data.get("headlines", []) + data.get("scenes", []):
        for line in item.get("lines", []):
            if len(visible(line)) > MAX_LINE:
                raise SystemExit(f"headline line too long for big text ({len(visible(line))} > {MAX_LINE}): {line!r}")
        if len(item.get("lines", [])) > 2:
            raise SystemExit(f"big text is two lines at most: {item['lines']}")
    for item in data.get("headlines", []):
        if item.get("hold", 3.0) > MAX_HOLD:
            raise SystemExit(f"headline holds {item['hold']}s; text must not linger beyond {MAX_HOLD}s")
    for scene in data.get("scenes", []):
        if scene["type"] not in SCENE_TYPES:
            raise SystemExit(f"unknown scene type {scene['type']!r}")


def scene_windows(plan: Plan):
    out = []
    for scene in plan.data.get("scenes", []):
        if scene.get("end_card"):
            start, end = plan.voice, plan.total
        else:
            first, last = plan.by_id[scene["from"]], plan.by_id[scene.get("to", scene["from"])]
            start = plan.at(scene["at"], 0) if "at" in scene else first["start"]
            end = last["start"] + last["dur"]
        if not 0.8 <= end - start <= MAX_SCENE:
            raise SystemExit(f"scene {scene['type']} lasts {end - start:.1f}s; keep it between 0.8 and {MAX_SCENE}s")
        for window in plan.solo:
            if start < window["end"] - 0.02 and window["start"] < end - 0.02:
                raise SystemExit(f"scene {scene['type']} ({start:.1f}-{end:.1f}s) overlaps a solo window "
                                 f"({window['start']:.1f}-{window['end']:.1f}s)")
        out.append({**scene, "start": round(start, 3), "end": round(end, 3)})
    out.sort(key=lambda s: s["start"])
    for a, b in zip(out, out[1:]):
        if b["start"] < a["end"] - 0.01:
            raise SystemExit(f"scenes overlap at {b['start']:.1f}s")
    return out


def headline_windows(plan: Plan, scenes):
    items = []
    for h in plan.data.get("headlines", []):
        start = plan.at(h["at"], 0) if isinstance(h["at"], str) else float(h["at"])
        items.append({"start": 0.0 if start < 0.25 else start, "hold": h.get("hold", 3.0), "lines": h["lines"]})
    items.sort(key=lambda h: h["start"])
    for i, h in enumerate(items):
        end = h["start"] + h["hold"]
        if i + 1 < len(items):
            end = min(end, items[i + 1]["start"] - 0.12)
        for scene in scenes:
            if scene["start"] <= h["start"] < scene["end"]:
                raise SystemExit(f"headline {h['lines']} starts inside the {scene['type']} scene")
            if h["start"] < scene["start"] < end:
                end = scene["start"] - 0.02
        for window in plan.solo:   # big text sits differently in each layout, so it leaves with it
            for edge in (window["start"], window["end"]):
                if h["start"] < edge - 0.05 < end:
                    end = edge - 0.02
        if end - h["start"] < 0.9:
            raise SystemExit(f"headline {h['lines']} would show for only {end - h['start']:.1f}s")
        h["end"] = round(end, 3)
    return items


def camera_track(plan: Plan, width: int, height: int):
    """Each shot flies to a region of the screen, then keeps drifting until the next."""
    shots = []
    for i, shot in enumerate(plan.data["shots"]):
        t = plan.at(shot["at"], 0) if isinstance(shot["at"], str) else float(shot["at"])
        fx, fy, fw = shot["focus"]
        scale = FIT_W / fw
        if scale > 1.2:
            raise SystemExit(f"shot at {shot['at']} zooms past the source resolution (width {fw} < {FIT_W / 1.2:.0f})")
        strength = min(1.0, max(0.35, fw / width))
        side = 1 if i % 2 else -1
        rx, ry = shot.get("tilt", [round(9 * strength, 2), round(side * 17 * strength, 2)])
        shots.append({"t": max(0.0, t), "x": width / 2 - fx, "y": height / 2 - fy, "s": scale, "rx": rx, "ry": ry,
                      "move": shot.get("move", 0.85)})
    shots.sort(key=lambda s: s["t"])
    if shots[0]["t"] > 0.05:
        raise SystemExit("the first shot must start at 0")
    js, first = [], shots[0]
    js.append(f'tl.set("#pan",{{x:{first["x"]:.1f},y:{first["y"]:.1f}}},0);')
    js.append(f'tl.fromTo("#cam",{{scale:{first["s"] * 0.62:.4f},rotationX:24,rotationY:-38,z:-420}},'
              f'{{scale:{first["s"]:.4f},rotationX:{first["rx"]},rotationY:{first["ry"]},z:0,duration:1.5,ease:"power3.out"}},0);')
    clock = 1.5
    for i, shot in enumerate(shots):
        after = shots[i + 1]["t"] if i + 1 < len(shots) else plan.voice
        if i:
            move = max(0.25, min(shot["move"], after - shot["t"] - 0.05))
            at = max(shot["t"], clock)
            js.append(f'tl.to("#pan",{{x:{shot["x"]:.1f},y:{shot["y"]:.1f},duration:{move:.3f},ease:"power3.inOut"}},{at:.3f});')
            js.append(f'tl.to("#cam",{{scale:{shot["s"]:.4f},rotationX:{shot["rx"]},rotationY:{shot["ry"]},duration:{move:.3f},ease:"power3.inOut"}},{at:.3f});')
            clock = at + move
        drift = after - clock - 0.02
        if drift > 0.3:
            push = min(1.2, shot["s"] * 1.06)
            js.append(f'tl.to("#cam",{{scale:{push:.4f},rotationY:{shot["ry"] * 0.35:.2f},rotationX:{shot["rx"] * 0.5:.2f},'
                      f'duration:{drift:.3f},ease:"sine.inOut"}},{clock:.3f});')
            clock += drift
    return js


def face_track(plan: Plan, headlines):
    """Punch in when big text lands; otherwise breathe slowly between two framings."""
    marks = [(h["start"], h["end"]) for h in headlines if h["start"] > 0.3]
    face = plan.face
    js, clock, wide = ['tl.set(".zoom",{scale:1.0},0);'], 0.0, True

    def breathe(until):
        nonlocal clock, wide
        while until - clock > 0.6:
            length = min(5.0, until - clock)
            if until - clock - length < 0.6:
                length = until - clock
            js.append(f'tl.to(".zoom",{{scale:{face["wide"] if wide else 1.0},duration:{length - 0.01:.3f},ease:"sine.inOut"}},{clock:.3f});')
            clock += length
            wide = not wide

    for start, end in marks:
        if start < clock:
            continue
        breathe(start)
        js.append(f'tl.to(".zoom",{{scale:{face["punch"]},duration:0.16,ease:"power4.out"}},{start:.3f});')
        js.append(f'tl.to(".zoom",{{scale:{face["held"]},duration:{max(0.2, end - start - 0.2):.3f},ease:"none"}},{start + 0.17:.3f});')
        js.append(f'tl.to(".zoom",{{scale:1.0,duration:0.3,ease:"power2.out"}},{end:.3f});')
        clock, wide = end + 0.31, True
    breathe(plan.voice)
    return js


def sentence_ends(plan: Plan):
    """Times on the edit's clock where a new phrase begins: the natural places to change framing."""
    marks = []
    for seg in plan.segments:
        words = json.loads(plan.path(plan.data["sources"][seg["src"]]["words"]).read_text())
        inside = [w for w in words if seg["in"] <= (w[0] + w[1]) / 2 < seg["out"]]
        marks += [seg["start"] + max(0.0, b[0] - seg["in"]) for a, b in zip(inside, inside[1:]) if a[2][-1:] in ".?!,"]
        marks.append(seg["start"])
    return sorted(marks)


def text_spans(window, headlines):
    """When big text is up inside a window. Spans with only a short gap are one, and a span that
    nearly reaches an edge of the window runs to it: the camera never darts in between two lines."""
    start, end, spans = window["start"], window["end"], []
    for h in sorted(headlines, key=lambda h: h["start"]):
        a, z = max(start, h["start"]), min(end, h["end"])
        if z - a < 0.1:
            continue
        a = start if a - start < 1.2 else a
        z = end if end - z < 1.2 else z
        if spans and a - spans[-1][1] < 1.2:
            spans[-1][1] = max(spans[-1][1], z)
        else:
            spans.append([a, z])
    return spans


def solo_beats(plan: Plan, window, headlines):
    """Split a solo window into (start, end, under_text) beats of about 2 to 4.5 seconds. Where big
    text arrives or leaves is always a boundary; phrase ends divide what lies between."""
    spans = text_spans(window, headlines)
    edges = sorted({window["start"], window["end"], *(t for span in spans for t in span)})
    marks, beats = sentence_ends(plan), []
    for start, end in zip(edges, edges[1:]):
        under = any(a - 0.01 <= start and end <= z + 0.01 for a, z in spans)
        cuts = [start]
        for mark in marks:
            if start < mark < end - 1.7 and mark - cuts[-1] >= 2.3:
                cuts.append(mark)
        for a, z in zip(cuts, cuts[1:] + [end]):
            parts = max(1, int((z - a) // 4.6) + (1 if z - a > 4.6 and (z - a) % 4.6 > 1.6 else 0))
            beats += [(a + (z - a) * i / parts, a + (z - a) * (i + 1) / parts, under) for i in range(parts)]
    return beats


def crown_rows(work: Path):
    """Frame row of the top of the head in each full-screen frame, read from the cut-out itself."""
    cols, rows = 270, SOLO["height"] // 4
    raw = subprocess.run(["ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i", str(work / "solo_person.webm"), "-vf",
                          f"alphaextract,scale={cols}:{rows}:flags=neighbor", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                         capture_output=True, check=True).stdout
    tops = []
    for f in range(len(raw) // (cols * rows)):
        picture = raw[f * cols * rows:(f + 1) * cols * rows]
        # the middle only: a raised hand at the side is not the head
        top = next((r for r in range(rows) if sum(v > 128 for v in picture[r * cols + 60:r * cols + 210]) >= 6), rows)
        tops.append(SOLO["top"] + top * 4)
    return tops


# (scale from, scale to, x from, x to, y, tilt) for the speaker; the set follows by less.
# x stays within (scale - 1) * 450, so no layer ever shows an edge.
FRAMINGS = {
    "medium": (1.080, 1.130, -22, -8, 0, -0.35),
    "wide": (1.030, 1.075, 12, 4, 6, 0.0),
    "close": (1.150, 1.185, 6, -4, -4, 0.30),
    "side": (1.100, 1.135, 30, 12, 0, 0.45),
}
UNDER_TEXT = (1.000, 1.010, 0, 0, 34, 0.0)   # big text is up: stay back and sit a little lower
TEXT_FOOT, MAX_DROP = 505, 92               # keep the head under this row; never push the chin onto captions


def solo_track(plan: Plan, headlines, crowns):
    """Camera moves for the full-screen shots: jump cuts and short pushes on phrase changes, a slow
    drift inside each beat, and speaker and room moving by different amounts."""
    js, order, count = [], ["medium", "close", "wide", "side"], 0
    for i, window in enumerate(plan.solo):
        js.append(f'tl.set("#solo{i}",{{autoAlpha:1}},{window["start"]:.3f});')
        if window["end"] < plan.voice - 0.05:
            js.append(f'tl.set("#solo{i}",{{autoAlpha:0}},{window["end"] - 0.001:.3f});')
        for n, (a, b, under) in enumerate(solo_beats(plan, window, headlines)):
            if under:   # sit as low as the highest the head gets while the text is up (ignoring stray frames)
                first = int((window["offset"] + a - window["start"]) * FPS)
                heads = sorted(crowns[first:first + max(1, int((b - a) * FPS))])
                lowest_needed = TEXT_FOOT - heads[len(heads) // 20] if heads else 0
                shot = UNDER_TEXT[:4] + (min(MAX_DROP, max(UNDER_TEXT[4], lowest_needed)),) + UNDER_TEXT[5:]
            else:
                shot = FRAMINGS[order[count % len(order)]]
                count += 1
            s0, s1, x0, x1, y, tilt = shot

            def layers(scale, x, lift, turn):
                depth = scale - 1
                return [(f"#sman{i}", f"scale:{scale:.4f},x:{x:.1f},y:{lift:.1f},rotation:{turn:.2f}"),
                        (f"#sbg{i}", f"scale:{1.02 + depth * 0.45:.4f},x:{-x * 0.28:.1f},y:0,rotation:{turn * 0.35:.2f}")]

            arrive = 0.0
            if n == 0:       # into the full screen: land with a quick settle
                arrive = 0.45
                for (target, start_at), (_, land) in zip(layers(s0 + 0.09, x0, y, tilt), layers(s0, x0, y, tilt)):
                    js.append(f'tl.fromTo("{target}",{{{start_at}}},{{{land},duration:{arrive},ease:"power3.out",immediateRender:false}},{a:.3f});')
            elif n % 3 == 2 and not under:   # every third change glides; the rest are jump cuts
                arrive = 0.5
                for target, land in layers(s0, x0, y, tilt):
                    js.append(f'tl.to("{target}",{{{land},duration:{arrive},ease:"power3.inOut"}},{a:.3f});')
            else:
                for target, land in layers(s0, x0, y, tilt):
                    js.append(f'tl.set("{target}",{{{land}}},{a:.3f});')
            drift = b - a - arrive - 0.02
            if drift > 0.2:
                for target, land in layers(s1, x1, y, tilt * 0.4):
                    js.append(f'tl.to("{target}",{{{land},duration:{drift:.3f},ease:"sine.inOut"}},{a + arrive + 0.001:.3f});')
    return js


def captions(plan: Plan, takeovers):
    words = {}
    for key, source in plan.data["sources"].items():
        loaded = json.loads(plan.path(source["words"]).read_text())
        fixes = {round(f["at"], 2): f["text"] for f in plan.data.get("word_fixes", {}).get(key, [])}
        unused = set(fixes) - {round(w[0], 2) for w in loaded}
        if unused:
            raise SystemExit(f"word_fixes for {key} match no word start: {sorted(unused)}")
        words[key] = [(a, b, fixes.get(round(a, 2), t)) for a, b, t in loaded]
    chunks = []
    for seg in plan.segments:
        current, size = [], 0
        for a, b, text in words[seg["src"]]:
            # A word belongs to a segment when most of it is inside the cut.
            if text is None or not (seg["in"] <= (a + b) / 2 < seg["out"]):
                continue
            shown = re.sub(r'[.,?!"]+$', "", text).strip('"')
            if not shown or shown.lower() in ("um", "uh", "ah"):
                continue
            start = seg["start"] + max(0.0, a - seg["in"])
            end = seg["start"] + min(seg["dur"], b - seg["in"])
            if current and size + len(shown) > 22:
                chunks.append(current)
                current, size = [], 0
            current.append((start, end, shown))
            size += len(shown) + 1
            if len(current) >= 3 or re.search(r"[.,?!]$", text):
                chunks.append(current)
                current, size = [], 0
        if current:
            chunks.append(current)
    out = []
    for i, chunk in enumerate(chunks):
        start = max(0.0, chunk[0][0] - 0.03)
        limit = chunks[i + 1][0][0] - 0.03 if i + 1 < len(chunks) else plan.voice
        end = max(start + 0.1, min(chunk[-1][1] + 0.25, limit))
        cls = "cap take" if any(a <= start + 0.05 < b for a, b in takeovers) else "cap"
        if any(w["start"] <= start + 0.05 < w["end"] for w in plan.solo):
            cls = "cap solo"
        for w in plan.solo:   # a caption never carries across a change of layout
            for edge in (w["start"], w["end"]):
                if start < edge - 0.05 < end:
                    end = max(start + 0.1, edge)
        text = html.escape(" ".join(w[2] for w in chunk).upper(), quote=False)
        out.append(f'<div class="clip {cls}" id="c{i}" data-start="{start:.3f}" data-duration="{end - start - 0.001:.3f}" '
                   f'data-track-index="3"><span>{text}</span></div>')
    return out


def comp(plan: Plan):
    validate(plan)
    work, dest = plan.root / "build", plan.root / "comp"
    # A failed rebuild must never leave an old composition that renders over new footage.
    (dest / "index.html").unlink(missing_ok=True)
    assets = dest / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    rules = plan.data.get("redact")
    if plan.face["look"] == "studio" or plan.face["layout"] == "popout":
        stamp = work / "face.json"
        made = [work / n for n, wanted in (("lower_studio.mp4", plan.face["look"] == "studio"),
                                           ("cutout.webm", plan.face["layout"] == "popout"),
                                           ("solo_person.webm", bool(plan.solo))) if wanted]
        if (not stamp.exists() or json.loads(stamp.read_text()) != face_stamp(plan) or not face_source(plan).exists()
                or any(not f.exists() or f.stat().st_mtime < face_source(plan).stat().st_mtime for f in made)):
            raise SystemExit("the face look or head cut-out is missing, or older than the footage or settings: "
                             "run --stage face")
    for name in ("lower", "screen"):
        source = work / (f"{name}_redacted.mp4" if rules else f"{name}.mp4")
        finished = name == "lower" and plan.face["look"] == "studio"
        if finished:
            source = face_video(plan)
        if not source.exists():
            raise SystemExit(f"missing {source.name}: this layout needs face and screen video"
                             + (" (run --stage redact)" if rules else ""))
        if rules and not finished:   # re-encode for dense keyframes
            ffmpeg("-i", source, "-c:v", "libx264", "-crf", "16", "-g", FPS, "-pix_fmt", "yuv420p", "-an", assets / f"{name}.mp4")
        else:
            shutil.copy(source, assets / f"{name}.mp4")
    shutil.copy(work / "voice.m4a", assets / "voice.m4a")
    face, cutout = plan.face, ""
    if face["layout"] == "popout":
        shutil.copy(work / "cutout.webm", assets / "cutout.webm")
        cutout = (f'<div id="cutwrap" class="zoom"><video id="cutout" class="clip" data-start="0" data-duration="{plan.voice:.3f}" '
                  f'data-track-index="4" src="assets/cutout.webm" muted playsinline></video></div>')
    solo_html = []
    if plan.solo:
        for name in ("solo_bg.png", "solo_person.webm"):
            shutil.copy(work / name, assets / name)
        for i, window in enumerate(plan.solo):
            solo_html.append(
                f'<div class="solowrap" id="solo{i}"><img class="solobg" id="sbg{i}" src="assets/solo_bg.png" alt="">'
                f'<div class="soloman" id="sman{i}"><video id="sv{i}" class="clip" data-start="{window["start"]:.3f}" '
                f'data-duration="{window["end"] - window["start"] - 0.001:.3f}" data-media-start="{window["offset"]:.3f}" '
                f'data-track-index="7" src="assets/solo_person.webm" muted playsinline></video></div>'
                f'<div class="soloshade" data-layout-allow-occlusion></div></div>')
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(assets / "screen.mp4")], capture_output=True, text=True, check=True)
    win_w, win_h = (int(v) for v in probe.stdout.strip().split(",")[:2])

    font = plan.data["font"]
    faces = []
    for family, key in (("UIFont", "ui"), ("UIMono", "mono")):
        path = plan.path(font.get(key) or font["ui"])
        if not path.exists():
            raise SystemExit(f"font file not found: {path}")
        shutil.copy(path, assets / f"{key}{path.suffix}")
        faces.append(f'@font-face {{ font-family:"{family}"; src:url("assets/{key}{path.suffix}"); font-weight:1 1000; }}')

    # Highlighted *words* can use the interface's own display accent (say, an italic serif headline word).
    accent = plan.path(font["accent"]) if font.get("accent") else None
    if accent:
        if not accent.exists():
            raise SystemExit(f"font file not found: {accent}")
        shutil.copy(accent, assets / f"accent{accent.suffix}")
        faces.append(f'@font-face {{ font-family:"UIAccent"; src:url("assets/accent{accent.suffix}"); font-weight:1 1000; }}')

    theme = {"ground": "#0e0e17", "accent": "#9283f5", "ink": "#f6f7fb", "cap_bg": "#ffffff", "cap_ink": "#252739",
             "palette": ["#7465df", "#6fb9a9", "#eca677"], "scene": "#242142", "solid": "#6f66b8", "solid_hi": "#b4aaff",
             "edge": ["#c9c8da", "#8e8aa8", "#4b4766"], **plan.data.get("theme", {})}
    logo = ""
    if theme.get("logo"):
        path = plan.path(theme["logo"])
        shutil.copy(path, assets / f"logo{path.suffix}")
        logo = f"assets/logo{path.suffix}"

    scenes = scene_windows(plan)
    headlines = headline_windows(plan, scenes)
    js = camera_track(plan, win_w, win_h) + face_track(plan, headlines)
    if plan.solo:
        js += solo_track(plan, headlines, crown_rows(work))

    title_html = []
    for i, h in enumerate(headlines):
        spans = "".join(f'<span class="hl" id="h{i}_{n}">{esc(line)}</span>' for n, line in enumerate(h["lines"]))
        solo = any(w["start"] - 0.05 <= h["start"] < w["end"] for w in plan.solo)
        title_html.append(f'<div class="clip headline{" solo" if solo else ""}" id="h{i}" data-start="{h["start"]:.3f}" '
                          f'data-duration="{h["end"] - h["start"] - 0.001:.3f}" data-track-index="5">{spans}</div>')
        for n in range(len(h["lines"])):
            at = h["start"] + n * 0.09
            if h["start"] <= 0.05:
                js.append(f'tl.set("#h{i}_{n}",{{opacity:1,y:0,rotationX:0}},0);')
            else:
                js.append(f'tl.fromTo("#h{i}_{n}",{{opacity:0,y:60,rotationX:-75}},{{opacity:1,y:0,rotationX:0,duration:0.38,'
                          f'ease:"back.out(1.5)",immediateRender:false}},{at:.3f});')
            js.append(f'tl.to("#h{i}_{n}",{{opacity:0,y:-40,rotationX:55,duration:0.2,ease:"power2.in"}},{h["end"] - 0.22:.3f});')
        if not solo:   # the scrim keeps text readable over the app; over the speaker it would cover the cap
            js.append(f'tl.fromTo("#scrim",{{opacity:{1 if h["start"] <= 0.05 else 0}}},{{opacity:1,duration:0.25,immediateRender:false}},{h["start"]:.3f});')
            js.append(f'tl.to("#scrim",{{opacity:0,duration:0.2}},{h["end"] - 0.2:.3f});')

    scene_html = []
    for i, scene in enumerate(scenes):
        body = "".join(f'<span class="big" id="s{i}_{n}">{esc(line)}</span>' for n, line in enumerate(scene.get("lines", [])))
        extra = ""
        if scene["type"] in ("meter", "pie", "coins"):
            extra = f'<div class="figure" id="fig{i}">{html.escape(scene.get("figure", ""))}</div>'
        if scene["type"] == "cards":
            cells = "".join(
                f'<div class="card3d" id="s{i}_c{n}" style="--c:{c.get("color", theme["accent"])}">'
                f'<b>{html.escape(c["big"])}</b><span>{html.escape(c["text"])}</span></div>'
                for n, c in enumerate(scene["items"]))
            extra = f'<div class="deck">{cells}</div>'
        if scene.get("logo") and logo:
            extra += f'<div class="lockup"><img src="{logo}" alt=""><b>{html.escape(scene["logo"])}</b></div>'
        scene_html.append(f'<div class="clip scene s-{scene["type"]}" id="scene{i}" data-start="{scene["start"]:.3f}" '
                          f'data-duration="{scene["end"] - scene["start"] - 0.001:.3f}" data-track-index="6">'
                          f'<div class="words">{body}</div>{extra}</div>')
        for n in range(len(scene.get("lines", []))):
            js.append(f'tl.fromTo("#s{i}_{n}",{{opacity:0,scale:1.5,rotationX:-60}},{{opacity:1,scale:1,rotationX:0,duration:0.42,'
                      f'ease:"back.out(1.4)",immediateRender:false}},{scene["start"] + 0.06 + n * 0.14:.3f});')
        for n in range(len(scene.get("items", [])) if scene["type"] == "cards" else 0):
            step = min(0.7, (scene["end"] - scene["start"]) / (len(scene["items"]) + 1.5))
            js.append(f'tl.fromTo("#s{i}_c{n}",{{opacity:0,x:{(-1) ** n * 700},rotationY:{(-1) ** n * 80},z:-500}},'
                      f'{{opacity:1,x:0,rotationY:{(-1) ** n * -9},z:0,transformPerspective:1600,duration:0.6,ease:"power3.out",immediateRender:false}},'
                      f'{scene["start"] + 0.25 + n * step:.3f});')
        if scene["type"] != "cards" and scene.get("figure"):
            js.append(f'tl.fromTo("#fig{i}",{{opacity:0,y:50}},{{opacity:1,y:0,duration:0.4,immediateRender:false}},{scene["start"] + 0.35:.3f});')
        if scene.get("logo") and logo:
            js.append(f'tl.fromTo("#scene{i} .lockup",{{opacity:0,y:40}},{{opacity:1,y:0,duration:0.5,immediateRender:false}},{scene["start"] + 0.3:.3f});')

    gl_scenes = [{k: s[k] for k in ("type", "start", "end", "data", "count") if k in s} | {"index": i}
                 for i, s in enumerate(scenes) if s["type"] != "cards"]
    takeovers = [(s["start"], s["end"]) for s in scenes]
    page = TEMPLATE.read_text()
    fill = {
        "TOTAL": f"{plan.total:.3f}", "VOICE": f"{plan.voice:.3f}", "FONT_FACES": "\n      ".join(faces),
        "GROUND": theme["ground"], "ACCENT": theme["accent"], "INK": theme["ink"],
        "CAP_BG": theme["cap_bg"], "CAP_INK": theme["cap_ink"],
        "WIN_W": str(win_w), "WIN_H": str(win_h), "HALF_W": str(win_w // 2), "HALF_H": str(win_h // 2),
        "CX": str(STAGE_CX), "CY": str(face["stage_cy"]), "STAGE_H": str(face["stage_h"]),
        "FACE_TOP": str(face["top"]), "FACE_H": str(face["height"]), "CARD_Y": str(face["card"] - face["top"]),
        "CARD_H": str(H - face["card"]), "CARD_TOP": str(face["card"]), "RADIUS": str(face["radius"]),
        "CUT_CLIP": cut_clip(face),
        "CUT_H": str(face["rows"]), "ORIGIN": face["origin"], "CAP_TOP": str(face["cap_top"]), "CUTOUT": cutout,
        "SEAM": "none" if face["layout"] == "popout" else "block",
        "SCENE_BG": theme["scene"], "EDGE1": theme["edge"][0], "EDGE2": theme["edge"][1], "EDGE3": theme["edge"][2],
        "TONES": json.dumps({k: theme[k] for k in ("accent", "scene", "solid", "solid_hi")}),
        "EM": 'font-family:"UIAccent"; font-weight:400; letter-spacing:-.01em;' if accent else "",
        "HEADLINES": "\n      ".join(title_html), "SCENES": "\n      ".join(scene_html),
        "CAPS": "\n      ".join(captions(plan, takeovers)), "JS": "\n      ".join(js),
        "GL": json.dumps(gl_scenes), "PALETTE": json.dumps(theme["palette"]),
        "SOLO": "\n      ".join(solo_html), "SOLO_TOP": str(SOLO["top"]), "SOLO_H": str(SOLO["height"]),
        "SOLO_ORIGIN": str(SOLO["origin_y"]), "SOLO_PIVOT": str(SOLO["origin_y"] - SOLO["top"]),
        "SHADE_TOP": str(SOLO["floor"] - 195), "SHADE_H": str(H - SOLO["floor"] + 195),
    }
    for key, value in fill.items():
        page = page.replace(f"%%{key}%%", value)
    left = re.findall(r"%%[A-Z_]+%%", page)
    if left:
        raise SystemExit(f"unfilled template fields: {left}")
    (dest / "index.html").write_text(page)
    (dest / "meta.json").write_text(json.dumps({"id": "comp", "name": "comp"}))
    (dest / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "assets"}, "media": {"autoProxy": True}}))
    print(f"composition ready: {dest}  ({plan.total:.1f}s, voice {plan.voice:.1f}s)")
    for window in plan.solo:
        print(f"  {window['start']:7.2f}-{window['end']:7.2f}  solo     {', '.join(window['ids'])}")
    for kind, items in (("headline", headlines), ("scene", scenes)):
        for item in items:
            print(f"  {item['start']:7.2f}-{item['end']:7.2f}  {kind:8s} {item.get('type', '')} {' '.join(item.get('lines', []))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--stage", choices=["cut", "redact", "face", "comp", "all"], default="all")
    parser.add_argument("--stills", help="with --stage face: times in seconds, e.g. 3,36,71")
    options = parser.parse_args()
    plan = Plan(options.project)
    if options.stills:
        if options.stage != "face":
            raise SystemExit("--stills goes with --stage face")
        face(plan, [float(t) for t in options.stills.split(",")])
        return
    for name, step in (("cut", cut), ("redact", redact), ("face", face), ("comp", comp)):
        if options.stage in (name, "all"):
            step(plan)


if __name__ == "__main__":
    main()
