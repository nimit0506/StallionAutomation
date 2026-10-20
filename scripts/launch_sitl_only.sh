#!/usr/bin/env bash
# =================================================================
#  launch_sitl_only.sh — TERMINAL 2
#  Starts ArduPlane SITL connected to Gazebo via JSON FDM
#  Run this AFTER Gazebo is already running (launch_gazebo_only.sh)
# =================================================================
set -e

# Repo root (override with STALLION_DIR=... if needed)
STALLION_DIR="${STALLION_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ARDUPILOT_DIR="${ARDUPILOT_DIR:-${HOME}/ardupilot}"
PARAM_FILE="${STALLION_DIR}/params/stallion_vtol_sitl.parm"

# ─── Verify ArduPilot source exists ────────────────────────────
if [ ! -d "${ARDUPILOT_DIR}" ]; then
    echo "!!! ERROR: ArduPilot source not found at ${ARDUPILOT_DIR}"
    echo "    Clone with: git clone https://github.com/ArduPilot/ardupilot.git"
    exit 1
fi

if [ ! -f "${PARAM_FILE}" ]; then
    echo "!!! ERROR: Parameter file not found at ${PARAM_FILE}"
    exit 1
fi

# Delete stale param cache to force fresh load
rm -f "${ARDUPILOT_DIR}/mav.parm" ./mav.parm 2>/dev/null

# Windows host IP for Mission Planner UDP connection
# Windows host IP for Mission Planner (WSL only; plain Linux uses localhost)
if grep -qi microsoft /proc/version 2>/dev/null; then
    WINDOWS_HOST=$(ip route show default | awk '/default/ {print $3}' | head -1)
else
    WINDOWS_HOST=127.0.0.1
fi

echo ""
echo "============================================="
echo " TERMINAL 2: ArduPlane SITL (JSON → Gazebo)"
echo "============================================="
echo " Location  : Chennai (13.0827 N, 80.2707 E)"
echo " Frame     : JSON (physics from Gazebo)"
echo " Params    : ${PARAM_FILE}"
echo " UDP out   : ${WINDOWS_HOST}:14550 (Mission Planner)"
echo "============================================="
echo ""
echo ">>> IMPORTANT: Make sure Gazebo is already running!"
echo ">>> Connect Mission Planner to UDP ${WINDOWS_HOST}:14550"
echo ""
echo ">>> After MAVProxy starts, test hover with:"
echo ">>>   mode QHOVER"
echo ">>>   arm throttle"
echo ">>>   rc 3 1600"
echo ""

cd "${ARDUPILOT_DIR}"

# -f JSON tells SITL to use Gazebo's JSON FDM physics backend
# -w wipes eeprom (add -w flag below on FIRST RUN to force param reload)
# sim_vehicle.py starts ArduPlane SITL and MAVProxy together:
#   -v ArduPlane            the vehicle type (ArduPlane firmware, which includes QuadPlane)
#   -f JSON                 physics comes from Gazebo over JSON (not the built-in simulator)
#   -w                      wipe the EEPROM so the parameter file is loaded fresh
#   --custom-location       Chennai home position and heading (lat, lon, alt, heading)
#   --add-param-file        the Stallion parameters, loaded on top of the defaults
#   --out                   send telemetry to Mission Planner (WINDOWS_HOST) and to localhost
#   --console / --map       open the MAVProxy console and the map window
python3 Tools/autotest/sim_vehicle.py \
    -v ArduPlane \
    -f JSON \
    -w \
    --custom-location="13.0827,80.2707,10,90" \
    --add-param-file="${PARAM_FILE}" \
    --out=udpout:${WINDOWS_HOST}:14550 \
    --out=udpout:127.0.0.1:14550 \
    --console \
    --map
