"""Objects the story needs: shield, coins, documents, flags, photos, trophies and so on."""
import math
import random

import bmesh
import bpy
from mathutils import Vector

import kit as K
from kit import (CHARCOAL, CLEAR, FLAG, FLAG_SOFT, GAP, GOLD, INK2, ORANGE, ORANGE_SOFT, WHITE, anim, back, box,
                 cylinder, empty, flat, inout, mat, out3, pop, prism, seg, slab, sphere, text, torus, tube, visible)

# set these from a scene file: the word on a shield and the letter struck on coins
SHIELD_WORD = ""
COIN_FACE = ""
DEFAULT = object()


def title(lines, start, leave=None, row=330, size=92, colours=(WHITE, ORANGE), depth=-0.4, maxw=960):
    """Big extruded words at the top of the set; each line swings in."""
    made = []
    for i, line in enumerate(lines):
        pivot = empty(K.P(540, row + i * size * 1.28, depth))
        words = text(line, size, mat(colours[min(i, len(colours) - 1)], rough=0.3, emit=0.55), parent=pivot,
                     weight=900, thick=0.34, maxw=maxw, edge=0.012)
        words.visible_shadow = False
        begin = start + i * 0.12

        def step(t, pivot=pivot, begin=begin):
            k = back(seg(t, begin, 0.55), 1.3)
            gone = K.inout(seg(t, leave, 0.28)) if leave is not None else 0.0
            pivot.rotation_euler = ((1 - k) * 1.45 - gone * 1.4, 0, 0)
            s = max(0.001, min(1.0, seg(t, begin, 0.3) * 1.4) * (1 - gone))
            pivot.scale = (s, s, s)
            visible(pivot, t >= begin and gone < 0.999)
        anim(step)
        made.append(pivot)
    return made


def shield(width, height, parent=None, location=(0, 0, 0), word=DEFAULT):
    """A raised shield; `word` is written across it."""
    word = SHIELD_WORD if word is DEFAULT else word
    group = empty(location, parent)
    w, h = width / 2, height / 2

    def outline(k):
        pts = [(-w * k, h * 0.78 * k), (-w * 0.55 * k, h * 0.92 * k), (0, h * k), (w * 0.55 * k, h * 0.92 * k),
               (w * k, h * 0.78 * k), (w * 0.96 * k, h * 0.1 * k), (w * 0.72 * k, -h * 0.45 * k),
               (w * 0.38 * k, -h * 0.78 * k), (0, -h * k), (-w * 0.38 * k, -h * 0.78 * k),
               (-w * 0.72 * k, -h * 0.45 * k), (-w * 0.96 * k, h * 0.1 * k)]
        return pts
    prism(outline(1.0), 0.45, mat(ORANGE, rough=0.22, metal=0.35, coat=0.6), parent=group, round_=0.14)
    prism(outline(0.84), 0.2, mat(CHARCOAL, rough=0.3, coat=0.4), (0, -0.24, 0), group, round_=0.08)
    if word:
        text(word, width * 100 * 0.17, mat(WHITE, rough=0.3, emit=0.5), (0, -0.42, 0.02), group, weight=900,
             thick=0.14, maxw=width * 100 * 0.76)
    return group


def coin(radius=0.5, thick=0.14, parent=None, location=(0, 0, 0), face=DEFAULT):
    face = COIN_FACE if face is DEFAULT else face
    group = empty(location, parent)
    gold = mat(GOLD, rough=0.24, metal=1.0)
    cylinder(radius, thick, gold, parent=group, axis="Y", round_=0.035)
    torus(radius * 0.76, radius * 0.055, gold, (0, -thick / 2, 0), group, rings=64, sides=12)
    if face:
        text(face, radius * 105, mat("#ffe3a1", rough=0.35, metal=0.6, emit=0.22), (0, -thick / 2 - 0.02, 0), group,
             weight=900, thick=0.05)
    return group


def flat_coin(radius, thick, location, parent=None):
    """A coin lying down, for stacks."""
    gold = mat(GOLD, rough=0.26, metal=1.0)
    group = empty(location, parent)
    cylinder(radius, thick, gold, parent=group, round_=min(0.04, thick * 0.3))
    torus(radius * 0.74, thick * 0.16, gold, (0, 0, thick / 2), group, rings=48, sides=8, upright=False)
    return group


