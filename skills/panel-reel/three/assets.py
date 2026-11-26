"""Fetch the open-licence files the 3D scenes use, once, into ~/.cache/panel-reel/assets.

    python3 -I assets.py            (about 10 MB; every file is checked against a fixed checksum)

Fonts: Roboto (SIL OFL) and Roboto Slab (Apache 2.0) from google/fonts. Country outlines: Natural
Earth (public domain). Studio lighting: Poly Haven "studio_small_09" (CC0). None are stored in
the repository. REEL_ASSETS overrides the folder.
"""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path

ASSETS = Path(os.environ.get("REEL_ASSETS") or Path.home() / ".cache" / "panel-reel" / "assets")
FONTS = "https://raw.githubusercontent.com/google/fonts"
FILES = {
    "fonts/Roboto.ttf": (f"{FONTS}/1c627bfa375fc51cf86fabeca4f6e08a95f0aa5c/ofl/roboto/Roboto%5Bwdth%2Cwght%5D.ttf",
                         "d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134"),
    "fonts/RobotoSlab.ttf": (f"{FONTS}/369504809965ab8a0e467ad1f2d00ea07eefe1d0/apache/robotoslab/RobotoSlab%5Bwght%5D.ttf",
                             "786ae192477447d33c6672c3055fba7cbfe45184c9a79e77a14f15716ca05b16"),
    "geo/countries50.geojson": ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
                                "9380cca83db5f9aef52d5e762765100745f84b27/geojson/ne_50m_admin_0_countries.geojson",
                                "3e458fc036ad0a66411f2c1e6cac49c5d7bfb81cb1123bc513b22511a2b7fdeb"),
    "hdri/studio.hdr": ("https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/studio_small_09_2k.hdr",
                        "36724313c0fc66dab126ff90f081b85a0b1ef47be65eda1417bd20b033f0573f"),
}
# Blender cannot pick a weight from a variable font, so fixed weights are made from each
WEIGHTS = {"Roboto": ((500, 700, 900), {"wdth": 100}), "RobotoSlab": ((600, 700, 900), {})}
MAKE_WEIGHTS = """
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
source, out, axes = sys.argv[1], sys.argv[2], dict(a.split("=") for a in sys.argv[3:])
instantiateVariableFont(TTFont(source), {k: float(v) for k, v in axes.items()}).save(out)
"""


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for name, (url, wanted) in FILES.items():
        path = ASSETS / name
        if path.exists() and digest(path) == wanted:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        print("downloading", name)
        subprocess.run(["curl", "-fL", "--retry", "3", "-sS", "-A", "panel-reel-assets", "-o", str(partial), url],
                       check=True)
        if digest(partial) != wanted:
            partial.unlink()
            raise SystemExit(f"{name} is not the expected file; nothing was kept")
        partial.replace(path)
    for family, (weights, extra) in WEIGHTS.items():
        for weight in weights:
            out = ASSETS / "fonts" / f"{family}-{weight}.ttf"
            if out.exists():
                continue
            if not shutil.which("uv"):
                raise SystemExit("uv is needed to prepare the fonts (brew install uv)")
            axes = [f"{k}={v}" for k, v in {"wght": weight, **extra}.items()]
            subprocess.run(["uv", "run", "--no-project", "--python", "3.13", "--with", "fonttools==4.60.1", "python",
                            "-I", "-c", MAKE_WEIGHTS, str(ASSETS / "fonts" / f"{family}.ttf"), str(out), *axes],
                           check=True)
    print("assets ready in", ASSETS)


if __name__ == "__main__":
    main()
