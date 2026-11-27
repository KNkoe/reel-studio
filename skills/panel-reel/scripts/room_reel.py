"""One upright recording in, a full-frame video with the studio room behind the speaker out.

    python3 -I room_reel.py <take folder or video> <project dir> [--preview 2,12,24]
        [--window right|left] [--trim 0.035] [--look '{"skin": 0.7}'] [--room style.json]
        [--one-at-a-time]

Steps, all on this machine: measure the camera's angle from this recording (probe.swift,
fit_room.py), render the room to match (Blender), cut the speaker out (Robust Video Matting),
smooth the skin with a light colour touch and no relighting (studio.swift), then scan the result
for pieces of the speaker that blink in and out. Every recording is fitted afresh, so the camera
may move between recordings, but not during one. Renders are numbered; none is overwritten.
The room is rendered while the speaker is still being cut out, a few seconds behind it
("--one-at-a-time" waits for the whole cut-out first, which needs a little less memory).
A room style file recolours the room and lights the speaker to match:
{"swap": {"#6b5d55": "#494a4c"}, "look": {"match": 1.0, "ambient": [r, g, b],
"windowLight": [r, g, b], "lampLight": [r, g, b]}}, where "swap" names colours in studio_set.py.
It may also name your own room and make it move: "set": a Blender script used in place of
studio_set.py (same arguments), "animate": a script run as `animate.py <backdrop.png> <loop.mp4>`
(Python with numpy and Pillow) whose looping video then plays behind the speaker.
The sound is the recording's own, copied unchanged.
"""
import argparse
import hashlib
import json
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
W, H, FPS = 1080, 1920, 30
RATIO = "0.35"                       # cut-out working scale that stayed solid on upright frames
MODEL = Path.home() / ".cache" / "panel-reel" / "models" / "rvm_resnet50_fp32.onnx"
MODEL_URL = "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_resnet50_fp32.onnx"
LOOK = {"key": 0.0, "rim": 0.0, "relight": 0.0, "bloom": 0.03, "grain": 0.6, "skin": 0.8,
        "gold": 0.25, "selective": 0.1, "gate": False}
MODEL_SHA = "25db300fcb6ee27f941a1b52c97856e8d1f13c7f35817f81a612f89af0e8a85c"
# pinned so another machine renders the same way
PYTHON, PINS = "3.13", {"numpy": "2.5.5", "onnxruntime": "1.32.0", "pillow": "12.0.0"}
TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def run(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def uv_command(*cmd, extra=()):
    packages = [v for name in ("numpy", *extra) for v in ("--with", f"{name}=={PINS[name]}")]
    return [str(c) for c in ("uv", "run", "--no-project", "--python", PYTHON, *packages, "python", "-I", *cmd)]


def uv(*cmd, extra=()):
    return run(*uv_command(*cmd, extra=extra))


def ready_as_is(source: Path) -> bool:
    """Is the recording already what the room steps read: upright 1080x1920 H.264, BT.709, with its
    frames evenly spaced at 30 a second (a cut made by cut.py is)? Converting it again would only take
    minutes and lose a little quality."""
    def probe(*what):
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", *what, "-of", "json", str(source)],
                             capture_output=True, text=True, check=True).stdout
        return json.loads(out)
    video = probe("-show_streams")["streams"][0]
    wanted = {"codec_name": "h264", "width": W, "height": H, "pix_fmt": "yuv420p", "r_frame_rate": f"{FPS}/1",
              "color_space": "bt709", "color_primaries": "bt709", "color_transfer": "bt709", "color_range": "tv"}
    if any(video.get(key) != value for key, value in wanted.items()):
        return False
    if video.get("sample_aspect_ratio", "1:1") != "1:1" or any("rotation" in d for d in video.get("side_data_list", [])):
        return False
    times = sorted(float(p["pts_time"]) for p in probe("-show_entries", "packet=pts_time")["packets"])
    return bool(times) and all(abs(t - n / FPS) < 0.002 for n, t in enumerate(times))