def document(width=2.0, height=2.7, parent=None, location=(0, 0, 0), seed=1, heading=ORANGE, paper="#eef0f5"):
    group = empty(location, parent)
    slab(width, height, 0.07, mat(paper, rough=0.55), radius=0.12, parent=group)
    rnd = random.Random(seed)
    ink = mat(GAP, rough=0.7)
    top = height / 2 - height * 0.12
    box((width * 0.46, 0.03, height * 0.065), mat(heading, rough=0.4), (-width * 0.2, -0.05, top), 0.02, group)
    rows = int(height / 0.27) - 2
    for i in range(rows):
        z = top - height * 0.14 - i * (height * 0.7 / max(1, rows))
        length = width * rnd.uniform(0.35, 0.78)
        box((length, 0.02, height * 0.028), ink, (-width * 0.39 + length / 2, -0.045, z), 0.008, group)
    return group


def flag(height=3.2, width=1.9, parent=None, location=(0, 0, 0), colour=FLAG, mark="?"):
    """A pole with cloth that ripples; location is the foot of the pole."""
    group = empty(location, parent)
    steel = mat("#c9ccd6", rough=0.25, metal=1.0)
    cylinder(0.07, height, steel, (0, 0, height / 2), group, round_=0.02)
    sphere(0.14, steel, (0, 0, height + 0.05), group)
    cylinder(0.42, 0.14, mat(CHARCOAL, rough=0.35, coat=0.5), (0, 0, 0.07), group, round_=0.05)
    cloth_h = width * 0.66
    nx, nz = 28, 14
    bm = bmesh.new()
    grid = [[bm.verts.new((0.07 + width * i / nx, 0, height - cloth_h + cloth_h * j / nz)) for j in range(nz + 1)]
            for i in range(nx + 1)]
    for i in range(nx):
        for j in range(nz):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
    cloth = K.mesh_object("cloth", bm, mat(colour, rough=0.45, emit=0.12), parent=group)
    thicken = cloth.modifiers.new("cloth thickness", "SOLIDIFY")
    thicken.thickness, thicken.offset = 0.025, 0
    rest = [v.co.copy() for v in cloth.data.vertices]

    def wave(x, t):
        reach = (x - 0.07) / width
        return 0.22 * reach * math.sin(reach * 7.5 - t * 5.2)

    letter = None
    if mark:
        letter = text(mark, cloth_h * 62, flat(WHITE), (0.07 + width * 0.5, -0.14, height - cloth_h / 2), group,
                      weight=900, thick=0.04)

    def step(t):
        for v, co in zip(cloth.data.vertices, rest):
            v.co = (co.x, wave(co.x, t), co.z + 0.05 * (co.x / width) * math.sin(co.x * 3 - t * 4))
        cloth.data.update()
        if letter:
            letter.location.y = wave(0.07 + width * 0.5, t) - 0.17
    anim(step)
    return group


def photo(path, width=None, height=None, parent=None, location=(0, 0, 0), border=0.12, crop=None):
    """A framed print. Give width or height in units; crop=(x0, y0, x1, y1) as shares of the picture."""
    m, image = K.picture_mat(path)
    iw, ih = image.size
    x0, y0, x1, y1 = crop or (0, 0, 1, 1)
    ratio = (iw * (x1 - x0)) / (ih * (y1 - y0))
    if width is None:
        width = height * ratio
    if height is None:
        height = width / ratio
    group = empty(location, parent)
    slab(width + border * 2, height + border * 2, 0.12, mat("#f7f7fa", rough=0.5, emit=0.2), radius=0.1,
         parent=group)
    bm = bmesh.new()
    corners = [(-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2), (-width / 2, height / 2)]
    verts = [bm.verts.new((x, -0.075, z)) for x, z in corners]
    face = bm.faces.new(verts)
    uv = bm.loops.layers.uv.new("uv")
    for loop, (u, v) in zip(face.loops, ((x0, 1 - y1), (x1, 1 - y1), (x1, 1 - y0), (x0, 1 - y0))):
        loop[uv].uv = (u, v)
    K.mesh_object("print", bm, m, parent=group, smooth=False)
    return group


