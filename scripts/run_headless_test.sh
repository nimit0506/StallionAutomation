#!/usr/bin/env bash
# =================================================================
#  run_headless_test.sh — one-command automated flight test (no GUI)
#
#  Starts Gazebo (server only), ArduPlane SITL driven by the Gazebo
#  JSON physics, a MAVProxy bridge on UDP 14550, then runs
#  scripts/sitl_hover_check.py with the arguments you pass here.
#
#    scripts/run_headless_test.sh --transition --csv results/transition/log.csv
#    scripts/run_headless_test.sh --csv results/hover/log.csv
#
#  Needs (paths can be overridden with environment variables):
#    ARDUPILOT_DIR      ArduPilot source tree, built for SITL   (default ~/ardupilot)
#    ARDUPILOT_GZ_DIR   ardupilot_gazebo, built (libArduPilotPlugin.so)  (default ~/ardupilot_gazebo)
#    gz, mavproxy.py    on PATH (Gazebo Harmonic, MAVProxy)
#    python3 with pymavlink
#  Logs go to $LOG_DIR (default: logs/, git-ignored).
#  Exit code = exit code of sitl_hover_check.py (0 = PASS).
# =================================================================
set -u

R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARDUPILOT_DIR="${ARDUPILOT_DIR:-$HOME/ardupilot}"
ARDUPILOT_GZ_DIR="${ARDUPILOT_GZ_DIR:-$HOME/ardupilot_gazebo}"
LOG_DIR="${LOG_DIR:-$R/logs}"
WORLD="$R/gazebo/worlds/stallion_runway.sdf"
PARAMS="$R/params/stallion_vtol_sitl.parm"
SITL_BIN="$ARDUPILOT_DIR/build/sitl/bin/arduplane"

for f in "$SITL_BIN" "$ARDUPILOT_GZ_DIR/build/libArduPilotPlugin.so" "$WORLD" "$PARAMS"; do
    [ -e "$f" ] || { echo "!!! missing: $f"; exit 2; }
done
mkdir -p "$LOG_DIR"

stop_all() {
    pkill -9 -f "[g]z sim" 2>/dev/null
    pkill -9 -f "[b]in/arduplane" 2>/dev/null
    pkill -9 -f "[m]avproxy.py" 2>/dev/null
}
stop_all; sleep 1

export GZ_SIM_SYSTEM_PLUGIN_PATH="$ARDUPILOT_GZ_DIR/build"
export GZ_SIM_RESOURCE_PATH="$R/gazebo/models:$R/gazebo/worlds:$ARDUPILOT_GZ_DIR/models"
# On some Linux images Gazebo fails with a libsystemd symbol error; preloading the system copy fixes it.
[ -f /usr/lib/x86_64-linux-gnu/libsystemd.so.0 ] && export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libsystemd.so.0

# 1. Gazebo server, auto-run (-s = server only, -r = start running)
gz sim -s -r -v 3 "$WORLD" > "$LOG_DIR/gz.log" 2>&1 &
sleep 8

# 2. ArduPlane SITL: JSON physics from Gazebo, Chennai home, Stallion parameters
#    (run from LOG_DIR so the eeprom file lands there, not in the repo)
(
    cd "$LOG_DIR" && rm -f eeprom.bin && exec "$SITL_BIN" --model JSON --speedup 1 --slave 0 \
        --defaults "$ARDUPILOT_DIR/Tools/autotest/models/plane.parm,$PARAMS" \
        --home 13.0827,80.2707,10,90 -I0
) > "$LOG_DIR/sitl.log" 2>&1 &
sleep 5

# 3. MAVProxy: TCP 5760 (SITL) -> UDP 14550 (the check script)
(cd "$LOG_DIR" && exec mavproxy.py --master tcp:127.0.0.1:5760 --out udp:127.0.0.1:14550 \
    --daemon --non-interactive) > "$LOG_DIR/mavproxy.log" 2>&1 &
sleep 25

# Sometimes Gazebo and SITL start out of step: SITL then resends servos forever
# and nothing flies. Catch that here instead of waiting out the arming timeout.
if ! grep -q "JSON received" "$LOG_DIR/sitl.log"; then
    echo "!!! SITL is not getting physics from Gazebo (no 'JSON received' in $LOG_DIR/sitl.log). Re-run."
    stop_all
    exit 3
fi

# 4. The flight check (arming, climb, hold, optional transition, landing)
python3 "$R/scripts/sitl_hover_check.py" --connect udp:127.0.0.1:14550 "$@"
RC=$?

stop_all
exit $RC
