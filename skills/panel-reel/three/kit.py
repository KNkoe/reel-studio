"""Stage, materials, shapes, motion and the scene registry for explainer scenes (Blender 5, EEVEE).

Layout is written in picture pixels: P(px, py, depth) is the world point that appears near
pixel (px, py) when depth is 0. 100 px = 1 unit. The floor is the row FLOOR.
"""
import math
import os
import pathlib

import bpy
import bmesh
from mathutils import Vector

ASSETS = pathlib.Path(os.environ.get("REEL_ASSETS") or pathlib.Path.home() / ".cache" / "panel-reel" / "assets")
W = 1080
DIST = 26.0          # camera distance
LIFT = 5.2           # camera height above the floor line, in units

# default palette: a dark set, one warm accent, a calm blue. Scenes may use their own colours.
ORANGE, ORANGE_SOFT = "#f86923", "#ffd9c4"
CHARCOAL, INK2 = "#232733", "#4b5060"
FLAG, FLAG_SOFT = "#5b74f0", "#c9d2fb"
CLEAR, GAP = "#2f9a6c", "#8a93a6"
WHITE, GOLD = "#f4f5f8", "#f2b33d"
NIGHT_TOP, NIGHT_LOW = "#0b0d14", "#222a41"


# "split" scenes sit above the speaker's card: 1080x1520, keep content above row 930.
# "full" scenes take the whole frame: 1080x1920, keep content above row 1330 for captions.
SPLIT = (1520, 925)          # picture height, floor row
FULL = (1920, 1330)
SCENES = {}


def scene(name, start, end, shape):
    """Register build(c, length) for the seconds start..end of the edit; c(t) is t within the scene."""
    def register(fn):
        SCENES[name] = (start, end, shape, fn)
        return fn
    return register


class S:
    """The scene being built."""
    h = 1520
    floor = 1000
    fps = 30
    updates = []


def lin(hex_colour, alpha=1.0):
    c = hex_colour.lstrip("#")
    out = []
    for i in (0, 2, 4):
        v = int(c[i:i + 2], 16) / 255
        out.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    return (*out, alpha)


def P(px, py, depth=0.0):
    """The world point at `depth` that the resting camera sees at picture pixel (px, py)."""
    s = DIST / (DIST + depth)
    horizon = S.floor - LIFT * 100
    return Vector(((px - W / 2) / 100 / s, depth, LIFT - (py - horizon) / 100 / s))


def F(px, depth=0.0, z=0.0):
    """A point on the floor (or z above it) at `depth` that appears at column px."""
    return Vector(((px - W / 2) / 100 * (DIST + depth) / DIST, depth, z))


def front(px, row, z=0.45):
    """The point z above the floor that appears at picture row `row`: how far forward it must come."""
    horizon = S.floor - LIFT * 100
    s = (row - horizon) / ((LIFT - z) * 100)
    return Vector(((px - W / 2) / 100 / s, DIST / s - DIST, z))


# ---------------------------------------------------------------- motion
def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def seg(t, start, length):
    """0..1 while t moves through [start, start+length]."""
    return clamp((t - start) / max(1e-6, length))


def out3(x):
    return 1 - (1 - x) ** 3


def inout(x):
    return x * x * (3 - 2 * x)


def back(x, s=1.5):
    x -= 1
    return 1 + x * x * ((s + 1) * x + s)


def mix(a, b, x):
    return a + (b - a) * x


def vmix(a, b, x):
    return a.lerp(b, x)


def anim(fn):
    """Register fn(t seconds) to run for every frame."""
    S.updates.append(fn)
    return fn


def pop(obj, start, length=0.5, base=None, leave=None):
    """Scale in with a small overshoot (and out again at `leave`)."""
    base = Vector(base if base is not None else obj.scale)

    def step(t):
        k = back(seg(t, start, length)) if t >= start else 0.0
        if leave is not None and t > leave:
            k *= 1 - inout(seg(t, leave, 0.3))
        obj.scale = base * max(k, 0.0001)
        visible(obj, k > 0.001)
    anim(step)
    return obj


