"""Blender's side of render.py: draw one scene from a project's scene file.

    blender --background --factory-startup --python run.py -- <scenes.py> <scene> <out folder>
        [--stills 40,44] [--scale 80] [--every 15]
"""
import argparse
import importlib.util
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import bpy

import kit

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("scenes")
parser.add_argument("name")
parser.add_argument("out")
parser.add_argument("--stills", help="times on the edit's clock")
parser.add_argument("--scale", type=int, default=100)
parser.add_argument("--every", type=int, default=1)
options = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])

spec = importlib.util.spec_from_file_location("project_scenes", options.scenes)
spec.loader.exec_module(importlib.util.module_from_spec(spec))
if options.name not in kit.SCENES:
    raise SystemExit(f"no scene called {options.name}; there are: {', '.join(kit.SCENES)}")
start, end, (height, floor), build = kit.SCENES[options.name]
kit.stage(height, floor)
build(lambda t: t - start, end - start)
kit.camera_move(end - start)
bpy.context.scene.render.resolution_percentage = options.scale
stills = [float(v) - start for v in options.stills.split(",")] if options.stills else None
kit.render(end - start, options.out, stills=stills, every=options.every)
