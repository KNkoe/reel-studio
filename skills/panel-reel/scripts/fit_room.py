"""Fit the studio set to one recording: measure the camera's angle, then write set options.

    uv run --no-project --with numpy python -I fit_room.py <probe_dir> <options.json>
        [--window right|left] [--overlay lines.raw]

Reads what probe.swift wrote. Measures, from the real wall and table:
    roll    the lean of upright lines in the background
    table   the slope of a table edge near the bottom of the picture
    eyes    the height of the speaker's eyes (taken as the camera's eye level)
    light   which side of the face is brighter
Anything it cannot see clearly falls back to the approved room, and the report says so.
The camera is assumed to be roughly level (no strong tilt up or down) and still during a take.
"""
import argparse
import json
import math
from pathlib import Path

import numpy as np

W, H = 540, 960                      # probe size; the set is rendered at twice this
FOCAL = 50 / 36 * 1080               # studio_set.py's lens, in render pixels
CORNER, TABLE = (-0.624, 3.90), -0.455   # must match studio_set.py
APPROVED_TOWARD = 3.2                # table_toward depth used when no table edge is visible

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("probe")
parser.add_argument("out")
parser.add_argument("--window", choices=("right", "left"))
parser.add_argument("--overlay", help="also write a 540x960 grey check picture with the measured lines (raw bytes)")
options = parser.parse_args()

probe = Path(options.probe)
frames = np.fromfile(probe / "frames.gray", np.uint8).reshape(-1, H, W).astype(np.float32)
masks = np.fromfile(probe / "masks.gray", np.uint8).reshape(-1, H, W)
faces = [f for f in json.loads((probe / "faces.json").read_text()) if f]
if not faces:
    raise SystemExit("no face found in any sample: the room cannot be fitted")

still = np.median(frames, axis=0)    # moving hands and head fade out; the room stays
person = np.median(masks, axis=0) > 90


def grow(mask, px):
    out = mask.copy()
    for step in range(1, px + 1):
        out[step:] |= mask[:-step]
        out[:-step] |= mask[step:]
    wide = out.copy()
    for step in range(1, px + 1):
        wide[:, step:] |= out[:, :-step]
        wide[:, :-step] |= out[:, step:]
    return wide