def framing(trim: float) -> str:
    """Cut a strip off the bottom (the real table's edge) by zooming, keeping the top."""
    if trim <= 0:
        return "null"
    w, h = (int(round(v / (1 - trim) / 2)) * 2 for v in (W, H))
    return f"scale={w}:{h}:flags=lanczos:in_color_matrix=bt709:out_color_matrix=bt709,crop={W}:{H}:{(w - W) // 2}:0"


def scan(face: str, final: str, trim: float):
    """Frames where the finished video changes although the footage does not: a flickering cut-out.
    Reads both videos a few seconds at a time, so a long video does not fill the memory."""
    import numpy as np
    w, h, at_once = 360, 640, 150

    def pieces(path, first="null"):
        reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-vf",
                                   f"{first},scale={w}:{h}:flags=area,format=gray", "-f", "rawvideo", "-"],
                                  stdout=subprocess.PIPE)
        while True:
            raw = reader.stdout.read(w * h * at_once)
            if len(raw) >= w * h:
                yield np.frombuffer(raw, np.uint8, len(raw) // (w * h) * w * h).reshape(-1, h, w).astype(np.int16)
            if len(raw) < w * h * at_once:
                break
        reader.stdout.close()
        if reader.wait():
            raise SystemExit(f"the flicker scan could not read {path}")

    counts, last = [], None
    for before, after in zip(pieces(face, framing(trim)), pieces(final)):
        n = min(len(before), len(after))
        before, after = before[:n], after[:n]
        if last is not None:                     # compare across the join between two pieces too
            before, after = np.concatenate((last[0], before)), np.concatenate((last[1], after))
        counts.append(((np.abs(np.diff(after, axis=0)) > 22) & (np.abs(np.diff(before, axis=0)) < 9)).sum((1, 2)))
        last = (before[-1:].copy(), after[-1:].copy())
    bad = np.concatenate(counts)
    usual = max(float(np.median(bad)), 1)
    suspects = [int(i) + 1 for i in np.argsort(bad)[::-1] if bad[i] > max(1200, usual * 15)][:12]
    if suspects:
        print("LOOK AT these frames, something blinks: " + ", ".join(f"{i} ({i / 30:.1f}s)" for i in sorted(suspects)))
    else:
        print(f"flicker scan: nothing stands out (worst frame {int(bad.max())} changed pixels, usual {usual:.0f})")


def render_room(work: Path, face: Path, source: Path, settings: Path, partial: Path, trim: float, cutout=None):
    """Render the room and encode it. "cutout" is the cut-out still running beside it, if any."""
    graded = subprocess.Popen([str(work / "studio_bin"), str(face), str(settings)], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
    encode = None
    try:
        if cutout:                     # if either side fails, stop the other instead of waiting for it
            threading.Thread(target=lambda: cutout.wait() and graded.terminate(), daemon=True).start()
        encode = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS),
             "-i", "pipe:0", "-i", str(source), "-map", "0:v", "-map", "1:a?", "-vf",
             f"scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,{framing(trim)},format=yuv420p", *TAGS,
             "-c:v", "libx264", "-crf", "17", "-preset", "medium", "-g", str(FPS), "-c:a", "copy",
             "-movflags", "+faststart", str(partial)], stdin=graded.stdout)
        graded.stdout.close()
        if graded.wait() or encode.returncode:
            if cutout and cutout.poll():
                raise SystemExit("the cut-out failed (its message is above), so the room render was stopped")
            raise SystemExit("the render failed")
    finally:
        if graded.poll() is None:
            graded.kill()


def join_parts(listing: Path, out: Path):
    """Put the outline's parts together without encoding them again."""
    names = [line.split(",")[0] for line in listing.read_text().splitlines() if line]
    order = listing.with_suffix(".txt")
    order.write_text("".join(f"file '{name}'\n" for name in names))
    partial = out.with_suffix(".partial.mp4")
    run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", order, "-c", "copy", partial)
    partial.replace(out)