def confetti(start, count=160, seed=3, top=17.0, spread=7.5, depth=(-2.5, 5.0)):
    rnd = random.Random(seed)
    colours = (ORANGE, FLAG, "#ffffff", GOLD, CLEAR)
    pieces = []
    for i in range(count):
        piece = box((0.16, 0.012, 0.09), mat(rnd.choice(colours), rough=0.35, metal=0.2, emit=0.35), round_=0)
        piece.visible_shadow = False
        pieces.append((piece, rnd.uniform(-spread, spread), rnd.uniform(*depth), rnd.uniform(0, 7),
                       rnd.uniform(2.4, 4.4), rnd.uniform(0, 6.28), rnd.uniform(2, 7)))

    def step(t):
        for piece, x, y, wait, speed, phase, spin in pieces:
            fall = t - start - wait * 0.35
            z = top - speed * fall
            visible(piece, fall > 0 and z > 0)
            piece.location = (x + 0.5 * math.sin(fall * 2 + phase), y, max(z, 0))
            piece.rotation_euler = (fall * spin + phase, fall * spin * 0.6, phase)
    anim(step)


def tower(width, height, depth, parent=None, location=(0, 0, 0), body="#343b55", lit=ORANGE_SOFT, seed=2):
    """An office block with lit windows; location is the middle of its foot."""
    group = empty(location, parent)
    box((width, depth, height), mat(body, rough=0.4, metal=0.2, coat=0.3), (0, 0, height / 2), 0.07, group)
    rnd = random.Random(seed)
    cols, rows = max(2, int(width / 0.34)), max(3, int(height / 0.4))
    for i in range(cols):
        for j in range(rows):
            x = -width / 2 + width * (i + 0.5) / cols
            z = height * (j + 0.55) / (rows + 0.2)
            on = rnd.random() < 0.62
            box((width / cols * 0.55, 0.03, height / rows * 0.45),
                flat(lit, 0.95) if on else mat("#1b2032", rough=0.15, metal=0.4),
                (x, -depth / 2 - 0.012, z), 0, group)
    return group


def arrow_ring(radius, thick, colour, parent=None, location=(0, 0, 0)):
    """A circular 'sent back' arrow."""
    group = empty(location, parent)
    pts = []
    for i in range(41):
        a = math.radians(70 + 290 * i / 40)
        pts.append((radius * math.cos(a), 0, radius * math.sin(a)))
    m = mat(colour, rough=0.25, emit=0.35, metal=0.2)
    tube(pts, thick, m, group)
    end, before = Vector(pts[-1]), Vector(pts[-2])
    direction = (end - before).normalized()
    side = Vector((-direction.z, 0, direction.x))
    tip = end + direction * thick * 4
    base_a, base_b = end + side * thick * 2.8, end - side * thick * 2.8
    prism([(tip.x, tip.z), (base_a.x, base_a.z), (base_b.x, base_b.z)], thick * 2.2, m, parent=group, round_=0.03)
    return group


def magnifier(radius=1.0, parent=None, location=(0, 0, 0)):
    group = empty(location, parent)
    steel = mat("#d7d9e2", rough=0.18, metal=1.0)
    torus(radius, radius * 0.13, steel, parent=group)
    cylinder(radius * 0.95, 0.04, mat("#bcd4ff", rough=0.05, alpha=0.16), parent=group, axis="Y", round_=0)
    grip = cylinder(radius * 0.16, radius * 1.35, mat(ORANGE, rough=0.3, coat=0.5),
                    (radius * 1.27, 0, -radius * 1.27), group, round_=0.1)
    grip.rotation_euler = (0, math.radians(-45), 0)
    return group


def check_mark(size, colour, parent=None, location=(0, 0, 0), thick=None):
    group = empty(location, parent)
    pts = [(-size * 0.5, 0, 0.0), (-size * 0.14, 0, -size * 0.36), (size * 0.52, 0, size * 0.42)]
    tube(pts, thick or size * 0.12, mat(colour, rough=0.25, emit=0.4), group, smooth=False)
    for p in pts:
        sphere(thick or size * 0.12, mat(colour, rough=0.25, emit=0.4), p, group)
    return group


def cross_mark(size, colour, parent=None, location=(0, 0, 0)):
    group = empty(location, parent)
    for turn in (45, -45):
        bar = box((size, size * 0.2, size * 0.2), mat(colour, rough=0.25, emit=0.4), round_=size * 0.08, parent=group)
        bar.rotation_euler = (0, math.radians(turn), 0)
    return group


