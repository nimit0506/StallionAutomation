#!/usr/bin/env bash
# ============================================================================
# run_headless_test.sh  —  "Start the whole simulation by itself and run the flight test"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   A flight test needs four programs running together:
#     1. Gazebo        : the physics simulator (the air, gravity, the aircraft's body).
#     2. ArduPlane SITL: the real autopilot software, running on this computer.
#                        SITL = Software In The Loop. It thinks it is flying a real plane.
#     3. MAVProxy      : a message relay. It takes the autopilot's messages on TCP port
#                        5760 and re-sends them on UDP port 14550, where our test reads them.
#     4. sitl_hover_check.py : the automatic pilot-and-examiner that flies and grades the test.
#   "Headless" means there is no window on screen. Everything runs in the background.
#   This script starts all four in the right order, runs the test, then stops them.
#
# KEY WORDS
#   TCP / UDP  : two ways of sending data over a network. Here both are local (127.0.0.1 = this computer).
#   JSON FDM   : the link between Gazebo and the autopilot. Gazebo sends sensor data;
#                the autopilot sends back motor and servo commands (port 9002).
#   Lock-step  : Gazebo waits for the autopilot each step, so results do not depend on speed.
#   Environment variable: a named setting, such as WORLD=..., that a script reads.
#
# HOW TO RUN IT
#   scripts/run_headless_test.sh --csv results/hover/hover_log.csv
#   scripts/run_headless_test.sh --transition --climb-time 30 --climb-throttle 1800 --csv log.csv
#   WORLD=gazebo/worlds/stallion_runway_nopod.sdf scripts/run_headless_test.sh --csv nopod.csv
#   Everything after the script name is passed on to sitl_hover_check.py.
#
# NEEDS (set these with environment variables if your install is elsewhere)
#   ARDUPILOT_DIR     the ArduPilot source folder, built for SITL   (default ~/ardupilot)
#   ARDUPILOT_GZ_DIR  the ardupilot_gazebo folder with libArduPilotPlugin.so (default ~/ardupilot_gazebo)
#   WORLD             the Gazebo world file (default: the with-pod world)
#   LOG_DIR           where logs go (default: logs/, ignored by git)
#   gz, mavproxy.py   must be on the PATH (Gazebo Harmonic and MAVProxy)
#   python3 with the pymavlink package
#
# EXIT CODE: 0 = the test passed; 1 = the test failed; 2 = a file is missing;
#            3 = the autopilot never received physics from Gazebo (try again).
# ============================================================================

set -u                 # stop with an error if a variable is used without a value

# ----------------------------------------------------------------------------
# 1. Settings. Each line uses a default unless you set the variable beforehand.
#    ${VAR:-default} means "use VAR if it is set and not empty, otherwise default".
# ----------------------------------------------------------------------------
# The repository folder: the folder above this script's own folder (scripts/)
R="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARDUPILOT_DIR="${ARDUPILOT_DIR:-$HOME/ardupilot}"
ARDUPILOT_GZ_DIR="${ARDUPILOT_GZ_DIR:-$HOME/ardupilot_gazebo}"
LOG_DIR="${LOG_DIR:-$R/logs}"
WORLD="${WORLD:-$R/gazebo/worlds/stallion_runway.sdf}"
PARAMS="$R/params/stallion_vtol_sitl.parm"          # the Stallion's autopilot parameters
SITL_BIN="$ARDUPILOT_DIR/build/sitl/bin/arduplane"   # the ArduPlane program built for SITL

# ----------------------------------------------------------------------------
# 2. Check that everything we need exists. If not, stop now with a clear message.
# ----------------------------------------------------------------------------
for f in "$SITL_BIN" "$ARDUPILOT_GZ_DIR/build/libArduPilotPlugin.so" "$WORLD" "$PARAMS"; do
    [ -e "$f" ] || { echo "!!! missing: $f"; exit 2; }
done
mkdir -p "$LOG_DIR"       # create the log folder if it does not exist yet