def count_frames(path: Path) -> int:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                          "stream=nb_read_packets", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip().rstrip(","))


def main():
    # being told to stop must also stop the programs started here
    signal.signal(signal.SIGTERM, lambda *_: sys.exit("stopped"))
    if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        return scan(sys.argv[2], sys.argv[3], float(sys.argv[4]))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source")
    parser.add_argument("project")
    parser.add_argument("--preview", help="seconds to preview as stills; renders no video")
    parser.add_argument("--window", choices=("right", "left"), help="override the side chosen from the recording")
    parser.add_argument("--trim", type=float, help="share of the height cut from the bottom (default: from the table)")
    parser.add_argument("--look", default="{}", help="JSON that overrides the skin and colour settings")
    parser.add_argument("--room", help="JSON file with the room's colours (swap) and the matching light (look)")
    parser.add_argument("--one-at-a-time", action="store_true", help="finish the cut-out before rendering the room")
    options = parser.parse_args()
    style = json.loads(Path(options.room).expanduser().read_text()) if options.room else {}

    source = Path(options.source).expanduser().resolve()
    if source.is_dir():
        source = source / "camera.mov"
    if not source.is_file():
        raise SystemExit(f"no recording at {source}")
    work = Path(options.project).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    blender = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
    for needed in ("ffmpeg", "uv", "swiftc", blender):
        if not (shutil.which(needed) or Path(needed).exists()):
            raise SystemExit(f"missing {needed}")

    stamp = {"source": str(source), "size": source.stat().st_size, "time": source.stat().st_mtime_ns}
    record, face = work / "source.json", work / "face.mp4"
    if not face.exists() or not record.exists() or json.loads(record.read_text()) != stamp:
        for old in (face, work / "outline.mp4"):
            old.unlink(missing_ok=True)       # "face" may be a link to a recording: remove it, never write into it
        if ready_as_is(source):
            face.symlink_to(source)
        else:
            run("ffmpeg", "-v", "error", "-y", "-i", source, "-an", "-vf", f"scale={W}:{H}:flags=lanczos,fps={FPS}",
                "-c:v", "libx264", "-crf", "10", "-pix_fmt", "yuv420p", *TAGS, face)
        record.write_text(json.dumps(stamp))
    for name in ("probe", "studio"):
        run("swiftc", "-O", "-suppress-warnings", HERE / f"{name}.swift", "-o", work / f"{name}_bin")

    print("measuring the camera's angle", flush=True)
    probe = work / "probe"
    probe.mkdir(exist_ok=True)
    run(work / "probe_bin", source, probe, 12, stderr=subprocess.DEVNULL)
    room = work / "set_options.json"
    uv(HERE / "fit_room.py", probe, room, "--overlay", probe / "check.raw",
       *(["--window", options.window] if options.window else []))
    run("ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "540x960", "-i",
        probe / "check.raw", "-frames:v", "1", work / "angle-check.png")

    if style.get("swap"):
        room.write_text(json.dumps({**json.loads(room.read_text()), "swap": style["swap"]}, indent=1))
    print("rendering the room (about a minute)", flush=True)
    backdrop = work / "backdrop.png"
    own = {name: Path(style[name]).expanduser().resolve() for name in ("set", "animate") if style.get(name)}
    for name, script in own.items():
        if not script.is_file():
            raise SystemExit(f"no {name} script named by the room style: {script}")
    run(blender, "--background", "--factory-startup", "--python-exit-code", "1", "--python",
        own.get("set", HERE / "studio_set.py"), "--", backdrop, room, stdout=subprocess.DEVNULL)
    fitted = json.loads(room.read_text())
    trim = options.trim if options.trim is not None else round(min(max(1 - fitted["table_top"], 0.035), 0.08), 3)
    if "animate" in own:
        print("making the background move", flush=True)
        moving = work / "backdrop.mp4"
        uv(own["animate"], backdrop, moving, extra=("pillow",))
        backdrop = moving
    look = {**LOOK, **style.get("look", {}), **json.loads(options.look), "backdrop": str(backdrop),
            "windowRight": bool(fitted.get("mirror", False))}
    settings = work / "studio.json"

    if options.preview:
        settings.write_text(json.dumps({**look, "matte": ""}, indent=1))
        shots = work / "preview"
        shots.mkdir(exist_ok=True)
        frames = [round(float(t) * FPS) for t in options.preview.split(",")]
        run(work / "studio_bin", face, settings, "--stills", ",".join(map(str, frames)), shots, stderr=subprocess.DEVNULL)
        for frame in frames:
            run("ffmpeg", "-v", "error", "-y", "-i", shots / f"studio_{frame}.png", "-vf",
                f"format=rgb24,{framing(trim)}", "-frames:v", "1", shots / f"preview_{frame}.png")
        print(f"preview stills in {shots} (rough cut-out: judge edges on the video). Angle check: {work / 'angle-check.png'}")
        return

    outline = work / "outline.mp4"
    if not outline.exists():
        if not MODEL.exists():
            print("downloading the cut-out model once (107 MB, free)")
            MODEL.parent.mkdir(parents=True, exist_ok=True)
            run("curl", "-fL", "--retry", "3", "-sS", "-o", MODEL.with_suffix(".partial"), MODEL_URL)
            MODEL.with_suffix(".partial").replace(MODEL)
        if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA:
            raise SystemExit(f"the cut-out model at {MODEL} is not the expected file: delete it and run again")

    number = 1
    while (work / f"room-v{number}.mp4").exists():
        number += 1
    final, partial = work / f"room-v{number}.mp4", work / "room.partial.mp4"

    if outline.exists() or options.one_at_a_time:
        if not outline.exists():
            print("cutting out the speaker (about 5 frames a second)", flush=True)
            making = work / "outline.partial.mp4"
            uv(HERE / "rvm_matte.py", MODEL, face, making, "--ratio", RATIO, extra=("onnxruntime",))
            making.replace(outline)
        settings.write_text(json.dumps({**look, "matte": str(outline)}, indent=1))
        print(f"rendering {final.name}", flush=True)
        render_room(work, face, source, settings, partial, trim)
    else:
        parts = work / "outline_parts"
        shutil.rmtree(parts, ignore_errors=True)
        parts.mkdir()
        listing = parts / "outline.csv"
        listing.write_text("")
        settings.write_text(json.dumps({**look, "matte": str(listing)}, indent=1))
        print(f"cutting out the speaker and rendering {final.name} behind it", flush=True)
        cutout = subprocess.Popen(uv_command(HERE / "rvm_matte.py", MODEL, face, listing, "--ratio", RATIO,
                                             extra=("onnxruntime",)))

        def finished():
            if cutout.wait() == 0:
                Path(f"{listing}.done").touch()
        watcher = threading.Thread(target=finished, daemon=True)
        watcher.start()
        try:
            render_room(work, face, source, settings, partial, trim, cutout)
            if cutout.wait():
                raise SystemExit("the cut-out failed (its message is above)")
            watcher.join()
        finally:
            if cutout.poll() is None:
                cutout.terminate()
        join_parts(listing, outline)
        if count_frames(outline) != count_frames(face):
            outline.unlink()
            raise SystemExit("the joined outline does not match the footage frame for frame: "
                             "run again with --one-at-a-time")
        shutil.rmtree(parts)
        settings.write_text(json.dumps({**look, "matte": str(outline)}, indent=1))
    if count_frames(partial) != count_frames(face):
        raise SystemExit(f"the room render has {count_frames(partial)} frames and the footage {count_frames(face)}")
    partial.replace(final)
    uv(Path(__file__).resolve(), "--scan", face, final, trim)
    print(f"done: {final}  (bottom trim {trim:.1%})")


if __name__ == "__main__":
    main()
