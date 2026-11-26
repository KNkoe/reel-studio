"""Cut the speaker out of every frame with Robust Video Matting (on this machine).

    python3 rvm_matte.py <model.onnx> <face.mp4> <matte.mp4> [--cuts 0,219,414] [--ratio 0.5]

Needs onnxruntime and numpy (build.py supplies them with `uv`). The output is a grey video of the
speaker's outline, one frame per input frame. Unlike a per-photo person mask, the model carries
memory from frame to frame, which is what keeps edges steady while the speaker moves. The memory
is cleared at each cut ("--cuts": the first frame of every segment) so one shot cannot ghost into
the next.
"""
import argparse
import json
import subprocess
import sys
import time

import numpy as np
import onnxruntime as ort

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("model")
parser.add_argument("video")
parser.add_argument("out")
parser.add_argument("--cuts", default="0")
parser.add_argument("--ratio", type=float, default=0.8,
                    help="the model's internal working scale; lower is faster but hazier around a lit cheek")
options = parser.parse_args()

probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "json", options.video],
                       capture_output=True, text=True, check=True)
stream = json.loads(probe.stdout)["streams"][0]
width, height, rate = stream["width"], stream["height"], stream["r_frame_rate"]
cuts = {int(v) for v in options.cuts.split(",") if v}

# Core ML is about 2.5x faster than the processor alone on Apple silicon and gives the same outline.
wanted = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
session = ort.InferenceSession(options.model, providers=[p for p in wanted if p in ort.get_available_providers()])
ratio = np.array([options.ratio], dtype=np.float32)

reader = subprocess.Popen(["ffmpeg", "-v", "error", "-i", options.video, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          stdout=subprocess.PIPE)
writer = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s",
                           f"{width}x{height}", "-r", rate, "-i", "pipe:0", "-vf",
                           "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p", "-colorspace", "bt709",
                           "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
                           "-c:v", "libx264", "-preset", "fast", "-crf", "8", options.out],
                          stdin=subprocess.PIPE)


def fresh():
    return [np.zeros((1, 1, 1, 1), dtype=np.float32) for _ in range(4)]


memory, count, started = fresh(), 0, time.time()
while True:
    raw = reader.stdout.read(width * height * 3)
    if len(raw) < width * height * 3:
        break
    frame = np.frombuffer(raw, np.uint8).reshape(height, width, 3).transpose(2, 0, 1)[None].astype(np.float32) / 255
    passes = 1
    if count == 0 or count in cuts:   # forget the last shot, then look at this first frame a few times
        memory, passes = fresh(), 3
    for _ in range(passes):
        feed = {"src": frame, "downsample_ratio": ratio, **{f"r{i + 1}i": memory[i] for i in range(4)}}
        _, alpha, *memory = session.run(None, feed)
    writer.stdin.write((np.clip(alpha[0, 0], 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    count += 1
    if count % 300 == 0:
        print(f"matte {count} frames, {count / (time.time() - started):.1f} a second", file=sys.stderr, flush=True)
writer.stdin.close()
if reader.wait() or writer.wait() or not count:
    raise SystemExit("matting failed")
print(f"matte done: {count} frames in {time.time() - started:.0f}s", file=sys.stderr)
