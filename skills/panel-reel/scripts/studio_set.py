"""Render the studio set that goes behind the speaker (Blender, Cycles, on this machine).

    blender --background --factory-startup --python studio_set.py -- <out.png> [options.json]

Everything is modelled here, so there are no downloads, stock licences or generation credits.
A real lens blur and bounced light are what make it read as a room rather than a graphic. The
colours are the warm copper family of the face grade, and the grade is applied over it again when
the speaker is composited, so the two always match.

The room is seen at an angle, into a corner: a window wall running away on the left, and a second
wall with a wooden table along it on the right. A wall square to the camera looks like a backdrop;
the converging sill and table edge are what make it read as a place. This borrows how well-regarded
tech creators frame their rooms, not any one creator's belongings.

Keep it uncluttered: a plant and two books by the window; a vase, a few books and one lamp on the
table. Do not add objects to fill space. No screens or computers: a lit screen is a second light
source that fights the grade.

The table stands BEHIND the speaker. Footage framed at the shoulders shows no hands resting on
anything, so furniture in front of them never sits in the right place.

Framing: the camera matches a speaker at about 0.85 m filling the middle of a 1080x886 frame.
In the popout layout only the lower ~610 px show, and the speaker hides the middle, so what must
be seen sits in the side zones (the window left of column 300, the lamp near column 900). The face
punch-in crops about 35 px from each side.
"""
import json
import math
import random
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
options = json.load(open(argv[1])) if len(argv) > 1 else {}
WIDTH, HEIGHT = options.get("size", [1080, 886])
TALL = HEIGHT > WIDTH                           # the full-screen version, used when the speaker fills the frame
EYE_ROW = options.get("eye_row", 920 if TALL else HEIGHT / 2 - 43)
WALL_H = 4.8 if TALL else 2.8
SAMPLES = options.get("samples", 220)
FSTOP = options.get("fstop", 4.2)              # lower is blurrier
LIGHT = options.get("light", 1.0)              # overall strength of the practicals
SWAP = options.get("swap", {})                 # recolouring: a colour written below -> the colour to use
rng = random.Random(options.get("seed", 7))
# Fitting the room to the footage: which side the window is on, the camera's roll, how fast the
# table recedes and where its things stand. The defaults give the room exactly as approved.
MIRROR = options.get("mirror", False)           # window on the right, table on the left
ROLL = math.radians(options.get("roll", 0.0))   # positive turns the finished picture counterclockwise
TABLE_TOWARD = options.get("table_toward", [1.088, 2.55])   # a larger second number flattens the table edge
PROPS = {"vase": 0.62, "books": 1.40, "lamp": 1.78, **options.get("props", {})}   # distance from the corner

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


