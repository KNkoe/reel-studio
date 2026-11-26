"""Cut a talk-only recording from the ranges in <project>/reel.json.

    python3 -I cut.py <project>            transcribe if needed, cut picture and voice
    python3 -I cut.py <project> --plan     only the edit list and word timings (no video work)

reel.json "cut": {"take": "sources/take-main", "keep": [["name", in, out], ...],
                  "long": 0.62, "leave": 0.17, "tail": 2.4}
Times are the microphone's. A pause longer than "long" inside a range keeps "leave" seconds on
each side; "tail" is how long the last picture is held. Writes work/edl.json,
work/words_edit.json, work/face_cut.mp4 and work/voice.wav. A take is a Clapless folder
(camera.mov, mic.m4a, take.json).
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE
FPS, RATE = 30, 48000
TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


def ffmpeg(*cmd):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, cmd)], check=True)


def silences(mic):
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mic), "-af", "silencedetect=noise=-40dB:d=0.28",
                          "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
    starts = [float(v) for v in re.findall(r"silence_start: ([0-9.]+)", log)]
    ends = [float(v) for v in re.findall(r"silence_end: ([0-9.]+)", log)]
    return list(zip(starts, ends))


def segments(settings, quiet):
    long, leave = settings.get("long", 0.62), settings.get("leave", 0.17)
    out, frame = [], 0
    for name, a, b in settings["keep"]:
        pieces, start = [], a
        for s, e in quiet:
            if e - s >= long and s > start + 0.3 and e < b - 0.3:
                pieces.append((start, s + leave))
                start = e - leave
        pieces.append((start, b))
        for n, (p, q) in enumerate(pieces):
            frames = round((q - p) * FPS)
            out.append({"id": f"{name}_{n}", "key": name, "in": round(p, 3), "frames": frames,
                        "start": frame / FPS, "dur": frames / FPS})
            frame += frames
    return out, frame / FPS


def edit_words(segs, words):
    """Every kept word on the edit's clock, with its time in the recording last."""
    timed = []
    for a, b, text in words:
        overlap, s = max(((min(b, s["in"] + s["dur"]) - max(a, s["in"]), s) for s in segs), key=lambda p: p[0])
        if overlap < 0.08 and not s["in"] <= (a + b) / 2 < s["in"] + s["dur"]:
            continue
        timed.append([round(s["start"] + max(0.0, a - s["in"]), 2),
                      round(s["start"] + min(s["dur"], b - s["in"]), 2), text, a])
    return timed


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", type=Path)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--locale", default="en-US")
    options = parser.parse_args()
    project = options.project.expanduser().resolve()
    settings = json.loads((project / "reel.json").read_text())["cut"]
    work = project / "work"
    work.mkdir(exist_ok=True)
    take = project / settings["take"]
    mic, words_file = work / "mic_main.wav", work / "words_main.json"
    if not mic.exists():      # keeps the microphone's small start delay
        ffmpeg("-i", take / "mic.m4a", "-af", f"aresample={RATE}:async=1:first_pts=0", "-ac", "1", mic)
    if not words_file.exists():
        binary, small = work / "transcribe", work / "a16.wav"
        subprocess.run(["swiftc", "-O", str(SCRIPTS / "transcribe.swift"), "-o", str(binary)], check=True)
        ffmpeg("-i", mic, "-ar", "16000", small)
        subprocess.run([str(binary), str(small), str(words_file), options.locale], check=True)
    if not settings.get("keep"):
        raise SystemExit(f'transcript in {words_file}. Now list what to keep in reel.json "cut" "keep".')
    segs, voice = segments(settings, silences(mic))
    total = voice + settings.get("tail", 2.4)
    (work / "edl.json").write_text(json.dumps({"segments": segs, "voice": voice, "total": total}, indent=1))
    (work / "words_edit.json").write_text(json.dumps(edit_words(segs, json.loads(words_file.read_text()))))
    print(f"{len(segs)} pieces, voice {voice:.2f}s, total {total:.2f}s")
    for name, _, _ in settings["keep"]:
        mine = [s for s in segs if s["key"] == name]
        print(f"  {mine[0]['start']:7.2f}-{mine[-1]['start'] + mine[-1]['dur']:7.2f}  {name}")
    if options.plan:
        return
    sync = json.loads((take / "take.json").read_text())["sync"]
    if not sync.get("matchedBySound"):
        raise SystemExit("this take's camera and microphone were not matched by sound: do not edit it on a guess")
    offset, drift = sync["videoOffset"], sync["videoDrift"]
    out = work / "cut"
    out.mkdir(exist_ok=True)
    for s in segs:
        camera = s["in"] + offset + drift * s["in"]
        ffmpeg("-hwaccel", "videotoolbox", "-ss", f"{camera:.4f}", "-t", s["dur"] + 0.5, "-i", take / "camera.mov",
               "-an", "-vf", f"scale=1080:1920:flags=lanczos,fps={FPS},tpad=stop_mode=clone:stop_duration=1,setsar=1",
               "-frames:v", s["frames"], "-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p",
               *TAGS, out / f"{s['id']}.mp4")
        samples = s["frames"] * RATE // FPS
        ffmpeg("-ss", s["in"], "-t", s["dur"] + 0.5, "-i", mic, "-af",
               f"aresample={RATE},apad,atrim=end_sample={samples},afade=t=in:d=0.012,"
               f"afade=t=out:st={s['dur'] - 0.012:.4f}:d=0.012", "-c:a", "pcm_s16le", out / f"{s['id']}.wav")
    for ext, name in (("mp4", "face_cut_silent.mp4"), ("wav", "voice_raw.wav")):
        listing = out / f"{ext}.txt"
        listing.write_text("".join(f"file '{s['id']}.{ext}'\n" for s in segs))
        ffmpeg("-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", work / name)
    clean = "aformat=channel_layouts=stereo,highpass=f=75"
    target = "loudnorm=I=-14:TP=-1.5:LRA=11"
    first = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(work / "voice_raw.wav"), "-af",
                            f"{clean},{target}:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True, check=True).stderr
    m = json.loads(first[first.rindex("{"):first.rindex("}") + 1])
    ffmpeg("-i", work / "voice_raw.wav", "-af",
           f"{clean},{target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
           f"measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true", "-ar", RATE,
           work / "voice.wav")
    ffmpeg("-i", work / "face_cut_silent.mp4", "-i", work / "voice.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "192k", work / "face_cut.mp4")
    print("cut ready:", work / "face_cut.mp4")


if __name__ == "__main__":
    main()