def trophy(parent=None, location=(0, 0, 0), scale=1.0, metal_colour=GOLD, label="", ghost=False):
    """A two-handled cup on a plinth; location is the middle of the plinth's foot."""
    group = empty(location, parent)
    cup = mat(metal_colour, rough=0.2, metal=1.0) if not ghost else mat("#9aa6d8", rough=0.15, emit=0.3, alpha=0.28,
                                                                        name="ghost")
    plinth = mat(CHARCOAL, rough=0.25, coat=0.6)
    box((1.9 * scale, 1.5 * scale, 1.05 * scale), plinth, (0, 0, 0.525 * scale), 0.1, group)
    profile = [(0.0, 1.05), (0.62, 1.05), (0.6, 1.17), (0.28, 1.28), (0.14, 1.5), (0.13, 1.75), (0.3, 1.9),
               (0.58, 2.15), (0.76, 2.6), (0.84, 3.15), (0.9, 3.22), (0.84, 3.26), (0.76, 3.15), (0.62, 2.6),
               (0.4, 2.25), (0.0, 2.15)]
    K.lathe([(r * scale, z * scale) for r, z in profile], cup, parent=group)
    for side in (-1, 1):
        pts = [(side * x * scale, 0, z * scale) for x, z in ((0.78, 3.0), (1.2, 2.98), (1.28, 2.62), (1.02, 2.32),
                                                             (0.62, 2.2))]
        tube(pts, 0.075 * scale, cup, group)
    if label:
        text(label, 44 * scale, mat(WHITE, rough=0.3, emit=0.6), (0, -0.78 * scale, 0.52 * scale), group,
             weight=900, thick=0.08)
    return group


def gear(radius, teeth, thick, material, parent=None, location=(0, 0, 0)):
    pts = []
    for i in range(teeth):
        for frac, r in ((0.0, 0.8), (0.18, 1.0), (0.48, 1.0), (0.66, 0.8)):
            a = 2 * math.pi * (i + frac) / teeth
            pts.append((radius * r * math.cos(a), radius * r * math.sin(a)))
    group = empty(location, parent)
    prism(pts, thick, material, parent=group, round_=0.04)
    cylinder(radius * 0.3, thick * 1.25, mat(CHARCOAL, rough=0.3, coat=0.5), parent=group, axis="Y", round_=0.05)
    return group


def spin(obj, speed, axis=1, start=0.0):
    def step(t):
        obj.rotation_euler[axis] = speed * max(0.0, t - start)
    anim(step)
    return obj


def label(words, px, py, start, c, size=40, colour=WHITE, depth=-0.6, maxw=330, emit=0.7, face="sans", weight=900):
    low = py > K.S.floor - 20
    group = empty(K.front(px, py) if low else K.P(px, py, depth))
    if low:        # nearer the camera, so drawn smaller to read at the asked size
        k = K.DIST / (K.DIST + group.location.y)
        size, maxw = size / k, maxw / k
    text(words, size, mat(colour, rough=0.4, emit=emit), parent=group, face=face, weight=weight, thick=0.06, maxw=maxw)
    pop(group, c(start), 0.4)
    return group


def drift_photo(group, t0, home, enter_from, tilt, c, length=0.7, leave=None, exit_to=None, zoom=0.04):
    """A print flies in, settles at a slight angle and keeps creeping closer."""
    begin = c(t0)
    start_at = Vector(home) + Vector(enter_from)

    def step(t):
        k = out3(seg(t, begin, length))
        where = start_at.lerp(Vector(home), k)
        s = 1 + zoom * seg(t, begin, 8.0)
        turn = (0, (1 - k) * tilt * 4 + tilt, (1 - k) * 0.7)
        if leave is not None and t > c(leave):
            g = inout(seg(t, c(leave), 0.45))
            where = where.lerp(Vector(exit_to), g)
        group.location = where
        group.rotation_euler = turn
        group.scale = (s, s, s)
        visible(group, t >= begin - 0.001)
    anim(step)


def stack(px, py, depth, colour):
    """A system of record: three stacked drums with a light on each."""
    group = empty(K.P(px, py, depth))
    for i in range(3):
        cylinder(1.05, 0.5, mat("#e8eaf2", rough=0.25, coat=0.6), (0, 0, i * 0.6), group, round_=0.14)
        torus(1.06, 0.035, flat(colour, 1.4), (0, 0, i * 0.6), group, upright=False)
        sphere(0.09, flat(CLEAR, 2.0), (0.55, -0.92, i * 0.6), group, detail=2)
    return group