def rise(obj, start, length=0.6, drop=2.0):
    """Come up into place from below."""
    home = obj.location.copy()

    def step(t):
        k = out3(seg(t, start, length))
        obj.location = home - Vector((0, 0, drop * (1 - k)))
        visible(obj, t >= start)
    anim(step)
    return obj


def visible(obj, on):
    for o in (obj, *obj.children_recursive):
        o.hide_render = not on
        o.hide_viewport = not on


def bob(obj, amount=0.08, speed=1.1, phase=0.0, sway=0.0):
    """A slow float, applied on top of whatever else moves the object."""
    state = {}

    def step(t):
        base_z = state.get("z")
        if base_z is None:
            base_z = state["z"] = obj.location.z
            state["rz"] = obj.rotation_euler.z
        obj.location.z = base_z + amount * math.sin(t * speed + phase)
        if sway:
            obj.rotation_euler.z = state["rz"] + sway * math.sin(t * speed * 0.7 + phase)
    anim(step)
    return obj


# ---------------------------------------------------------------- materials
_materials = {}


def mat(colour, rough=0.35, metal=0.0, emit=0.0, alpha=1.0, coat=0.0, name=None):
    key = (colour, rough, metal, emit, alpha, coat, name)
    if key in _materials:
        return _materials[key]
    m = bpy.data.materials.new(name or colour)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = lin(colour)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Coat Weight"].default_value = coat
    if emit:
        bsdf.inputs["Emission Color"].default_value = lin(colour)
        bsdf.inputs["Emission Strength"].default_value = emit
    if alpha < 1:
        bsdf.inputs["Alpha"].default_value = alpha
        m.surface_render_method = "BLENDED"
    _materials[key] = m
    return m


def flat(colour, strength=1.0):
    """A colour that ignores the lights: text and screens stay exactly on brand."""
    key = ("flat", colour, strength)
    if key in _materials:
        return _materials[key]
    m = bpy.data.materials.new("flat" + colour)
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    nodes.clear()
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = lin(colour)
    em.inputs["Strength"].default_value = strength
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(em.outputs["Emission"], out.inputs["Surface"])
    _materials[key] = m
    return m


def picture_mat(path):
    m = bpy.data.materials.new("photo")
    m.use_nodes = True
    nodes, links = m.node_tree.nodes, m.node_tree.links
    nodes.clear()
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(path))
    tex.interpolation = "Cubic"
    tex.extension = "EXTEND"
    em = nodes.new("ShaderNodeEmission")
    out = nodes.new("ShaderNodeOutputMaterial")
    links.new(tex.outputs["Color"], em.inputs["Color"])
    links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m, tex.image


# ---------------------------------------------------------------- shapes
def link(obj, parent=None):
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


def empty(location=(0, 0, 0), parent=None):
    o = bpy.data.objects.new("group", None)
    o.location = location
    return link(o, parent)


def mesh_object(name, bm, material, location=(0, 0, 0), parent=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(35))
    if material:
        me.materials.append(material)
    o = bpy.data.objects.new(name, me)
    o.location = location
    return link(o, parent)


