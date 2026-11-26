"""Put the reel together: full-frame speaker, 3D scenes above the face card, headlines and captions.

    uv run --no-project --python 3.13 --with numpy==2.5.5 --with pillow==12.0.0 python -I compose.py <project>
        [--stills 3,15,40]      review frames into work/look/

Reads <project>/reel.json, scenes.py (scene times) and work/: edl.json, words_edit.json, voice.wav,
room/room-v1.mp4 (or the newest room-vN), room/outline.mp4, room/set_options.json and 3d/.
reel.json: {"name": "my-reel",
            "headlines": [[start, end, ["LINE ONE", "LINE TWO"]]],   big words over the speaker
            "fixes": {"3.90": "Word", "12.78": null},   misheard words by time in the recording
            "lifts": {"scene": 120},                    scenes whose lowest words need more room
            "accent": "#f86923"}                        colour of a headline's second line
Renders are numbered in renders/; none is overwritten.
"""
import argparse
import json
import math
import os
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(os.environ.get("REEL_ASSETS") or Path.home() / ".cache" / "panel-reel" / "assets")
FONTS = ASSETS / "fonts"
W, H, FPS = 1080, 1920, 30
CARD_TOP, RADIUS = 1330, 200      # the face card; edge to edge, curve deep enough to survive side crops
FACE_DROP = 620                   # how far the camera picture moves down in the split layout
SET_LIFT = 80                     # the 3D picture moves up so captions fit between it and the head
CAP_Y = {"face": 1390, "split": 1006, "full": 1425}
GROUND = (11, 13, 20)
MOVE = 0.34                       # seconds for the speaker to settle into the card
INK, WHITE = (35, 39, 51), (255, 255, 255)

TAGS = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]


class Project:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.work = self.root / "work"
        self.settings = json.loads((self.root / "reel.json").read_text())
        self.name = self.settings.get("name", self.root.name)
        self.headlines = [(a, b, lines) for a, b, lines in self.settings.get("headlines", [])]
        self.fixes = {float(k): v for k, v in self.settings.get("fixes", {}).items()}
        self.lifts = self.settings.get("lifts", {})
        accent = self.settings.get("accent", "#f86923").lstrip("#")
        self.accent = tuple(int(accent[i:i + 2], 16) for i in (0, 2, 4))
        for a, b, lines in self.headlines:
            if b - a > 4.05 or len(lines) > 2:
                raise SystemExit(f"headline {lines}: at most two lines, and no longer than 4 seconds")

    def scenes(self):
        text = (self.root / "scenes.py").read_text()
        found = re.findall(r'^@scene\("(\w+)", ([0-9.]+), ([0-9.]+), (SPLIT|FULL)\)', text, re.M)
        return [{"name": n, "start": float(a), "end": float(b), "kind": k.lower()} for n, a, b, k in found]


def font(name, size):
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


def captions(project, voice):
    words = []
    unused = dict(project.fixes)
    for start, end, text, src in json.loads((project.work / "words_edit.json").read_text()):
        key = next((k for k in project.fixes if abs(k - src) < 0.011), None)
        if key is not None:
            unused.pop(key, None)
            text = project.fixes[key]
        if text is None:
            continue
        shown = re.sub(r"[.,?!\"]+$", "", text)
        if not shown or shown.lower() in ("um", "uh", "ah", "hmm", "#um", "#ah"):
            continue
        words.append((start, end, shown, bool(re.search(r"[.,?!]$", text))))
    if unused:
        print("fixes that matched no kept word:", sorted(unused))
    chunks, current, size = [], [], 0
    for start, end, text, stop in words:
        if current and (size + len(text) > 17 or start - current[-1][1] > 0.8):
            chunks.append(current)
            current, size = [], 0
        current.append((start, end, text))
        size += len(text) + 1
        if len(current) >= 3 or stop:
            chunks.append(current)
            current, size = [], 0
    if current:
        chunks.append(current)
    out = []
    for i, chunk in enumerate(chunks):
        start = max(0.0, chunk[0][0] - 0.04)
        limit = chunks[i + 1][0][0] - 0.04 if i + 1 < len(chunks) else voice
        end = max(start + 0.12, min(chunk[-1][1] + 0.3, limit))
        out.append((start, end, " ".join(w[2] for w in chunk).upper()))
    return out


