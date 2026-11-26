"""Real geography for the map and the globe (Natural Earth, public domain)."""
import functools
import json
import math

import bmesh
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

import kit as K

@functools.lru_cache(maxsize=1)
def countries():
    data = json.loads((K.ASSETS / "geo" / "countries50.geojson").read_text())
    out = []
    for feature in data["features"]:
        geometry = feature["geometry"]
        polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
        out.append((feature["properties"].get("ADM0_A3"), polygons))
    return out


def _rings(code):
    polygons = next(p for c, p in countries() if c == code)
    return max(polygons, key=lambda p: len(p[0]))       # the mainland


def place(codes, width, latitude=None):
    """Outlines (ISO3 codes) as flat rings in set units, the first one `width` wide. Holes are kept,
    so a country that surrounds another leaves room for it."""
    shapes = [_rings(code) for code in codes]
    lons = [p[0] for p in shapes[0][0]]
    lats = [p[1] for p in shapes[0][0]]
    mx, my = (max(lons) + min(lons)) / 2, (max(lats) + min(lats)) / 2
    squeeze = math.cos(math.radians(my if latitude is None else latitude))
    scale = width / ((max(lons) - min(lons)) * squeeze)
    return [[[((lon - mx) * squeeze * scale, (lat - my) * scale) for lon, lat in ring[:-1]] for ring in rings]
            for rings in shapes]


def centre(rings):
    xs, ys = [p[0] for p in rings[0]], [p[1] for p in rings[0]]
    return (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2


def extrude(rings, thick, material, parent=None, location=(0, 0, 0)):
    """A country as a raised plate lying flat; further rings are holes."""
    bm = bmesh.new()
    flat_points = [p for ring in rings for p in ring]
    triangles = tessellate_polygon([[Vector((x, y, 0)) for x, y in ring] for ring in rings])
    top = [bm.verts.new((x, y, thick)) for x, y in flat_points]
    low = [bm.verts.new((x, y, 0)) for x, y in flat_points]
    for a, b, c in triangles:
        for face in ((top[a], top[b], top[c]), (low[c], low[b], low[a])):
            try:
                bm.faces.new(face)
            except ValueError:
                pass
    start = 0
    for ring in rings:
        n = len(ring)
        for i in range(n):
            a, b = start + i, start + (i + 1) % n
            bm.faces.new((low[a], low[b], top[b], top[a]))
        start += n
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return K.mesh_object("country", bm, material, location, parent, smooth=False)


def on_sphere(lon, lat, radius):
    lon, lat = math.radians(lon), math.radians(lat)
    return Vector((radius * math.cos(lat) * math.cos(lon), radius * math.cos(lat) * math.sin(lon),
                   radius * math.sin(lat)))


def _inside(x, y, ring):
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            hit = not hit
    return hit


@functools.lru_cache(maxsize=4)
def _land(density):
    shapes = []
    for code, polygons in countries():
        for polygon in polygons:
            ring = [tuple(p[:2]) for p in polygon[0]]
            xs, ys = [p[0] for p in ring], [p[1] for p in ring]
            shapes.append((min(xs), max(xs), min(ys), max(ys), ring, code))
    points = []
    golden = math.pi * (3 - math.sqrt(5))
    n = int(density * 2.9)          # about a third of the points fall on land
    for i in range(n):
        z = 1 - 2 * (i + 0.5) / n
        lat = math.degrees(math.asin(z))
        lon = math.degrees((i * golden) % (2 * math.pi)) - 180
        for x0, x1, y0, y1, ring, code in shapes:
            if x0 <= lon <= x1 and y0 <= lat <= y1 and _inside(lon, lat, ring):
                points.append((lon, lat))
                break
    return points


def dot_globe(radius, parent, location, density, dot, ocean, highlight=None):
    group = K.empty(location, parent)
    K.sphere(radius * 0.985, K.mat(ocean, rough=0.22, metal=0.3, coat=0.5), parent=group, detail=4)
    base = bmesh.new()
    bmesh.ops.create_icosphere(base, subdivisions=1, radius=dot)
    template = [v.co.copy() for v in base.verts]
    faces = [[v.index for v in f.verts] for f in base.faces]
    base.free()

    def cloud(points, size, lift, material):
        verts, polys = [], []
        for lon, lat in points:
            at = on_sphere(lon, lat, radius * lift)
            offset = len(verts)
            verts += [at + co * size for co in template]
            polys += [[offset + i for i in f] for f in faces]
        import bpy
        me = bpy.data.meshes.new("dots")
        me.from_pydata(verts, [], polys)
        me.materials.append(material)
        K.link(bpy.data.objects.new("dots", me), group)
    cloud(_land(density), 1.0, 1.0, K.flat("#8d9ac8", 1.0))
    if highlight:       # the country itself, drawn densely enough to read
        ring = [tuple(p[:2]) for p in _rings(highlight)[0]]
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        step = max(0.22, max(max(xs) - min(xs), max(ys) - min(ys)) / 60)
        fine = [(min(xs) + i * step, min(ys) + j * step) for i in range(int((max(xs) - min(xs)) / step) + 2)
                for j in range(int((max(ys) - min(ys)) / step) + 2)]
        cloud([(x, y) for x, y in fine if _inside(x, y, ring)], 0.85, 1.012, K.flat(K.ORANGE, 1.4))
    return group
