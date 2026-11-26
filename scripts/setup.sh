#!/bin/bash
# Check this Mac, link the editing skill into Claude Code and Codex, and test the scripts.
#
#   bash scripts/setup.sh             check what is installed (changes nothing)
#   bash scripts/setup.sh --install   install what Homebrew can
#   bash scripts/setup.sh --link      link the skill for Claude Code and Codex
#   bash scripts/setup.sh --test      compile every tool and render the room once (about 2 minutes)
set -uo pipefail
REPO="$(cd -P "$(dirname "$0")/.." && pwd)"
SCRIPTS="$REPO/skills/panel-reel/scripts"
BLENDER="$(command -v blender || echo /Applications/Blender.app/Contents/MacOS/Blender)"
mode="${1:-check}"
missing=0

have() { command -v "$1" >/dev/null 2>&1; }
report() { # name, test command, fix
  if eval "$2" >/dev/null 2>&1; then echo "  ok    $1"; else echo "  MISS  $1  ->  $3"; missing=$((missing + 1)); fi
}

if [ "$mode" = "--install" ]; then
  have brew || { echo "Install Homebrew first: https://brew.sh"; exit 1; }
  for formula in ffmpeg uv node; do have "$formula" || brew install "$formula"; done
  [ -x "$BLENDER" ] || brew install --cask blender
  echo "Xcode comes from the App Store; open it once to accept its licence."
  exit 0
fi

if [ "$mode" = "--link" ]; then
  for home in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
    mkdir -p "$home"
    target="$home/panel-reel"
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      echo "left alone (a real folder, not a link): $target"
      continue
    fi
    ln -sfn "$REPO/skills/panel-reel" "$target" && echo "linked $target -> $REPO/skills/panel-reel"
  done
  exit 0
fi

echo "Checking this Mac"
report "macOS 26 or later" '[ "$(sw_vers -productVersion | cut -d. -f1)" -ge 26 ]' "update macOS"
report "Apple silicon" '[ "$(uname -m)" = arm64 ]' "only tested on Apple silicon"
report "Swift compiler" 'swiftc --version' "install Xcode, then: sudo xcode-select -s /Applications/Xcode.app"
report "ffmpeg" 'have ffmpeg' "brew install ffmpeg"
report "ffmpeg VP9 encoder" 'ffmpeg -hide_banner -encoders | grep -q libvpx-vp9' "brew reinstall ffmpeg (needed for split-screen reels)"
report "uv" 'have uv' "brew install uv"
report "Node (npx)" 'have npx' "brew install node (needed for split-screen reels)"
report "Python 3" 'have python3' "comes with Xcode"
report "Blender" '[ -x "$BLENDER" ]' "brew install --cask blender"
report "skill linked for Claude Code" '[ "$(cd -P "$HOME/.claude/skills/panel-reel" && pwd)" = "$REPO/skills/panel-reel" ]' "bash scripts/setup.sh --link"
report "Clapless app code" '[ -f "$REPO/apps/clapless/Package.swift" ]' "git submodule update --init (see SETUP.md)"

if [ "$mode" = "--test" ]; then
  set -e
  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT
  echo "Compiling the Swift tools"
  for tool in "$SCRIPTS"/*.swift; do
    swiftc -O -suppress-warnings "$tool" -o "$work/$(basename "$tool" .swift)"
    echo "  ok    $(basename "$tool")"
  done
  echo "Checking the Python scripts"
  python3 -I - "$SCRIPTS" <<'EOF'
import ast, pathlib, sys
for path in sorted(pathlib.Path(sys.argv[1]).glob("*.py")):
    ast.parse(path.read_text(), str(path))
    print("  ok   ", path.name)
EOF
  echo "Rendering the room (small test)"
  echo '{"size": [270, 480], "eye_row": 234, "samples": 16, "mirror": true, "roll": 1.5}' > "$work/room.json"
  "$BLENDER" --background --factory-startup --python-exit-code 1 --python "$SCRIPTS/studio_set.py" \
    -- "$work/room.png" "$work/room.json" >/dev/null 2>&1
  [ -s "$work/room.png" ] && echo "  ok    studio_set.py"
  echo "Tests passed"
  exit 0
fi

[ "$missing" -eq 0 ] && echo "Everything is in place." || echo "$missing item(s) to fix."
exit 0
