#!/usr/bin/env bash
# =================================================================
#  render_sim_images.sh — render the five model views used in the deck
#  Output: results/images/{iso,top,side,front,rear}.png
#  Usage:  scripts/render_sim_images.sh [SCAD_FILE] [OUT_DIR]
#          SCAD_FILE defaults to scripts/sim_model.scad (with pod).
#          Use scripts/sim_model_nopod.scad for the variant without the pod.
#  Needs: openscad (use xvfb-run -a if there is no display)
# =================================================================
set -e

# Repo root, found from this script's own location
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCAD="${1:-$R/scripts/sim_model.scad}"
OUT="${2:-$R/results/images}"
mkdir -p "$OUT"
cd "$R/scripts"   # the .scad files import meshes with paths relative to their own folder

# Render one view.
#   $1 = output name (without .png)
#   $2 = camera position x,y,z
#   $3 = p (perspective) or o (orthographic)
render() {
    openscad --imgsize=2400,1500 --colorscheme=Tomorrow --projection="$3" --viewall --autocenter \
        --camera="$2",0,0,0 -o "$OUT/$1.png" "$SCAD" >/dev/null 2>&1
    echo "wrote $OUT/$1.png"
}
render iso   1.2,-1.1,0.7  p     # three-quarter view from the front-left, above
render top   0.001,0,2     o     # straight down
render side  0,-2,0.0      o     # from the left side
render front 2,0,0.1       o     # from the nose
render rear  -1.5,0.9,0.5  p     # from behind and to the right