def smooth(a):
    return (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5


picture = smooth(still)
gx = np.zeros_like(picture)
gy = np.zeros_like(picture)
gx[:, 1:-1] = picture[:, 2:] - picture[:, :-2]
gy[1:-1] = picture[2:] - picture[:-2]


def ridge(g, other, axis):
    """Edge pixels: the local peak across the edge, pointing the right way."""
    a = np.abs(g)
    return (a >= np.roll(a, 1, axis)) & (a >= np.roll(a, -1, axis)) & (a > 1.7 * np.abs(other)) & (a > 7)


def lines(g, other, region, angles, upright, most):
    """The longest straight edges in a region, longest first: (pixels along it, degrees, offset).
    Upright lines satisfy x - tan(a) y = offset; level ones y + tan(a) x = offset (rising right
    is positive). Dark-to-light and light-to-dark edges are kept apart."""
    axis = 1 if upright else 0
    ys, xs = np.nonzero(ridge(g, other, axis) & region)
    sign = np.sign(g[ys, xs])
    alive = np.ones(len(ys), bool)
    found = []
    for _ in range(most):
        best = None
        for angle in angles:
            t = math.tan(math.radians(angle))
            u = xs - t * ys if upright else ys + t * xs
            for s in (-1, 1):
                keep = alive & (sign == s)
                if keep.sum() < 10:
                    continue
                keys = np.round(u[keep]).astype(int)
                low = keys.min()
                hist = np.append(np.bincount(keys - low, minlength=2), 0)
                joined = hist[:-1] + hist[1:]                 # a line may straddle two pixels
                at = int(joined.argmax())
                chosen = (keys - low == at) | (keys - low == at + 1)
                cover = len(np.unique((ys if upright else xs)[keep][chosen]))
                if best is None or cover > best[0]:
                    best = (cover, float(angle), float(low + at))
        if best is None or best[0] < 30:
            break
        found.append(best)
        t = math.tan(math.radians(best[1]))
        u = xs - t * ys if upright else ys + t * xs
        alive &= np.abs(u - best[2]) >= 5                     # do not find the same line twice
    return found


# ---------------------------------------------------------------- roll, from upright lines
region = ~grow(person, 10)
region[:4] = region[-4:] = False
region[:, :8] = region[:, -8:] = False
uprights = [l for l in lines(gx, gy, region, np.arange(-10, 10.01, 0.2), True, 6) if l[0] >= 0.12 * H]
roll_seen = bool(uprights)
roll = 0.0
if roll_seen:                       # the middle value, longer lines counting for more
    total, running = sum(l[0] for l in uprights), 0
    for cover, angle, _ in sorted(uprights, key=lambda l: l[1]):
        running += cover
        if running >= total / 2:
            roll = angle
            break

# ---------------------------------------------------------------- the table edge, near the bottom
# The speaker's outline is not excluded: it often takes in the table the hands rest on, and
# clothing has no long straight edges.
region = np.zeros_like(person)
region[int(H * 0.84):-3] = True
edges = lines(gy, gx, region, np.arange(-14, 14.01, 0.25), False, 1)
support = edges[0][0] / W if edges else 0.0
table_seen = support >= 0.25 and abs(edges[0][1]) <= 12
table = edges[0][1] if table_seen else 0.0
intercept = edges[0][2] if table_seen else 0.0

# ---------------------------------------------------------------- eyes, light, speaker's outline
eye_row = float(np.median([f["eyes"][1] for f in faces]))
left, right = [], []
for index, face in enumerate(json.loads((probe / "faces.json").read_text())):
    if not face:
        continue
    x, y, w, h = (v / 2 for v in face["box"])
    cheek = slice(int(y + h * 0.35), int(y + h * 0.75))
    left.append(frames[index][cheek, int(x + w * 0.08):int(x + w * 0.38)].mean())
    right.append(frames[index][cheek, int(x + w * 0.62):int(x + w * 0.92)].mean())
light = float(np.mean(right) / max(np.mean(left), 1) - 1)   # positive: the right side is brighter

if options.window:
    mirror, why = options.window == "right", "chosen on the command line"
elif table_seen and abs(table - roll) >= 2.0:
    mirror, why = table > roll, "the real table edge rises to the " + ("right" if table > roll else "left")
elif abs(light) >= 0.05:
    mirror, why = light > 0, "the light on the face comes from the " + ("right" if light > 0 else "left")
else:
    mirror, why = True, "no clear table or light direction: the last approved side"

eye_row = round(min(max(eye_row, 650), 1200))


# ---------------------------------------------------------------- the room's geometry (table on the left)
def wall(toward_y):
    ax, ay = 1.088 - CORNER[0], toward_y - CORNER[1]
    length = math.hypot(ax, ay)
    ax, ay = ax / length, ay / length
    ox, oy = -ay, ax
    if ox * -CORNER[0] + oy * -CORNER[1] < 0:
        ox, oy = -ox, -oy
    return (ax, ay), (ox, oy)


def column(toward_y, s, d):
    """Picture column, counted as if the table were on the left, of a point s along the table."""
    (ax, ay), (ox, oy) = wall(toward_y)
    x, y = CORNER[0] + ax * s + ox * d, CORNER[1] + ay * s + oy * d
    return 1080 - (540 + FOCAL * x / y), eye_row - FOCAL * TABLE / y


def edge_angle(toward_y):
    (x0, y0), (x1, y1) = column(toward_y, 0.3, 0.49), column(toward_y, 1.9, 0.49)
    return math.degrees(math.atan2(abs(y1 - y0), abs(x1 - x0)))


if table_seen:
    # what the room itself has to supply once the camera's roll is taken out
    wanted = (table - roll) if mirror else (roll - table)
    wanted = min(max(wanted, 1.5), 8.0)
    low, high = 2.2, 3.8                      # the angle falls as the second number grows
    for _ in range(40):
        middle = (low + high) / 2
        low, high = (middle, high) if edge_angle(middle) > wanted else (low, middle)
    toward = round((low + high) / 2, 3)
else:
    toward = APPROVED_TOWARD

# stand the lamp, books and vase where the speaker does not hide them
side = person if mirror else person[:, ::-1]
rows = slice(max(eye_row // 2 - 40, 0), min(eye_row // 2 + 120, H))
covered = np.nonzero(side[rows].any(axis=0))[0]
free = float(covered.min() * 2) if len(covered) else 540.0     # width clear beside the speaker
target = min(max(free * 0.45, 130), 270)
lamp = min(np.arange(0.9, 2.16, 0.01), key=lambda s: abs(column(toward, s, 0.22)[0] - target))
props = {"lamp": round(float(lamp), 2), "books": round(float(lamp) - 0.29, 2), "vase": round(float(lamp) - 0.56, 2)}

# highest point of the real table edge, as a share of the height (1 = not seen)
table_top = (min(intercept, intercept - math.tan(math.radians(table)) * (W - 1)) / H) if table_seen else 1.0

result = {"table_top": round(float(table_top), 4), "size": [1080, 1920], "eye_row": eye_row, "exposure": 1.35, "fstop": 3.6, "samples": 220,
          "mirror": bool(mirror), "roll": round(roll, 2), "table_toward": [1.088, toward], "props": props}
Path(options.out).write_text(json.dumps(result, indent=1))

if options.overlay:
    check = (still * 0.75).astype(np.uint8)
    if roll_seen:
        k = math.tan(math.radians(roll))
        for x0 in (60, 270, 480):
            for y in range(0, H, 2):
                x = int(round(x0 + k * (y - H / 2)))
                if 0 <= x < W - 1:
                    check[y, x:x + 2] = 255
    if table_seen:
        for x in range(W):
            y = int(round(intercept - math.tan(math.radians(table)) * x))
            if 1 <= y < H - 1:
                check[y - 1:y + 2, x] = 255
    check[min(eye_row // 2, H - 1), ::6] = 255
    check.tofile(options.overlay)

print(f"roll   {roll:+.1f} deg" + ("" if roll_seen else "  (no upright line seen: assumed level)"))
print(f"table  " + (f"{table:+.1f} deg, rising right is positive ({support:.0%} of the width seen)" if table_seen
                    else f"not visible ({support:.0%}): approved angle used"))
print(f"eyes   row {eye_row} of 1920     light {light:+.0%} right against left")
print(f"room   window on the {'right' if mirror else 'left'} ({why}); table_toward {toward}; props {props}")
