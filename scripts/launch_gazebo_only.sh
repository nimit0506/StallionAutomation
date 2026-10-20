#!/usr/bin/env bash
# ============================================================================
# launch_gazebo_only.sh  —  TERMINAL 1 of the manual (GUI) setup
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   Opens the Gazebo window with the Stallion runway world. You can watch the
#   aircraft, rotate the camera, and see its physics. The autopilot is NOT
#   started here: run launch_sitl_only.sh in a second terminal for that.
#
# KEY WORDS
#   gz sim   : the Gazebo simulator command.
#   -v 3     : verbose messages (level 3 = detailed).
#   -r       : run immediately (no need to press Play).
#   GUI      : the window with the 3D view and the control buttons.
#
# HOW TO RUN IT
#   bash scripts/launch_gazebo_only.sh
#   then, in a second terminal: bash scripts/launch_sitl_only.sh
#
# Override the folders with environment variables if your install is elsewhere:
#   STALLION_DIR, ARDUPILOT_GZ_DIR
# ============================================================================
set -e                      # stop the script at the first error

# Repo root: the folder above this script (scripts/). You can override it.
STALLION_DIR="${STALLION_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Where the ardupilot_gazebo plugin was built (default: ~/ardupilot_gazebo)
ARDUPILOT_GZ_DIR="${ARDUPILOT_GZ_DIR:-${HOME}/ardupilot_gazebo}"
ARDUPILOT_GZ_BUILD="${ARDUPILOT_GZ_DIR}/build"

# ─── Check that the plugin exists; if not, show how to build it ─────────────
if [ ! -f "${ARDUPILOT_GZ_BUILD}/libArduPilotPlugin.so" ]; then
    echo "!!! ERROR: libArduPilotPlugin.so not found at ${ARDUPILOT_GZ_BUILD}"
    echo "    Build it with:"
    echo "      cd ~/ardupilot_gazebo && mkdir -p build && cd build"
    echo "      cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo && make -j$(nproc)"
    exit 1
fi

# ─── Gazebo environment ──────────────────────────────────────────────────────
# Gazebo loads system plugins (libArduPilotPlugin.so) from GZ_SIM_SYSTEM_PLUGIN_PATH,
# and finds models (model://stallion_vtol) and worlds in GZ_SIM_RESOURCE_PATH.
export GZ_SIM_SYSTEM_PLUGIN_PATH="${ARDUPILOT_GZ_BUILD}:${GZ_SIM_SYSTEM_PLUGIN_PATH}"
export LD_LIBRARY_PATH="${ARDUPILOT_GZ_BUILD}:${LD_LIBRARY_PATH}"
export GZ_SIM_RESOURCE_PATH="${STALLION_DIR}/gazebo/models:${STALLION_DIR}/gazebo/worlds:${ARDUPILOT_GZ_DIR}/models:${GZ_SIM_RESOURCE_PATH}"

# ─── Windows (WSL) display settings: only used when running under WSL ───────
# /proc/version mentions "microsoft" on Windows Subsystem for Linux.
if grep -qi microsoft /proc/version 2>/dev/null; then
    export DISPLAY=:0
    export WAYLAND_DISPLAY=wayland-0
    export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
    export PULSE_SERVER=unix:/mnt/wslg/PulseServer
    export LIBGL_ALWAYS_SOFTWARE=1               # software graphics (no GPU needed)
    export MESA_GL_VERSION_OVERRIDE=4.5
    export MESA_GLSL_VERSION_OVERRIDE=450
fi

WORLD_FILE="${STALLION_DIR}/gazebo/worlds/stallion_runway.sdf"

echo ""
echo "============================================="
echo " TERMINAL 1: Gazebo Server + GUI"
echo "============================================="
echo " World  : ${WORLD_FILE}"
echo " Plugin : ${ARDUPILOT_GZ_BUILD}/libArduPilotPlugin.so"
echo " Models : ${STALLION_DIR}/gazebo/models"
echo "============================================="
echo ""
echo ">>> Starting Gazebo (verbose level 3, auto-run)..."
echo ">>> Drone model should appear on the ground plane."
echo ">>> Once running, open a 2nd terminal and run:"
echo ">>>   bash ${STALLION_DIR}/scripts/launch_sitl_only.sh"
echo ""

# -r = auto-run (no need to press play), -v 3 = verbose. This line stays running until you close Gazebo.
gz sim -v 3 -r "${WORLD_FILE}"
