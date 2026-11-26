"""Line up a separately recorded camera clip with the screen recording, by their sound.

    uv run --no-project --with numpy python -I sync_camera.py <camera clip> <mic audio or .skbundle>

Prints "video_offset" and "video_drift" for the plan source:
    camera time = screen time + video_offset + video_drift * screen time
and how good the match is: "matched_points" of "points", "worst_ms" disagreement, whether
the drift could be measured at all (it needs a take over a minute), and "weak".
The camera's microphone is only used to find these; the voice still comes from the screen
recording's microphone. Two devices run on two clocks, so the match is measured at several
points along the take, and the script stops rather than guess when they do not agree.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

RATE = 8000
HOP = 80                     # 10 ms
WINDOW = 12.0                # seconds of sound per fine measurement
SEARCH = 0.4                 # seconds either side of the rough match
FRAME = 1 / 30


def sound(path: Path) -> np.ndarray:
    # first_pts=0 keeps a track's own small start delay, so times match its video
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-af",
                          f"aresample={RATE}:async=1:first_pts=0", "-ac", "1", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    data = np.frombuffer(out, np.float32).astype(np.float64)
    if len(data) < RATE * 4:
        raise SystemExit(f"{path.name}: under 4 seconds of sound, too short to match")
    return data


def loudness(x: np.ndarray) -> np.ndarray:
    """How loud each 10 ms is, minus the slow level, so only the rhythm of speech is left."""
    n = len(x) // HOP
    level = np.log(np.sqrt((x[:n * HOP].reshape(n, HOP) ** 2).mean(1)) + 1e-4)
    width = min(101, n | 1)
    slow = np.convolve(level, np.ones(width) / width, mode="same")
    return level - slow


def correlate(a: np.ndarray, b: np.ndarray):
    """c[k] = sum a[i + k] * b[i], for k from -(len(b) - 1) to len(a) - 1."""
    size = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    c = np.fft.irfft(np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size)), size)
    c = np.concatenate((c[size - len(b) + 1:], c[:len(a)]))
    return c, np.arange(-(len(b) - 1), len(a))


def rough(camera: np.ndarray, reference: np.ndarray):
    c, lags = correlate(loudness(camera), loudness(reference))
    # only lags where the two share at least a few seconds
    overlap = np.minimum(len(camera) // HOP - lags, len(reference) // HOP) - np.maximum(-lags, 0)
    need = min(500, int(0.6 * min(len(camera), len(reference)) / HOP))
    c = np.where(overlap >= need, c / np.sqrt(np.maximum(overlap, 1)), -np.inf)
    best = int(np.argmax(c))
    rest = c[np.abs(lags - lags[best]) > 100]
    rival = rest[np.isfinite(rest)].max(initial=1e-9)
    return lags[best] * HOP / RATE, float(c[best] / max(rival, 1e-9))


def speech_band(x: np.ndarray, size: int):
    spectrum = np.fft.rfft(x, size)
    freq = np.fft.rfftfreq(size, 1 / RATE)
    spectrum[(freq < 250) | (freq > 3400)] = 0
    return spectrum


def fine(camera, reference, start: float, length: float, guess: float):
    """Offset for one window of the reference, to within a sample, with how sharp the match is."""
    r = reference[int(start * RATE):int((start + length) * RATE)]
    first = int(round((start + guess - SEARCH) * RATE))
    c = camera[max(first, 0):int((start + length + guess + SEARCH) * RATE)]
    if len(c) < len(r) or np.sqrt((r ** 2).mean()) < 1e-3:
        return None
    size = 1 << int(np.ceil(np.log2(len(r) + len(c))))
    cross = speech_band(c, size) * np.conj(speech_band(r, size))
    cross /= np.abs(cross) ** 0.8 + 1e-9           # partly whitened: sharp peak, little noise gain
    corr = np.fft.irfft(cross, size)[:len(c) - len(r) + 1]
    peak = int(np.argmax(corr))
    sharp = float(corr[peak] / (np.median(np.abs(corr)) + 1e-12))
    if peak in (0, len(corr) - 1):
        return None
    return (max(first, 0) + peak) / RATE - start, sharp


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    clip, other = Path(sys.argv[1]), Path(sys.argv[2])
    if other.is_dir():
        tracks = sorted((other / "media").glob("microphone*"))
        if len(tracks) != 1:
            raise SystemExit(f"expected one microphone track in {other.name}/media, found {len(tracks)}")
        other = tracks[0]
    camera, reference = sound(clip), sound(other)
    guess, margin = rough(camera, reference)
    total = len(reference) / RATE
    # short takes get shorter, overlapping windows, so there is still more than one opinion
    length = min(WINDOW, max(3.0, total / 4))
    # measure only where both recordings exist
    low = max(0.0, -guess + SEARCH)
    high = min(total, len(camera) / RATE - guess - SEARCH) - length
    if high < low:
        raise SystemExit("the two recordings hardly overlap: are they the same take?")
    count = max(1 if high - low < 1 else 3, min(14, int((high - low) / length) + 1))
    found = []
    for start in np.linspace(low, high, count):
        got = fine(camera, reference, float(start), length, guess)
        if got and got[1] > 9:
            found.append((float(start) + length / 2, got[0], got[1]))
    needed = 1 if count == 1 else max(3 if count >= 3 else 2, count // 3)
    if len(found) < needed:
        raise SystemExit(f"NOT MATCHED: only {len(found)} of {count} points had a clear match (rough {guess:+.2f}s, "
                         f"{margin:.1f}x the next best). Check these are the same take, or line them up by a clap")
    t, offsets, weight = (np.array(v) for v in zip(*found))
    keep = np.abs(offsets - np.median(offsets)) < max(0.12, 3e-4 * np.ptp(t))
    for _ in range(3):
        if np.ptp(t[keep]) > 60 and keep.sum() >= 3:
            drift, base = np.polyfit(t[keep], offsets[keep], 1, w=np.sqrt(weight[keep]))
        else:                          # too short a span to measure drift honestly
            drift, base = 0.0, float(np.median(offsets[keep]))
        error = np.abs(offsets - (base + drift * t))
        keep = error < FRAME
        if keep.sum() < needed:
            raise SystemExit("NOT MATCHED: the points disagree by more than a frame. A recording may have skipped, "
                             "or these are different takes")
    if abs(drift) > 1e-3 or keep.sum() < 0.6 * len(found):
        raise SystemExit(f"NOT MATCHED: unreliable ({keep.sum()} of {len(found)} points agree, "
                         f"drift {drift * 1e6:.0f} ppm)")
    worst = float(error[keep].max())
    measured = bool(np.ptp(t[keep]) > 60 and keep.sum() >= 3)
    # few points, many of them disagreeing, or loose agreement: usable only after a check by eye
    weak = bool(keep.sum() < 3 or keep.sum() < 0.6 * count or worst > 0.02)
    print(f"matched at {keep.sum()} of {count} points, worst disagreement {worst * 1000:.0f} ms, "
          f"drift over the take {drift * total * 1000:+.0f} ms", file=sys.stderr)
    print(json.dumps({"video_offset": round(float(base), 4), "video_drift": float(f"{drift:.8f}"),
                      "matched_points": int(keep.sum()), "points": count, "worst_ms": round(worst * 1000, 1),
                      "drift_measured": measured, "weak": weak}))


if __name__ == "__main__":
    main()
