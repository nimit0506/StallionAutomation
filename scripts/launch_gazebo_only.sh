#!/usr/bin/env bash
# =================================================================
#  launch_gazebo_only.sh — TERMINAL 1
#  Starts Gazebo server + GUI with Stallion VTOL world
#  After this starts, run launch_sitl_only.sh in a SECOND terminal
# =================================================================
set -e

# Repo root (override with STALLION_DIR=... if needed)
STALLION_DIR="${STALLION_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARDUPILOT_GZ_DIR="${ARDUPILOT_GZ_DIR:-${HOME}/ardupilot_gazebo}"
ARDUPILOT_GZ_BUILD="${ARDUPILOT_GZ_DIR}/build"

# ─── Verify ardupilot_gazebo plugin exists ──────────────────────
if [ ! -f "${ARDUPILOT_GZ_BUILD}/libArduPilotPlugin.so" ]; then
    echo "!!! ERROR: libArduPilotPlugin.so not found at ${ARDUPILOT_GZ_BUILD}"
    echo "    Build it with:"
    echo "      cd ~/ardupilot_gazebo && mkdir -p build && cd build"
    echo "      cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo && make -j$(nproc)"
    exit 1
fi

# ─── Gazebo Environment ────────────────────────────────────────
# Gazebo loads system plugins (libArduPilotPlugin.so) from GZ_SIM_SYSTEM_PLUGIN_PATH,
# and finds models (model://stallion_vtol) and worlds in GZ_SIM_RESOURCE_PATH.
export GZ_SIM_SYSTEM_PLUGIN_PATH="${ARDUPILOT_GZ_BUILD}:${GZ_SIM_SYSTEM_PLUGIN_PATH}"
export LD_LIBRARY_PATH="${ARDUPILOT_GZ_BUILD}:${LD_LIBRARY_PATH}"
export GZ_SIM_RESOURCE_PATH="${STALLION_DIR}/gazebo/models:${STALLION_DIR}/gazebo/worlds:${ARDUPILOT_GZ_DIR}/models:${GZ_SIM_RESOURCE_PATH}"

# ─── WSLg Display (for GUI window in WSL2) ─────────────────────
if grep -qi microsoft /proc/version 2>/dev/null; then
    export DISPLAY=:0
    export WAYLAND_DISPLAY=wayland-0
    export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir
    export PULSE_SERVER=unix:/mnt/wslg/PulseServer
    export LIBGL_ALWAYS_SOFTWARE=1
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

# -r = auto-run (no need to press play), -v 3 = verbose
gz sim -v 3 -r "${WORLD_FILE}"
