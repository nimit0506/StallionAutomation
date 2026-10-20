#!/usr/bin/env bash
# =================================================================
#  render_sim_images.sh — render the five model views used in the deck
#  Output: results/images/{iso,top,side,front,rear}.png
#  Needs: openscad (xvfb-run if you have no display: xvfb-run -a scripts/render_sim_images.sh)
# =================================================================
set -e
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$R/results/images"
mkdir -p "$OUT"
cd "$R/scripts"

# usage: render <name> <camera x,y,z> <p=perspective|o=orthographic>
render() {
    openscad --imgsize=2400,1500 --colorscheme=Tomorrow --projection="$3" --viewall --autocenter \
        --camera="$2",0,0,0 -o "$OUT/$1.png" sim_model.scad >/dev/null 2>&1
    echo "wrote $OUT/$1.png"
}
render iso   1.2,-1.1,0.7  p
render top   0.001,0,2     o
render side  0,-2,0.0      o
render front 2,0,0.1       o
render rear  -1.5,0.9,0.5  p
