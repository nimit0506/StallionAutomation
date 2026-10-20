#!/usr/bin/env bash
# ============================================================================
# render_sim_images.sh  —  "Make simple 3D pictures of the airframe with OpenSCAD"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   Takes the 3D scene described in a .scad file and saves five pictures of it:
#   iso (three-quarter view), top, side, front and rear.
#   These are plain OpenSCAD renders. The Gazebo pictures in results/images/gazebo
#   come from gazebo_render_views.py instead, and are the ones used in the slides.
#
# KEY WORDS
#   OpenSCAD   : a free program that renders 3D scene files (.scad) to pictures.
#   Perspective: the far parts look smaller (like a real camera).
#   Orthographic: no size change with distance (like a technical drawing).
#   Camera position: where the viewer is, given as x,y,z in metres.
#
# HOW TO RUN IT
#   scripts/render_sim_images.sh                            (with pod, default folder)
#   scripts/render_sim_images.sh "$PWD/scripts/sim_model_nopod.scad" "$PWD/results/images/nopod"
#   On a machine with no screen, prefix with xvfb-run -a
#
# ARGUMENTS
#   $1 = the .scad scene file (default: scripts/sim_model.scad)
#   $2 = the output folder (default: results/images)
# ============================================================================

set -e            # stop at the first error

# The repository folder: the folder above this script's folder (scripts/)
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# ${1:-default} = use the first argument if given, otherwise the default
SCAD="${1:-$R/scripts/sim_model.scad}"
OUT="${2:-$R/results/images}"
mkdir -p "$OUT"                 # create the output folder if it does not exist
# The .scad files load their meshes with paths relative to their own folder,
# so we must run from scripts/ for those paths to work.
cd "$R/scripts"

# ----------------------------------------------------------------------------
# render <name> <camera x,y,z> <p or o>
#   name    : the picture's file name without .png
#   camera  : where the camera is (metres, relative to the origin of the scene)
#   p / o   : perspective (p) or orthographic (o) projection
# OpenSCAD options:
#   --imgsize       picture size in pixels
#   --colorscheme   Tomorrow = light background with clear colours
#   --viewall       move the camera so the whole model fits in the picture
#   --autocenter    centre the model in the picture
#   --camera        camera position (the three zeros are the look-at point's offset)
#   -o              output file
# ----------------------------------------------------------------------------
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