def linear(hex_colour):
    hex_colour = SWAP.get(hex_colour, hex_colour)
    out = []
    for i in (1, 3, 5):
        c = int(hex_colour[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def material(name, colour, rough=0.6, metal=0.0, grain=None, bump=0.0, glow=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = linear(colour)
    shader.inputs["Roughness"].default_value = rough
    shader.inputs["Metallic"].default_value = metal
    if glow:
        shader.inputs["Emission Color"].default_value = linear(glow)
        shader.inputs["Emission Strength"].default_value = strength * LIGHT
    if grain or bump:
        coords = nodes.new("ShaderNodeTexCoord")
        mapping = nodes.new("ShaderNodeMapping")
        links.new(coords.outputs["Object"], mapping.inputs["Vector"])
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Detail"].default_value = 8.0
        links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
        if grain:   # (second colour, stretch): long stretched noise reads as wood grain
            other, stretch = grain
            mapping.inputs["Scale"].default_value = stretch
            noise.inputs["Scale"].default_value = 1.0
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].position = 0.36
            ramp.color_ramp.elements[0].color = linear(colour)
            ramp.color_ramp.elements[1].position = 0.66
            ramp.color_ramp.elements[1].color = linear(other)
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
        if bump:
            noise.inputs["Scale"].default_value = 26.0 if not grain else 1.0
            node = nodes.new("ShaderNodeBump")
            node.inputs["Strength"].default_value = bump
            node.inputs["Distance"].default_value = 0.01
            links.new(noise.outputs["Fac"], node.inputs["Height"])
            links.new(node.outputs["Normal"], shader.inputs["Normal"])
    return mat


def place(obj, mat, bevel=0.0):
    obj.data.materials.append(mat)
    if bevel:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width, mod.segments = bevel, 3
    return obj


def box(centre, size, mat, bevel=0.004, turn=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=centre, rotation=turn)
    obj = bpy.context.object
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return place(obj, mat, bevel)


def cylinder(centre, radius, depth, mat, turn=(0, 0, 0), sides=48, bevel=0.004):
    bpy.ops.mesh.primitive_cylinder_add(vertices=sides, radius=radius, depth=depth, location=centre, rotation=turn)
    return place(bpy.context.object, mat, bevel)


def ball(centre, radius, mat, squash=(1, 1, 1), turn=(0, 0, 0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=20, radius=radius, location=centre, rotation=turn)
    obj = bpy.context.object
    obj.scale = squash
    bpy.ops.object.shade_smooth()
    return place(obj, mat)


# ---------------------------------------------------------------- materials (warm copper family)
plaster = material("plaster", "#6b5d55", rough=0.92, bump=0.22)
pier = material("pier", "#7a6a60", rough=0.9, bump=0.15)
walnut = material("walnut", "#654029", rough=0.38, grain=("#a0704a", (2.2, 30.0, 30.0)), bump=0.04)
frame_metal = material("frame", "#1b1715", rough=0.45, metal=0.4)
brass = material("brass", "#b98a55", rough=0.28, metal=1.0)
cream = material("cream", "#cdbba6", rough=0.65)
stone = material("stone", "#a8968a", rough=0.8, bump=0.1)
clay = material("clay", "#9a5435", rough=0.78, bump=0.15)
twig = material("twig", "#6a4a30", rough=0.9)
seed_head = material("seed", "#b8956c", rough=0.95)
leaves = [material(f"leaf{i}", c, rough=0.5) for i, c in enumerate(["#33452a", "#455a30", "#26361f"])]
books = [material(f"book{i}", c, rough=0.75) for i, c in enumerate(["#b89a7a", "#7a3b26", "#33261f", "#d3c3ab"])]
shade = material("shade", "#7a5636", rough=0.95, bump=0.15, glow="#ffb066", strength=1.25)


# ---------------------------------------------------------------- two walls that meet at a corner
# The corner lands about column 300 and 3.9 m away; each wall comes toward the camera from it.
CORNER = Vector((-0.624, 3.90))


class Wall:
    """Places things by distance along the wall from the corner (s), out into the room (d) and height."""

    def __init__(self, toward):
        self.along = (Vector(toward) - CORNER).normalized()
        self.out = Vector((-self.along.y, self.along.x))
        if self.out.dot(-CORNER) < 0:                    # the normal points into the room
            self.out.negate()
        self.angle = math.atan2(self.along.y, self.along.x)

    def at(self, s, d, z):
        flat = CORNER + self.along * s + self.out * d
        return (flat.x, flat.y, z)

    def box(self, s, d, z, mat, bevel=0.004, turn=0.0):
        """s, d and z are (from, to) pairs."""
        return box(self.at(sum(s) / 2, sum(d) / 2, sum(z) / 2), (s[1] - s[0], d[1] - d[0], z[1] - z[0]), mat, bevel,
                   turn=(0, 0, self.angle + turn))


window = Wall((-0.967, 2.50))                            # left
side = Wall(TABLE_TOWARD)                               # right, carries the table
LOW, HIGH = -3.2, WALL_H - 0.9

side.box((-0.05, 3.2), (-0.05, 0.0), (LOW, HIGH), plaster, 0)

SILL, HEAD, OPEN, END = -0.30, 0.78 if not TALL else 1.45, 0.13, 1.75
window.box((0.0, 2.1), (-0.05, 0.0), (LOW, SILL), plaster, 0)                    # below the window
window.box((0.0, 2.1), (-0.05, 0.0), (HEAD, HIGH), plaster, 0)                   # above it
window.box((END, 2.1), (-0.05, 0.0), (SILL, HEAD), plaster, 0)
window.box((-0.02, OPEN), (-0.05, 0.055), (LOW, HIGH), pier, 0.008)              # the corner column
for s in (OPEN + 0.012, 0.46, 0.80, 1.17, 1.58):                                 # slim dark glazing bars
    window.box((s - 0.011, s + 0.011), (-0.035, 0.0), (SILL, HEAD), frame_metal, 0.002)
for z in (SILL + 0.012, 0.13, HEAD - 0.012) + ((0.70,) if TALL else ()):
    window.box((OPEN, END), (-0.035, 0.0), (z - 0.011, z + 0.011), frame_metal, 0.002)
window.box((OPEN, END), (-0.04, 0.15), (SILL - 0.030, SILL), walnut, 0.006)      # a deep wooden sill

# ---------------------------------------------------------------- outside: soft late light, treetops, roofs
OUTSIDE = 7.0


def sky():
    mat = bpy.data.materials.new("sky")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.remove(nodes["Principled BSDF"])
    position = nodes.new("ShaderNodeNewGeometry")
    split = nodes.new("ShaderNodeSeparateXYZ")
    links.new(position.outputs["Position"], split.inputs[0])
    span = nodes.new("ShaderNodeMapRange")
    span.inputs["From Min"].default_value, span.inputs["From Max"].default_value = -1.4, 1.8
    links.new(split.outputs["Z"], span.inputs["Value"])
    ramp = nodes.new("ShaderNodeValToRGB")
    stops = ramp.color_ramp.elements
    stops[0].position, stops[0].color = 0.0, linear("#6f625a")
    stops[1].position, stops[1].color = 1.0, linear("#a9b2b8")
    for at, colour in ((0.36, "#d9bfa4"), (0.52, "#f2dcc0"), (0.72, "#cfd0ce")):
        stops.new(at).color = linear(colour)
    links.new(span.outputs["Result"], ramp.inputs["Fac"])
    glow = nodes.new("ShaderNodeEmission")
    glow.inputs["Strength"].default_value = 1.15
    links.new(ramp.outputs["Color"], glow.inputs["Color"])
    links.new(glow.outputs[0], nodes["Material Output"].inputs["Surface"])
    return mat


box((-2.9, OUTSIDE, 0.3), (4.2, 0.02, 8.0 if TALL else 4.6), sky(), 0)   # a tall window sees higher
roofs = [material(f"roof{i}", "#000000", glow=c, strength=0.75) for i, c in enumerate(["#8d7566", "#a58d7c", "#6f5e55"])]
foliage = [material(f"far{i}", "#000000", glow=c, strength=0.55) for i, c in enumerate(["#56583f", "#6b6644", "#474a35"])]
for x, top, width in [(-2.35, -0.30, 0.52), (-1.78, -0.16, 0.30), (-1.34, -0.40, 0.44), (-0.92, -0.26, 0.30)]:
    box((x, 6.7, (top - 1.8) / 2), (width, 0.05, top + 1.8), roofs[rng.randrange(3)], 0.0)
for centre_x, centre_z, size in [(-2.05, -0.55, 0.34), (-1.55, -0.62, 0.30), (-1.12, -0.52, 0.26), (-2.55, -0.40, 0.30)]:
    for _ in range(70):
        angle, reach = rng.uniform(0, math.tau), rng.uniform(0.0, 1.0) ** 0.5 * size
        ball((centre_x + math.cos(angle) * reach, 6.3 + rng.uniform(-0.2, 0.2), centre_z + math.sin(angle) * reach * 0.85),
             rng.uniform(0.06, 0.11), foliage[rng.randrange(3)])


# ---------------------------------------------------------------- things
def book_stack(wall, s, d, z, count, width=0.19):
    top = z
    for i in range(count):
        thick = rng.uniform(0.024, 0.036)
        wide = width - i * 0.016
        wall.box((s - wide / 2, s + wide / 2), (d - 0.065, d + 0.065), (top, top + thick), books[(i * 3 + count) % 4],
                 turn=rng.uniform(-0.08, 0.08))
        top += thick
    return top


def plant(centre, pot_radius, pot_height, width, height, count):
    x, y, z = centre
    cylinder((x, y, z + pot_height / 2), pot_radius, pot_height, clay, bevel=0.018)
    for _ in range(count):
        angle, reach = rng.uniform(0, math.tau), rng.uniform(0.0, 1.0) ** 0.6
        up = rng.uniform(0.0, 1.0)
        spread = width * math.sin(math.pi * (0.18 + 0.72 * up))       # a rounded crown, not a ball
        at = (x + math.cos(angle) * reach * spread, y + math.sin(angle) * reach * spread * 0.6,
              z + pot_height + up * height)
        ball(at, rng.uniform(0.022, 0.040), leaves[rng.randrange(3)], squash=(1.0, 0.16, 0.52),
             turn=(rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), rng.uniform(0, math.tau)))


# by the window: a plant and two books on the sill
plant(window.at(0.78, 0.075, SILL), 0.058, 0.115, 0.105, 0.175, 120)
book_stack(window, 0.43, 0.075, SILL, 3, 0.17)

# the table, along the right wall
TABLE = -0.455                                                      # height of the table top, eye level is 0
side.box((0.22, 2.55), (0.03, 0.49), (TABLE - 0.042, TABLE), walnut, 0.008)
for s in (0.30, 2.45):
    for d in (0.08, 0.44):
        side.box((s - 0.022, s + 0.022), (d - 0.022, d + 0.022), (TABLE - 0.96, TABLE - 0.04), walnut, 0.006)

# a stone vase with a few dry stems, near the corner
vase = side.at(PROPS["vase"], 0.22, TABLE)
cylinder((vase[0], vase[1], TABLE + 0.085), 0.052, 0.17, stone, bevel=0.034)
cylinder((vase[0], vase[1], TABLE + 0.190), 0.020, 0.045, stone, bevel=0.006)
for lean_x, lean_z, length in [(-0.34, 0.10, 0.30), (-0.10, -0.05, 0.36), (0.16, 0.04, 0.31), (0.36, -0.10, 0.24)]:
    tip = (vase[0] + math.sin(lean_x) * length, vase[1] + lean_z * 0.2, TABLE + 0.20 + math.cos(lean_x) * length)
    cylinder(((vase[0] + tip[0]) / 2, (vase[1] + tip[1]) / 2, (TABLE + 0.20 + tip[2]) / 2), 0.0035, length, twig,
             turn=(0, lean_x, 0), sides=8, bevel=0.0)
    for _ in range(14):
        ball((tip[0] + rng.uniform(-0.03, 0.03), tip[1] + rng.uniform(-0.02, 0.02), tip[2] + rng.uniform(-0.045, 0.02)),
             rng.uniform(0.008, 0.015), seed_head, squash=(0.7, 0.7, 1.3))

# books with a small brass ball, then the lamp, whose light on the wall is most of what makes the room real
top = book_stack(side, PROPS["books"], 0.23, TABLE, 3, 0.21)
x, y, _ = side.at(PROPS["books"], 0.23, 0)
ball((x, y, top + 0.032), 0.032, brass)

LAMP_X, LAMP_Y, _ = side.at(PROPS["lamp"], 0.22, 0)
cylinder((LAMP_X, LAMP_Y, TABLE + 0.012), 0.078, 0.024, brass, bevel=0.008)
cylinder((LAMP_X, LAMP_Y, TABLE + 0.100), 0.048, 0.155, cream, bevel=0.030)
cylinder((LAMP_X, LAMP_Y, TABLE + 0.205), 0.007, 0.060, brass)
bpy.ops.mesh.primitive_cone_add(vertices=64, radius1=0.130, radius2=0.096, depth=0.175,
                                end_fill_type="NOTHING", location=(LAMP_X, LAMP_Y, TABLE + 0.298))
bpy.ops.object.shade_smooth()
place(bpy.context.object, shade)

# ---------------------------------------------------------------- light
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = linear("#2a1d16")
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.20


def area(at, towards, power, size, colour):
    lamp = bpy.data.lights.new("a", "AREA")
    lamp.energy, lamp.size, lamp.color = power * LIGHT, size, linear(colour)[:3]
    obj = bpy.data.objects.new("a", lamp)
    scene.collection.objects.link(obj)
    obj.location = at
    obj.rotation_euler = (Vector(towards) - Vector(at)).to_track_quat("-Z", "Y").to_euler()


area(window.at(0.85, 0.16, 0.30), side.at(0.9, 0.0, -0.35), 9.0, 0.75, "#eadccf")    # daylight coming in
area((-0.2, 1.7, 0.9), (-0.65, 3.4, -0.3), 4.0, 1.0, "#f6dac2")                      # lifts the sill and corner
area((0.1, 2.45, 0.70), side.at(0.95, 0.0, -0.05), 3.5, 0.55, "#f3d2bb")             # pool on the wall behind the head
area((0.0, 1.9, 0.35), (0.2, 2.9, -0.55), 2.2, 0.9, "#f1d3bd")                       # catches the table top
area((1.5, 1.6, 0.8), side.at(1.9, 0.0, -0.2), 3.0, 1.0, "#ddc9bc")                  # weak fill on the right

bulb = bpy.data.lights.new("bulb", "POINT")                         # spills out of the open shade, up and down
bulb.energy, bulb.color, bulb.shadow_soft_size = 5.5 * LIGHT, linear("#ffab5e")[:3], 0.035
holder = bpy.data.objects.new("bulb", bulb)
scene.collection.objects.link(holder)
holder.location = (LAMP_X, LAMP_Y, TABLE + 0.298)

# ---------------------------------------------------------------- camera
cam = bpy.data.cameras.new("c")
cam.lens, cam.sensor_width, cam.sensor_fit = 50.0, 36.0, "HORIZONTAL"
cam.shift_y = -(HEIGHT / 2 - EYE_ROW) / WIDTH                      # eye level on EYE_ROW (fit is horizontal)
cam.dof.use_dof = True
cam.dof.focus_distance = 0.85
cam.dof.aperture_fstop = FSTOP
cam.dof.aperture_blades = 9
camera = bpy.data.objects.new("c", cam)
scene.collection.objects.link(camera)
camera.rotation_euler = (math.pi / 2, -ROLL if MIRROR else ROLL, 0)
scene.camera = camera

# ---------------------------------------------------------------- render
scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
try:
    prefs.compute_device_type = "METAL"
    prefs.get_devices()
    for device in prefs.devices:
        device.use = True
    scene.cycles.device = "GPU"
except TypeError:
    pass   # not a Mac: Cycles stays on the processor
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.seed = 3
scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGB"
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = options.get("exposure", 0.80)
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
if MIRROR:   # flip the finished picture: the whole room, light included, swaps sides
    import numpy
    picture = bpy.data.images.load(OUT)
    pixels = numpy.empty(WIDTH * HEIGHT * 4, dtype=numpy.float32)
    picture.pixels.foreach_get(pixels)
    picture.pixels.foreach_set(pixels.reshape(HEIGHT, WIDTH, 4)[:, ::-1, :].ravel())
    picture.filepath_raw, picture.file_format = OUT, "PNG"
    picture.save()
print("studio set written:", OUT)
