"""Render a project's 3D scenes.

    python3 -I render.py <project> --preview [scene ...]     movement preview: do this first
    python3 -I render.py <project> [scene ...]               full render (resumes where it stopped)
    python3 -I render.py <project> --stills scene:40,44      chosen moments at full size
    python3 -I render.py <project> --pack                    shrink finished frames (disk cleanup)

--preview draws two moments a second at a third of the size and lays each scene out on one sheet
(work/preview/<scene>.jpg, left to right, top to bottom). Look for empty stretches, text over
pictures, things leaving the frame and anything crude, and fix them before the full render.

--scale 80 draws smaller and lets the compositor enlarge it. A scene is drawn again when its own
code, the shared part of scenes.py, the toolkit or --scale changes.
"""
import argparse
import hashlib
import re
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FPS = 30
BLOCK = re.compile(r'^@scene\("(\w+)", ([0-9.]+), ([0-9.]+), (?:SPLIT|FULL)\)', re.M)
TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "pc"]


def ffmpeg(*cmd, **kw):
    return subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, cmd)], check=True, **kw)


def scene_list(path: Path):
    """name -> (frames, stamp) read from the scene file without starting Blender."""
    text = path.read_text()
    found = list(BLOCK.finditer(text))
    if not found:
        raise SystemExit(f'no @scene("name", start, end, SPLIT|FULL) in {path}')
    ends = [m.start() for m in found[1:]] + [len(text)]
    shared = hashlib.sha256(text[:found[0].start()].encode())
    for tool in ("kit.py", "props.py", "geo.py", "run.py"):
        shared.update((HERE / tool).read_bytes())
    out = {}
    for match, end in zip(found, ends):
        name, a, b = match.group(1), float(match.group(2)), float(match.group(3))
        stamp = shared.copy()
        stamp.update(text[match.start():end].strip().encode())
        out[name] = (max(1, round((b - a) * FPS)), stamp.hexdigest()[:16])
    return out


def blender():
    found = shutil.which("blender") or "/Applications/Blender.app/Contents/MacOS/Blender"
    if not Path(found).exists():
        raise SystemExit("3D scenes need Blender (brew install --cask blender)")
    return found


def draw(project, name, out, log, *extra):
    cmd = [blender(), "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(HERE / "run.py"),
           "--", str(project / "scenes.py"), name, str(out), *map(str, extra)]
    with open(log, "w") as record:
        done = subprocess.run(cmd, stdout=record, stderr=subprocess.STDOUT)
    if done.returncode:
        tail = [l for l in Path(log).read_text().splitlines() if re.search(r'Error|Traceback|File "', l)]
        print(f"{name} FAILED (full log: {log})\n  " + "\n  ".join(tail[-8:]))
        return False
    return True