def bevel(obj, width, segments=3):
    mod = obj.modifiers.new("bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.harden_normals = False
    return obj


def box(size, material, location=(0, 0, 0), round_=0.08, parent=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    o = mesh_object("box", bm, material, location, parent)
    if round_:
        bevel(o, min(round_, min(size) * 0.45), 4)
    return o


def slab(width, height, thick, material, radius=0.3, location=(0, 0, 0), parent=None):
    """An upright rounded card facing the camera."""
    bm = bmesh.new()
    pts, r = [], min(radius, width / 2 - 0.001, height / 2 - 0.001)
    for cx, cz, a0 in ((width / 2 - r, height / 2 - r, 0), (-width / 2 + r, height / 2 - r, 90),
                       (-width / 2 + r, -height / 2 + r, 180), (width / 2 - r, -height / 2 + r, 270)):
        for i in range(9):
            a = math.radians(a0 + 90 * i / 8)
            pts.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    front = [bm.verts.new((x, -thick / 2, z)) for x, z in pts]
    rear = [bm.verts.new((x, thick / 2, z)) for x, z in pts]
    bm.faces.new(front)
    bm.faces.new(list(reversed(rear)))
    n = len(pts)
    for i in range(n):
        bm.faces.new((front[i], rear[i], rear[(i + 1) % n], front[(i + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_object("slab", bm, material, location, parent)
    bevel(o, min(0.05, thick * 0.4), 2)
    return o


def cylinder(radius, depth, material, location=(0, 0, 0), parent=None, sides=64, round_=0.05, axis="Z"):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=sides, radius1=radius, radius2=radius, depth=depth)
    if axis == "Y":
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=__import__("mathutils").Matrix.Rotation(math.pi / 2, 3, "X"))
    elif axis == "X":
        bmesh.ops.rotate(bm, verts=bm.verts, matrix=__import__("mathutils").Matrix.Rotation(math.pi / 2, 3, "Y"))
    o = mesh_object("cyl", bm, material, location, parent)
    if round_:
        bevel(o, round_, 3)
    return o


def sphere(radius, material, location=(0, 0, 0), parent=None, detail=3):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=detail + 1, radius=radius)
    o = mesh_object("sphere", bm, material, location, parent)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def torus(radius, tube, material, location=(0, 0, 0), parent=None, rings=96, sides=24, upright=True):
    bm = bmesh.new()
    verts = []
    for i in range(rings):
        a = 2 * math.pi * i / rings
        row = []
        for j in range(sides):
            b = 2 * math.pi * j / sides
            r = radius + tube * math.cos(b)
            x, y, z = r * math.cos(a), r * math.sin(a), tube * math.sin(b)
            row.append(bm.verts.new((x, -z, y) if upright else (x, y, z)))
        verts.append(row)
    for i in range(rings):
        for j in range(sides):
            bm.faces.new((verts[i][j], verts[(i + 1) % rings][j], verts[(i + 1) % rings][(j + 1) % sides],
                          verts[i][(j + 1) % sides]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_object("torus", bm, material, location, parent)


def prism(points, thick, material, location=(0, 0, 0), parent=None, round_=0.06):
    """Extrude a flat outline (x, z) towards the camera."""
    bm = bmesh.new()
    front = [bm.verts.new((x, -thick / 2, z)) for x, z in points]
    rear = [bm.verts.new((x, thick / 2, z)) for x, z in points]
    bm.faces.new(front)
    bm.faces.new(list(reversed(rear)))
    n = len(points)
    for i in range(n):
        bm.faces.new((front[i], rear[i], rear[(i + 1) % n], front[(i + 1) % n]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_object("prism", bm, material, location, parent, smooth=False)
    if round_:
        bevel(o, round_, 3)
    return o


def lathe(profile, material, location=(0, 0, 0), parent=None, sides=72):
    """Spin a (radius, height) outline around the vertical axis."""
    bm = bmesh.new()
    rows = []
    for r, z in profile:
        rows.append([bm.verts.new((r * math.cos(2 * math.pi * i / sides), r * math.sin(2 * math.pi * i / sides), z))
                     for i in range(sides)])
    for a, b in zip(rows, rows[1:]):
        for i in range(sides):
            bm.faces.new((a[i], a[(i + 1) % sides], b[(i + 1) % sides], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_object("lathe", bm, material, location, parent)


def tube(points, radius, material, parent=None, smooth=True):
    """A round cable through the points. Grow it with obj.data.bevel_factor_end."""
    curve = bpy.data.curves.new("tube", "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth = radius
    curve.bevel_resolution = 6
    curve.use_fill_caps = True
    spline = curve.splines.new("BEZIER" if smooth else "POLY")
    if smooth:
        spline.bezier_points.add(len(points) - 1)
        for p, co in zip(spline.bezier_points, points):
            p.co = co
            p.handle_left_type = p.handle_right_type = "AUTO"
    else:
        spline.points.add(len(points) - 1)
        for p, co in zip(spline.points, points):
            p.co = (*co, 1)
    curve.materials.append(material)
    o = bpy.data.objects.new("tube", curve)
    return link(o, parent)


def along(points, k):
    """A point k of the way along a smooth path through `points` (Catmull-Rom)."""
    n = len(points) - 1
    i = min(int(k * n), n - 1)
    u = k * n - i
    p0, p1, p2, p3 = (points[max(0, i - 1)], points[i], points[i + 1], points[min(n, i + 2)])
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)


_fonts = {}


def font(name, weight):
    key = (name, weight)
    if key not in _fonts:
        # instanced ahead of time (see fonts.py): Blender cannot pick a weight from a variable font
        _fonts[key] = bpy.data.fonts.load(str(ASSETS / "fonts" / f"{name}-{weight}.ttf"))
    return _fonts[key]


def text(body, size, material, location=(0, 0, 0), parent=None, face="slab", weight=700, thick=0.08,
         align="CENTER", maxw=None, spacing=1.0, edge=None):
    """Upright extruded text facing the camera. size is the letter height in picture pixels."""
    curve = bpy.data.curves.new("text", "FONT")
    curve.body = body
    curve.font = font("RobotoSlab" if face == "slab" else "Roboto", weight)
    curve.size = size / 100 / 0.72      # cap height is about 0.72 of the font size
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.extrude = thick / 2
    curve.bevel_depth = (0.006 if face == "slab" else 0.0015) if edge is None else edge
    curve.bevel_resolution = 2
    curve.space_line = spacing
    curve.materials.append(material)
    o = bpy.data.objects.new("text", curve)
    o.location = location
    o.rotation_euler = (math.pi / 2, 0, 0)
    link(o, parent)
    if maxw:
        bpy.context.view_layer.update()
        width = o.dimensions.x
        if width > maxw / 100:
            k = maxw / 100 / width
            curve.size *= k
    return o


# ---------------------------------------------------------------- stage
def stage(height, floor, accent=ORANGE, second=FLAG, dust=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _materials.clear()
    _fonts.clear()
    S.h, S.floor, S.updates = height, floor, []
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = W, height
    sc.render.fps = S.fps
    sc.eevee.taa_render_samples = 16
    sc.eevee.use_raytracing = True
    sc.eevee.ray_tracing_options.resolution_scale = "4"
    sc.eevee.use_shadows = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.compression = 15
    sc.render.dither_intensity = 1.0

    cam_data = bpy.data.cameras.new("camera")
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.sensor_width = 36
    cam_data.lens = 36 * DIST / (W / 100)
    cam = link(bpy.data.objects.new("camera", cam_data))
    cam.location = (0, -DIST, LIFT)
    cam.rotation_euler = (math.pi / 2, 0, 0)
    cam_data.shift_y = (floor - height / 2 - LIFT * 100) / W
    sc.camera = cam
    cam_data.dof.use_dof = False
    S.cam = cam

    # sky: a quiet gradient in the picture, the studio HDRI only for reflections
    world = bpy.data.worlds.new("sky")
    sc.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputWorld")
    window = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    elements = ramp.color_ramp.elements
    horizon = 1 - floor / height
    elements[0].position, elements[0].color = 0.0, lin(NIGHT_TOP)
    elements[1].position, elements[1].color = min(0.97, horizon + 0.14), lin(NIGHT_LOW)
    top = elements.new(1.0)
    top.color = lin(NIGHT_TOP)
    links.new(window.outputs["Window"], sep.inputs[0])
    links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    backdrop = nodes.new("ShaderNodeBackground")
    links.new(ramp.outputs["Color"], backdrop.inputs["Color"])
    env = nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(ASSETS / "hdri" / "studio.hdr"))
    lightsky = nodes.new("ShaderNodeBackground")
    lightsky.inputs["Strength"].default_value = 0.85
    links.new(env.outputs["Color"], lightsky.inputs["Color"])
    path = nodes.new("ShaderNodeLightPath")
    pick = nodes.new("ShaderNodeMixShader")
    links.new(path.outputs["Is Camera Ray"], pick.inputs["Fac"])
    links.new(lightsky.outputs["Background"], pick.inputs[1])
    links.new(backdrop.outputs["Background"], pick.inputs[2])
    links.new(pick.outputs["Shader"], out.inputs["Surface"])

    # a dark polished floor that fades into the sky
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=60)
    floor_mat = bpy.data.materials.new("floor")
    floor_mat.use_nodes = True
    nt = floor_mat.node_tree
    nt.nodes.clear()
    # a fixed, faint mirror over a dark base: polished, without washing out at a low angle
    base = nt.nodes.new("ShaderNodeBsdfDiffuse")
    base.inputs["Color"].default_value = lin("#10131f")
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Color"].default_value = (0.055, 0.058, 0.068, 1.0)
    gloss.inputs["Roughness"].default_value = 0.2
    both = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(base.outputs["BSDF"], both.inputs[0])
    nt.links.new(gloss.outputs["BSDF"], both.inputs[1])
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dist = nt.nodes.new("ShaderNodeVectorMath")
    dist.operation = "LENGTH"
    nt.links.new(geo.outputs["Position"], dist.inputs[0])
    fade = nt.nodes.new("ShaderNodeMapRange")
    fade.inputs["From Min"].default_value = 7
    fade.inputs["From Max"].default_value = 26
    nt.links.new(dist.outputs["Value"], fade.inputs["Value"])
    clear = nt.nodes.new("ShaderNodeBsdfTransparent")
    blend = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(fade.outputs["Result"], blend.inputs["Fac"])
    nt.links.new(both.outputs["Shader"], blend.inputs[1])
    nt.links.new(clear.outputs["BSDF"], blend.inputs[2])
    out_floor = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(blend.outputs["Shader"], out_floor.inputs["Surface"])
    floor_mat.surface_render_method = "DITHERED"
    mesh_object("floor", bm, floor_mat, (0, 0, -0.01), smooth=False)

    def area(location, colour, power, size, aim=(0, 0, 3)):
        data = bpy.data.lights.new("area", "AREA")
        data.energy, data.size, data.color = power, size, lin(colour)[:3]
        o = link(bpy.data.objects.new("area", data))
        o.location = location
        o.rotation_euler = (Vector(aim) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        return o

    area((-9, -11, 13), "#fff1e6", 1500, 7)
    area((12, -4, 5), second, 900, 4)
    area((-10, 6, 4), accent, 900, 4)
    area((2, 8, 12), "#ffffff", 700, 5)

    if dust:            # slow motes in the distance give the depth something to read against
        import random
        rnd = random.Random(7)
        motes = []
        for i in range(70):
            m = sphere(rnd.uniform(0.012, 0.035), flat(rnd.choice((accent, second, "#ffffff")), rnd.uniform(0.5, 1.4)),
                       (rnd.uniform(-9, 9), rnd.uniform(5, 14), rnd.uniform(0.4, 12)), detail=1)
            motes.append((m, m.location.copy(), rnd.uniform(0.05, 0.18), rnd.uniform(0, 6)))

        def drift(t):
            for m, home, speed, phase in motes:
                m.location = home + Vector((0.25 * math.sin(t * speed * 3 + phase), 0, speed * t % 3))
        anim(drift)
    return sc


def camera_move(duration, push=0.06, swing=0.045):
    """A slow dolly in with a slight orbit about the middle of the set."""
    cam = S.cam
    focus_z = (S.floor - S.h * 0.46) / 100
    shift = cam.data.shift_y

    def step(t):
        k = inout(clamp(t / duration))
        angle = swing * (k - 0.5) * 2
        dist = DIST * (1 + push * (1 - k) - push * 0.35)
        cam.location = (math.sin(angle) * dist, -math.cos(angle) * dist, LIFT)
        cam.rotation_euler = (math.pi / 2, 0, angle)
        # keep the middle of the set at the same height in the picture while the distance changes
        offset = (focus_z - LIFT) * 100 / W
        cam.data.shift_y = shift + offset * (DIST / dist - 1)
    anim(step)


def render(duration, out, stills=None, every=1):
    sc = bpy.context.scene
    total = max(1, round(duration * S.fps))
    sc.frame_start, sc.frame_end = 0, total - 1
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)

    def step(frame):
        t = frame / S.fps
        sc.frame_set(frame)
        for fn in S.updates:
            fn(t)
    if stills is not None:
        wanted = [min(total - 1, round(t * S.fps)) for t in stills]
    else:
        wanted = range(0, total, every)
    for f in wanted:
        target = out / f"{f:05d}.png"
        if stills is None and target.exists():
            continue
        step(f)
        sc.render.filepath = str(target.with_suffix(".part.png"))
        bpy.ops.render.render(write_still=True)
        target.with_suffix(".part.png").replace(target)
    print("rendered", len(list(wanted)), "of", total, "into", out)
