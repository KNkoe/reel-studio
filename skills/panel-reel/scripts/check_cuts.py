#!/usr/bin/env python3
"""Find cuts that land in the middle of speech: check_cuts.py <project>

Speech-engine word timings can fold a pause into the neighbouring word, so a cut that
looks clean in the transcript can still slice a word. This reads the audio itself.
"""
import array
import json
import math
import subprocess
import sys
from pathlib import Path

RATE = 16000


def samples(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return array.array("h", raw)


def level(audio, start, length):
    part = audio[max(0, int(start * RATE)):int((start + length) * RATE)]
    if not part:
        return -120.0
    return 10 * math.log10(sum(v * v for v in part) / len(part) / 32768 ** 2 + 1e-12)


def quiet_point(audio, cut, direction, floor, reach=1.2):
    """Nearest point outward from the cut where 120 ms stays below the floor."""
    for step in range(1, int(reach / 0.02)):
        t = cut + direction * step * 0.02
        if level(audio, t - 0.06, 0.12) < floor:
            return round(t, 2)
    return None


def main():
    root = Path(sys.argv[1]).resolve()
    plan = json.loads((root / "plan.json").read_text())
    audio, floors = {}, {}
    for key, source in plan["sources"].items():
        path = Path(source.get("audio", source["video"])).expanduser()
        audio[key] = samples(path if path.is_absolute() else root / path)
        windows = sorted(level(audio[key], i * 0.1, 0.1) for i in range(int(len(audio[key]) / RATE * 10)))
        speech = windows[int(len(windows) * 0.9)]
        floors[key] = speech - 24
    flagged, segments = 0, plan["segments"]
    words = {}
    for key, source in plan["sources"].items():
        path = Path(source["words"]).expanduser()
        words[key] = json.loads((path if path.is_absolute() else root / path).read_text())
    for index, seg in enumerate(segments):
        a, floor = audio[seg["src"]], floors[seg["src"]]
        joined = {"in": index > 0 and segments[index - 1]["src"] == seg["src"] and abs(segments[index - 1]["out"] - seg["in"]) < 0.02,
                  "out": index + 1 < len(segments) and segments[index + 1]["src"] == seg["src"]
                         and abs(segments[index + 1]["in"] - seg["out"]) < 0.02}
        # A word whose timing crosses the end of a piece, with sound still to come before
        # it finishes, was probably spoken after the pause and has been cut off.
        for start, end, text in words[seg["src"]]:
            if not joined["out"] and start < seg["out"] < end - 0.15:
                later = [seg["out"] + i * 0.05 for i in range(int((end - seg["out"]) / 0.05))]
                heard = [t for t in later if level(a, t, 0.05) > floor + 10]
                if len(heard) >= 3:
                    flagged += 1
                    print(f"{seg['id']:6s} out {seg['out']:8.2f}  '{text}' may be cut off: sound continues until about {heard[-1] + 0.05:.2f}")
        for edge, cut, direction in (("in", seg["in"], -1), ("out", seg["out"], 1)):
            if joined[edge]:
                continue
            before, after = level(a, cut - 0.06, 0.06), level(a, cut, 0.06)
            if before > floor and after > floor:
                flagged += 1
                better = quiet_point(a, cut, direction, floor)
                print(f"{seg['id']:6s} {edge:3s} {cut:8.2f}  speech both sides ({before:.0f}/{after:.0f} dB, floor {floor:.0f})"
                      + (f"  -> quiet at {better}" if better else "  -> no pause nearby; listen to it"))
    print(f"{flagged} possible clipped edges across {len(segments)} pieces")


if __name__ == "__main__":
    main()