def caption_picture(text):
    face = font("Roboto-900", 60)
    while face.getlength(text) > 900:
        face = font("Roboto-900", face.size - 2)
    width = int(face.getlength(text)) + 56
    pic = Image.new("RGBA", (width + 40, 130), (0, 0, 0, 0))
    shadow = Image.new("RGBA", pic.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((20, 28, 20 + width, 116), 20, fill=(0, 0, 0, 115))
    pic.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(9)))
    draw = ImageDraw.Draw(pic)
    draw.rounded_rectangle((20, 20, 20 + width, 108), 20, fill=(*WHITE, 255))
    draw.text((20 + width / 2, 65), text, font=face, fill=(*INK, 255), anchor="mm")
    return pic


def headline_picture(lines, accent):
    size = 112
    while max(font("RobotoSlab-900", size).getlength(line) for line in lines) > 960:
        size -= 2
    face = font("RobotoSlab-900", size)
    step = int(size * 1.08)
    pic = Image.new("RGBA", (W, step * len(lines) + 80), (0, 0, 0, 0))
    shadow = Image.new("RGBA", pic.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    for i, line in enumerate(lines):
        sd.text((W / 2, 40 + step * i + step / 2 + 6), line, font=face, fill=(0, 0, 0, 215), anchor="mm",
                stroke_width=6, stroke_fill=(0, 0, 0, 215))
    pic.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    draw = ImageDraw.Draw(pic)
    for i, line in enumerate(lines):
        colour = accent if i == 1 else WHITE
        draw.text((W / 2, 40 + step * i + step / 2), line, font=face, fill=(*colour, 255), anchor="mm")
    return pic


def card_mask(top=CARD_TOP, radius=RADIUS):
    big = Image.new("L", (W * 2, H * 2), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, top * 2, W * 2 - 1, (H + RADIUS) * 2), radius * 2, fill=255)
    return np.asarray(big.resize((W, H), Image.LANCZOS), np.float32) / 255