def sheet(folder: Path, out: Path):
    frames = sorted(folder.glob("[0-9]*.png"))
    listing = folder / "frames.txt"
    listing.write_text("".join(f"file '{f.name}'\nduration 1\n" for f in frames))
    columns = 8
    rows = -(-len(frames) // columns)
    ffmpeg("-f", "concat", "-safe", "0", "-i", listing, "-vf",
           f"scale=240:-2,pad=iw+4:ih+4:2:2:color=red,tile={columns}x{rows}", "-frames:v", "1", "-q:v", "3", out)


def pack(project, name, frames):
    """Replace a finished scene's pictures with one near-lossless video, after checking it."""
    folder, video = project / "work" / "3d" / name, project / "work" / "3d" / f"{name}.mp4"
    have = sorted(folder.glob("[0-9]*.png"))
    if len(have) != frames:
        print(f"{name}: {len(have)} of {frames} frames, left as it is")
        return
    partial = video.with_suffix(".partial.mp4")
    ffmpeg("-framerate", FPS, "-i", folder / "%05d.png", "-vf",
           "scale=out_color_matrix=bt709:out_range=pc,format=yuv444p", *TAGS, "-c:v", "libx264", "-preset", "medium",
           "-crf", "10", "-g", FPS, partial)
    check = subprocess.run(
        ["ffmpeg", "-hide_banner", "-framerate", str(FPS), "-i", str(folder / "%05d.png"), "-i", str(partial), "-lavfi",
         "[0]format=rgb24[a];[1]scale=in_color_matrix=bt709:in_range=pc,format=rgb24[b];[a][b]psnr", "-f", "null", "-"],
        capture_output=True, text=True, check=True).stderr
    found = re.search(r"average:([0-9.]+|inf) min:([0-9.]+|inf)", check)
    count = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v", "-show_entries",
                            "stream=nb_read_packets", "-of", "csv=p=0", str(partial)],
                           capture_output=True, text=True, check=True).stdout.strip()
    if not found or float(found.group(2)) < 40 or int(count) != frames:
        partial.unlink()
        print(f"{name}: the packed copy did not match closely enough; frames kept")
        return
    partial.replace(video)
    before = sum(f.stat().st_size for f in have)
    shutil.rmtree(folder)
    print(f"{name}: {before / 1e6:.0f} MB -> {video.stat().st_size / 1e6:.0f} MB "
          f"(closeness {float(found.group(1)):.1f} dB average, {float(found.group(2)):.1f} dB worst)")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--stills", action="append", help="scene:time,time")
    parser.add_argument("--every", type=int, default=15, help="preview: one frame in this many")
    parser.add_argument("--scale", type=int, help="picture size in percent (preview 33, otherwise 100)")
    parser.add_argument("--pack", action="store_true")
    options = parser.parse_args()
    project = options.project.expanduser().resolve()
    scenes = scene_list(project / "scenes.py")
    unknown = set(options.names) - set(scenes)
    if unknown:
        raise SystemExit(f"no scene called {', '.join(sorted(unknown))}; there are: {', '.join(scenes)}")
    names = options.names or list(scenes)
    work = project / "work"
    logs = work / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if options.pack:
        for name in names:
            if (work / "3d" / name).is_dir():
                pack(project, name, scenes[name][0])
        return
    subprocess.run(["python3", "-I", str(HERE / "assets.py")], check=True, stdout=subprocess.DEVNULL)
    if options.stills:
        for item in options.stills:
            name, times = item.split(":")
            out = work / "stills" / name
            if draw(project, name, out, logs / f"{name}.log", "--stills", times, "--scale", options.scale or 100):
                print("stills in", out)
        return
    failed, began = [], time.time()
    for name in names:
        frames, stamp = scenes[name]
        start = time.time()
        if options.preview:
            out = work / "preview" / name
            shutil.rmtree(out, ignore_errors=True)
            if draw(project, name, out, logs / f"{name}.log", "--every", options.every, "--scale", options.scale or 33):
                sheet(out, work / "preview" / f"{name}.jpg")
                print(f"{name}: preview sheet in {time.time() - start:.0f}s", flush=True)
            else:
                failed.append(name)
            continue
        scale = options.scale or 100
        folder, video = work / "3d" / name, work / "3d" / f"{name}.mp4"
        record = work / "3d" / f"{name}.stamp"
        stamp = f"{stamp}-{scale}"
        current = record.exists() and record.read_text() == stamp
        if current and (video.exists() or len(list(folder.glob("[0-9]*.png"))) == frames):
            print(f"{name}: already rendered")
            continue
        if not current:           # frames from other code or another size must not be mixed in
            shutil.rmtree(folder, ignore_errors=True)
            video.unlink(missing_ok=True)
            record.parent.mkdir(parents=True, exist_ok=True)
            record.write_text(stamp)
        if draw(project, name, folder, logs / f"{name}.log", "--scale", scale):
            print(f"{name}: {len(list(folder.glob('[0-9]*.png')))} frames in {time.time() - start:.0f}s", flush=True)
        else:
            failed.append(name)
    print(f"finished in {(time.time() - began) / 60:.1f} minutes")
    if failed:
        raise SystemExit(f"failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