# ----------------------------------------------------------------------------
# 3. Stop any simulator left running from an earlier attempt.
#    The [g] trick: "[g]z sim" matches "gz sim" but not the pkill command itself,
#    so pkill never kills its own script by accident.
# ----------------------------------------------------------------------------
stop_all() {
    pkill -9 -f "[g]z sim" 2>/dev/null
    pkill -9 -f "[b]in/arduplane" 2>/dev/null
    pkill -9 -f "[m]avproxy.py" 2>/dev/null
}
stop_all; sleep 1

# ----------------------------------------------------------------------------
# 4. Environment for Gazebo. These tell it where to find the aircraft
#    model files, the world files, and the ArduPilot plugin.
# ----------------------------------------------------------------------------
export GZ_SIM_SYSTEM_PLUGIN_PATH="$ARDUPILOT_GZ_DIR/build"
export GZ_SIM_RESOURCE_PATH="$R/gazebo/models:$R/gazebo/worlds:$ARDUPILOT_GZ_DIR/models"
# On some Linux images Gazebo fails with a libsystemd symbol error; preloading the system copy fixes it.
[ -f /usr/lib/x86_64-linux-gnu/libsystemd.so.0 ] && export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libsystemd.so.0

# ----------------------------------------------------------------------------
# 5. Start the four programs, in order. Each "sleep" gives the previous one
#    time to start before the next one needs it.
# ----------------------------------------------------------------------------
# 5a. Gazebo server, auto-run.
#     -s = server only (no window), -r = start running at once, -v 3 = detailed messages
gz sim -s -r -v 3 "$WORLD" > "$LOG_DIR/gz.log" 2>&1 &
sleep 8   # give the world time to load before the autopilot connects

# 5b. ArduPlane SITL: the autopilot.
#     --model JSON     : take the physics from Gazebo over the JSON link (not its own simulator)
#     --speedup 1      : run at real speed
#     --slave 0        : do not wait for an external clock
#     --defaults ...   : load ArduPlane's standard settings, then our Stallion settings on top
#     --home ...       : the take-off point: latitude, longitude, altitude, heading (Chennai)
#     -I0              : instance 0 (the first autopilot on this computer)
# It runs inside LOG_DIR so its EEPROM file (saved settings) stays out of the repo.
(
    cd "$LOG_DIR" && rm -f eeprom.bin && exec "$SITL_BIN" --model JSON --speedup 1 --slave 0 \
        --defaults "$ARDUPILOT_DIR/Tools/autotest/models/plane.parm,$PARAMS" \
        --home 13.0827,80.2707,10,90 -I0
) > "$LOG_DIR/sitl.log" 2>&1 &
sleep 5   # give the autopilot time to start

# 5c. MAVProxy: relays messages from the autopilot (TCP 5760) to our test (UDP 14550).
#     --daemon : run in the background, --non-interactive : no prompt
(cd "$LOG_DIR" && exec mavproxy.py --master tcp:127.0.0.1:5760 --out udp:127.0.0.1:14550 \
    --daemon --non-interactive) > "$LOG_DIR/mavproxy.log" 2>&1 &
sleep 25  # the autopilot needs time to start up and settle its sensors

# ----------------------------------------------------------------------------
# 6. Check that the autopilot is really receiving physics. Sometimes Gazebo and
#    the autopilot start out of step. Then the autopilot keeps sending commands
#    but gets no replies, and nothing flies. We detect that here, after about
#    30 seconds, instead of waiting for the long arming timeout.
# ----------------------------------------------------------------------------
if ! grep -q "JSON received" "$LOG_DIR/sitl.log"; then
    echo "!!! SITL is not getting physics from Gazebo (no 'JSON received' in $LOG_DIR/sitl.log). Re-run."
    stop_all
    exit 3
fi

# ----------------------------------------------------------------------------
# 7. Run the flight test. "$@" passes every argument of this script on to the test.
#    The test runs in the folder where you started this script, so relative
#    --csv paths end up where you expect.
# ----------------------------------------------------------------------------
python3 "$R/scripts/sitl_hover_check.py" --connect udp:127.0.0.1:14550 "$@"
RC=$?                  # remember the test's exit code (0 = pass)

# ----------------------------------------------------------------------------
# 8. Stop everything and pass the test's result back to the caller.
# ----------------------------------------------------------------------------
stop_all
exit $RC