class Stream:
    """Frames of a video, one after another."""
    def __init__(self, path, channels, vf=None, start=0):
        pix = "rgb24" if channels == 3 else "gray"
        chain = [f for f in (vf, "scale=in_color_matrix=bt709:in_range=tv" if channels == 3 else None,
                             f"format={pix}") if f]
        seek = ["-ss", f"{start / FPS:.5f}"] if start else []
        self.proc = subprocess.Popen(["ffmpeg", "-v", "error", *seek, "-i", str(path), "-vf", ",".join(chain),
                                      "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
        self.shape = (H, W, 3) if channels == 3 else (H, W)
        self.size = int(np.prod(self.shape))
        self.last = None

    def read(self):
        raw = self.proc.stdout.read(self.size)
        if len(raw) == self.size:
            self.last = np.frombuffer(raw, np.uint8).reshape(self.shape)
        if self.last is None:
            raise SystemExit("a video gave no frames")
        return self.last

    def close(self):
        self.proc.kill()


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def framing_marks(project, edl, plan):
    """Where the framing of the full-frame speaker changes: every cut, and long takes every few seconds."""
    marks = []
    words = json.loads((project.work / "words_edit.json").read_text())
    ends = [w[1] for w in words if w[2][-1:] in ".?!,"]
    for s in edl["segments"]:
        marks.append(s["start"])
        t = s["start"]
        while s["start"] + s["dur"] - t > 5.5:
            near = [e for e in ends if t + 2.8 < e < min(t + 5.5, s["start"] + s["dur"] - 1.5)]
            t = near[0] if near else t + 4.2
            marks.append(t)
    for sc in plan:
        marks.append(sc["end"])
    return sorted(set(round(m, 3) for m in marks))


SIZES = (1.0, 1.10, 1.045, 1.0, 1.085, 1.03)


def speaker_view(t, marks, headline_on):
    """How the full-frame speaker is framed at time t: (scale, pixels lowered)."""
    index = max(0, sum(1 for m in marks if m <= t + 1e-6) - 1)
    since = t - marks[index]
    if headline_on:        # stay back so big text clears the head
        return 1.0 + 0.003 * min(since, 6.0), 44
    return SIZES[index % len(SIZES)] + 0.006 * min(since, 6.0), 0


def reframe(frame, scale, lowered):
    ox, oy = W / 2, 0.40 * H
    box = (ox - ox / scale, oy - oy / scale, ox + (W - ox) / scale, oy + (H - oy) / scale)
    pic = Image.fromarray(frame).resize((W, H), Image.BICUBIC, box=box)
    lowered = int(round(lowered))
    if lowered:
        canvas = pic.copy()
        canvas.paste(pic.crop((0, 0, W, H - lowered)), (0, lowered))
        canvas.paste(pic.crop((0, 0, W, 2)).resize((W, lowered)), (0, 0))
        pic = canvas
    return np.asarray(pic)


class Pictures:
    """A scene's 3D frames: numbered pictures, or the packed video left after a disk cleanup."""
    def __init__(self, folder, scene):
        self.folder, self.video = folder / scene["name"], folder / f"{scene['name']}.mp4"
        self.total = max(1, round((scene["end"] - scene["start"]) * FPS))
        self.proc, self.at, self.last = None, -1, None

    def get(self, index):
        path = self.folder / f"{index:05d}.png"
        if path.exists():
            picture = Image.open(path).convert("RGB")
        elif self.video.exists():
            picture = self.from_video(index)
        else:
            raise SystemExit(f"missing 3D frame {path} (run render.py)")
        if picture.width != W:           # rendered smaller to save time
            picture = picture.resize((W, round(picture.height * W / picture.width / 2) * 2), Image.LANCZOS)
        return picture

    def from_video(self, index):
        if index == self.at:
            return self.last
        if self.proc is None or index < self.at:
            if self.proc:
                self.proc.kill()
            probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height", "-of", "csv=p=0", str(self.video)],
                                   capture_output=True, text=True, check=True).stdout.strip().split(",")
            self.size = int(probe[0]), int(probe[1])
            seek = ["-ss", f"{index / FPS:.5f}"] if index else []
            self.proc = subprocess.Popen(["ffmpeg", "-v", "error", *seek, "-i", str(self.video), "-vf",
                                          "scale=in_color_matrix=bt709:in_range=pc,format=rgb24", "-f", "rawvideo", "-"],
                                         stdout=subprocess.PIPE)
            self.at = index - 1
        length = self.size[0] * self.size[1] * 3
        while self.at < index:
            raw = self.proc.stdout.read(length)
            if len(raw) != length:
                raise SystemExit(f"{self.video} ends before frame {index}")
            self.at += 1
        self.last = Image.frombytes("RGB", self.size, raw)
        return self.last


class Reel:
    def __init__(self, project):
        self.project = project
        self.edl = json.loads((project.work / "edl.json").read_text())
        self.plan = project.scenes()
        self.pictures = {}
        self.card = card_mask()
        self.caps = [(a, b, caption_picture(t), t) for a, b, t in captions(project, self.edl["voice"])]
        self.heads = [(a, b, headline_picture(lines, project.accent)) for a, b, lines in project.headlines]
        self.marks = framing_marks(project, self.edl, self.plan)
        # a soft shadow just outside the card, so it reads as lying in front of the 3D picture
        cast = Image.fromarray((self.card * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(28))
        self.shadow = np.roll(np.asarray(cast, np.float32) / 255, -16, axis=0)
        self.shadow[-16:] = 0
        # the 3D picture melts into plain ground before it ends, so no edge shows beside the card corners
        yy = np.arange(H, dtype=np.float32)[:, None, None]
        self.melt = np.clip((yy - 1180) / 215, 0, 1) ** 1.4

    def close(self):
        """Stop the readers of packed scenes, so they do not complain when the program ends."""
        for source in self.pictures.values():
            if source.proc:
                source.proc.kill()
                source.proc.wait()

    def scene_at(self, t):
        for sc in self.plan:
            if sc["start"] - 1e-6 <= t < sc["end"] - 1e-6:
                return sc
        return None

    def set_picture(self, sc, t):
        source = self.pictures.get(sc["name"])
        if source is None:
            source = self.pictures[sc["name"]] = Pictures(self.project.work / "3d", sc)
        return source.get(min(source.total - 1, max(0, round((t - sc["start"]) * FPS))))

    def split(self, sc, t, frame, matte, k=1.0, view=(1.0, 0)):
        """The 3D picture with the speaker's card under it. k runs 0..1 as the full-frame speaker
        settles down into the card (and back), so the two layouts never ghost over each other."""
        base = Image.new("RGB", (W, H), GROUND)
        base.paste(self.set_picture(sc, t), (0, -self.project.lifts.get(sc["name"], SET_LIFT)))
        out = np.asarray(base, np.float32)
        out = out * (1 - self.melt) + np.array(GROUND, np.float32) * self.melt
        if k < 0.999:       # still travelling: ease the camera framing out as it goes
            scale, lowered = 1 + (view[0] - 1) * (1 - k), view[1] * (1 - k)
            frame, matte = reframe(frame, scale, lowered), reframe(matte, scale, lowered)
        drop, top = int(round(FACE_DROP * k)), int(round(CARD_TOP * k))
        face = np.zeros((H, W, 3), np.float32)
        face[drop:] = frame[:H - drop]
        face[:drop] = frame[0]
        # pull the outline in a touch: against a dark set the room's light would show as a pale rim
        tight = Image.fromarray(np.ascontiguousarray(matte)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
        person = np.zeros((H, W), np.float32)
        person[drop:] = np.asarray(tight, np.float32)[:H - drop] / 255.0
        person = np.clip((person - 0.12) / 0.84, 0, 1) ** 1.2
        if k < 0.999:
            card = card_mask(top, int(RADIUS * min(1.0, k * 1.6)))
        else:
            card = self.card
        card = card.copy()
        card[:top] = 0
        person[top:] *= card[top:]
        person[min(H, top + RADIUS + 40):] = 0
        move = top - CARD_TOP
        shadow = np.zeros_like(self.shadow)
        if move <= 0:
            shadow[:H + move] = self.shadow[-move:]
        out = out * (1 - 0.42 * shadow * (1 - card))[..., None]
        alpha = np.maximum(card, person)[..., None]
        return out * (1 - alpha) + face * alpha

    def layout(self, sc, t, frame, matte, headline_on):
        """One settled frame of one layout, without text."""
        if sc is None:
            return reframe(frame, *speaker_view(t, self.marks, headline_on)).astype(np.float32)
        if sc["kind"] == "full":
            return np.asarray(self.set_picture(sc, t), np.float32)
        return self.split(sc, t, frame, matte)

    def frame(self, t, speaker, matte):
        sc = self.scene_at(t)
        headline = next(((a, b, p) for a, b, p in self.heads if a <= t < b and sc is None), None)
        # the latest change of layout before t
        start = sc["start"] if sc else max((p["end"] for p in self.plan if p["end"] <= t + 1e-6), default=None)
        before = self.scene_at(start - 0.02) if start is not None and start > 0.05 else None
        since = t - start + 1 / FPS if start is not None and start > 0.05 else 99.0
        kind, old = (sc or {}).get("kind"), (before or {}).get("kind")
        view = speaker_view(t, self.marks, headline is not None)
        place = "face" if sc is None else sc["kind"]      # where the caption goes; "" while the card travels
        if since < MOVE and {kind, old} == {"split", None}:
            k = ease(since / MOVE) if kind == "split" else 1 - ease(since / MOVE)
            place = "face" if k < 0.12 else "split" if k > 0.88 else ""
        if kind == "split" and old is None and since < MOVE:
            out = self.split(sc, t, speaker, matte, ease(since / MOVE), view)
        elif kind is None and old == "split" and since < MOVE:
            out = self.split(before, start - 1 / FPS, speaker, matte, 1 - ease(since / MOVE), view)
        elif kind == "split" and old == "split" and since < 0.2:      # same card, the picture above changes
            k = ease(since / 0.2)
            out = self.split(before, start - 1 / FPS, speaker, matte) * (1 - k) + self.split(sc, t, speaker, matte) * k
        else:
            out = self.layout(sc, t, speaker, matte, headline is not None)
        pic = Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))
        if ("full" in (kind, old)) and since < 0.22:                  # a cut that lands with a quick settle
            zoom = 1 + 0.07 * (1 - ease(since / 0.22))
            edge_x, edge_y = W * (1 - 1 / zoom) / 2, H * (1 - 1 / zoom) / 2
            pic = pic.resize((W, H), Image.BICUBIC, box=(edge_x, edge_y, W - edge_x, H - edge_y))
        if headline:
            a, b, words = headline
            k = ease((t - a) / 0.2)
            gone = ease((t - (b - 0.16)) / 0.16)
            self.paste(pic, words, W / 2, 330 - 30 * gone, 0.82 + 0.18 * k, k * (1 - gone))
        for a, b, words, _ in self.caps:
            if a <= t < b and place:
                where = CAP_Y[place]
                k = ease((t - a + 1 / FPS) / 0.1)
                self.paste(pic, words, W / 2, where, 0.9 + 0.1 * k, 1.0)
                break
        return pic

    @staticmethod
    def paste(base, picture, cx, cy, scale, opacity):
        if opacity <= 0.01:
            return
        if abs(scale - 1) > 0.002:
            picture = picture.resize((max(1, int(picture.width * scale)), max(1, int(picture.height * scale))), Image.BICUBIC)
        if opacity < 0.999:
            picture = picture.copy()
            picture.putalpha(picture.getchannel("A").point(lambda v: int(v * opacity)))
        base.paste(picture, (int(cx - picture.width / 2), int(cy - picture.height / 2)), picture)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project")
    parser.add_argument("--stills")
    parser.add_argument("--face", help="the speaker video, if not the newest work/room/room-vN.mp4")
    parser.add_argument("--out")
    options = parser.parse_args()
    project = Project(options.project)
    work = project.work
    reel = Reel(project)
    room = json.loads((work / "room" / "set_options.json").read_text())
    trim = round(min(max(1 - room["table_top"], 0.035), 0.08), 3)
    w, h = (int(round(v / (1 - trim) / 2)) * 2 for v in (W, H))
    matte_vf = f"scale={w}:{h}:flags=bicubic,crop={W}:{H}:{(w - W) // 2}:0"
    rooms = sorted((work / "room").glob("room-v*.mp4"), key=lambda p: int(p.stem.split("-v")[1]))
    if not options.face and not rooms:
        raise SystemExit("no work/room/room-vN.mp4: run room_reel.py on work/face_cut.mp4 first")
    face, outline = Path(options.face) if options.face else rooms[-1], work / "room" / "outline.mp4"
    total = round(reel.edl["total"] * FPS)
    if options.stills:
        out = work / "look"
        out.mkdir(exist_ok=True)
        for value in options.stills.split(","):
            t = float(value)
            n = min(round(t * FPS), round(reel.edl["voice"] * FPS) - 1)
            a, b = Stream(face, 3, start=n), Stream(outline, 1, matte_vf, start=n)
            reel.frame(t, a.read(), b.read()).save(out / f"{t:07.2f}.jpg", quality=92)
            a.close(), b.close()
        reel.close()
        print("stills in", out)
        return
    renders = project.root / "renders"
    renders.mkdir(exist_ok=True)
    number = 1
    while (renders / f"{project.name}-v{number}.mp4").exists():
        number += 1
    final = Path(options.out) if options.out else renders / f"{project.name}-v{number}.mp4"
    partial = final.with_suffix(".partial.mp4")
    speaker, matte = Stream(face, 3), Stream(outline, 1, matte_vf)
    encoder = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i",
         "pipe:0", "-i", str(work / "voice.wav"), "-map", "0:v", "-map", "1:a", "-vf",
         "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", *TAGS, "-c:v", "libx264", "-crf", "18",
         "-preset", "medium", "-g", str(FPS), "-af", f"apad=whole_dur={total / FPS:.4f}", "-t", f"{total / FPS:.4f}",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(partial)], stdin=subprocess.PIPE)
    for n in range(total):
        encoder.stdin.write(reel.frame(n / FPS, speaker.read(), matte.read()).tobytes())
        if n % 900 == 0:
            print(f"composed {n}/{total}", flush=True)
    reel.close()
    encoder.stdin.close()
    if encoder.wait():
        raise SystemExit("encoding failed")
    partial.replace(final)
    print("done:", final)


if __name__ == "__main__":
    main()
