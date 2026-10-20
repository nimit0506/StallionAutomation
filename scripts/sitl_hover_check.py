#!/usr/bin/env python3
# ============================================================================
# sitl_hover_check.py  —  "Fly the simulated aircraft automatically and grade it"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   This script acts as a pilot with a checklist. It talks to the autopilot
#   (ArduPilot, running as SITL = "software in the loop") and:
#     1. Switches it to a flight mode, arms the motors, and takes off.
#     2. Climbs, holds height, optionally flies forward (transition), comes
#        back to hover and lands.
#     3. Records altitude, attitude and servo values about 10 times a second.
#     4. Prints PASS or FAIL based on simple rules.
#
# KEY WORDS
#   MAVLink   : the language ground stations and autopilots use to talk.
#   Heartbeat : a short "I am alive" message sent by the autopilot every second.
#   Flight mode:
#     QHOVER  : quadplane hover (vertical flight, uses the motors)
#     FBWB    : fly-by-wire B, a fixed-wing mode that holds altitude (wings carry the aircraft)
#     QLAND   : quadplane land (descends vertically)
#   Arm       : enable the motors. The aircraft will spin up when throttle is applied.
#   RC override: we send throttle values ourselves instead of using a radio.
#   Attitude  : roll (wing tilt, left/right) and pitch (nose up/down), in degrees.
#   Ground speed / airspeed: how fast the aircraft moves over the ground / through the air.
#   PWM       : the 1000..2000 value used for throttle and servos (1000 = low/min).
#
# HOW TO RUN IT (Gazebo and SITL must already be running, see run_headless_test.sh)
#   python3 scripts/sitl_hover_check.py --connect udp:127.0.0.1:14550
#   python3 scripts/sitl_hover_check.py --transition --climb-time 30 --climb-throttle 1800 --csv log.csv
# ============================================================================

import argparse   # reads the command-line options
import math       # converts radians to degrees
import sys        # exits the program with a message
import time       # measures time for timeouts and logging

from pymavlink import mavutil   # the MAVLink library: connects to the autopilot

# ----------------------------------------------------------------------------
# Global settings. Other functions read and change these values.
# ----------------------------------------------------------------------------
PRINT_DT = 1.0      # seconds between console lines (one per second by default)
VERBOSE = False     # if True, also print airspeed and motor values
CSV = None          # the open log file, when --csv is given; None means no log
T0 = time.time()    # the moment the script started; CSV times are measured from here
PHASE = "init"      # name of the current flight part, written into every log row


def wait_heartbeat(m, timeout=60):
    """Wait until the autopilot sends its heartbeat (proof that it is alive).

    m       : the MAVLink connection.
    timeout : seconds to wait before giving up.
    """
    hb = m.wait_heartbeat(timeout=timeout)
    if hb is None:
        sys.exit("FAIL: no heartbeat from SITL")     # stop the program with a clear message
    print(f"Heartbeat from system {m.target_system}")


def set_mode(m, mode, timeout=10):
    """Ask the autopilot to change flight mode, and wait until it confirms.

    The request is sent once; then we listen to the heartbeats until the
    autopilot reports the new mode name, or until the timeout passes.
    """
    m.set_mode(mode)                                 # send the mode request
    t0 = time.time()
    while time.time() - t0 < timeout:
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=1)   # listen for 1 s
        if hb and mavutil.mode_string_v10(hb) == mode:                   # is it the mode we asked for?
            return
    sys.exit(f"FAIL: could not enter {mode}")


def rc_throttle(m, pwm):
    """Send a throttle value (PWM) to the autopilot as if it came from a radio.

    Channel 3 is the throttle. The other channels are released (0 = not overridden).
    The autopilot keeps using this value only for a short time, so we send it again
    in every loop of fly().
    """
    # Channel 3 override, others released (0 = no override, 65535 = ignore)
    m.mav.rc_channels_override_send(m.target_system, m.target_component,
                                    0, 0, pwm, 0, 0, 0, 0, 0)


def fly(m, seconds, throttle, log):
    """Keep sending a throttle value for `seconds`, and record what the aircraft does.

    m        : the MAVLink connection.
    seconds  : how long to fly with this throttle.
    throttle : throttle PWM (1000..2000) to send during this time.
    log      : a dictionary holding the latest measured values and the running maxima.
               This function updates it as new messages arrive.
    """
    t_end = time.time() + seconds
    while time.time() < t_end:
        rc_throttle(m, throttle)                     # keep the throttle command alive
        # Wait up to 0.2 s for any of the four message types we use
        msg = m.recv_match(type=["GLOBAL_POSITION_INT", "ATTITUDE", "VFR_HUD", "SERVO_OUTPUT_RAW", "GPS_RAW_INT"], blocking=True, timeout=0.2)
        if msg is None:
            continue
        # GPS altitude: the simulated GPS sensor, close to the true height. We log it next
        # to the autopilot's own estimate (alt), because the estimate can drift in forward
        # flight. The first GPS reading (aircraft on the ground) is taken as zero.
        if msg.get_type() == "GPS_RAW_INT":
            if msg.fix_type >= 3:                    # only use a proper 3D fix
                if "gps_home" not in log:
                    log["gps_home"] = msg.alt
                log["gps_alt"] = (msg.alt - log["gps_home"]) / 1000.0   # mm -> m, relative to take-off
            continue
        # Servo outputs: the PWM values the autopilot is sending to each servo and motor
        if msg.get_type() == "SERVO_OUTPUT_RAW":
            # servo4 = tilt, servo6 = aileron, servo7/8 = V-tail left/right; servo1-3 = motors
            log["servo"] = (msg.servo4_raw, msg.servo6_raw, msg.servo7_raw, msg.servo8_raw)
            log["motors"] = (msg.servo1_raw, msg.servo2_raw, msg.servo3_raw)
            continue
        # VFR_HUD: speeds. groundspeed = over the ground, airspeed = through the air (m/s)
        if msg.get_type() == "VFR_HUD":
            log["gs"] = msg.groundspeed
            log["aspd"] = msg.airspeed
            continue
        # ATTITUDE: roll and pitch arrive in radians; convert to degrees
        if msg.get_type() == "ATTITUDE":
            log["roll"] = math.degrees(msg.roll)
            log["pitch"] = math.degrees(msg.pitch)
            # Keep the largest tilt seen so far (roll or pitch, whichever is bigger)
            log["max_tilt"] = max(log["max_tilt"], abs(log["roll"]), abs(log["pitch"]))
        else:
            # GLOBAL_POSITION_INT: relative altitude is in millimetres; convert to metres
            log["alt"] = msg.relative_alt / 1000.0
            log["max_alt"] = max(log["max_alt"], log["alt"])
        now = time.time()
        # Write a line to the CSV log at most every 0.1 s (10 lines per second)
        if CSV and now - log.get("last_csv", 0) > 0.1:
            log["last_csv"] = now
            CSV.write(f"{now - T0:.2f},{PHASE},{log['alt']:.3f},{log['roll']:.2f},{log['pitch']:.2f},"
                      f"{log['gs']:.2f},{log['aspd']:.2f},{','.join(map(str, log['servo']))},"
                      f"{','.join(map(str, log['motors']))},{log.get('gps_alt', 0.0):.3f}\n")
        # Print a line to the screen at most every PRINT_DT seconds
        if now - log["last_print"] > PRINT_DT:
            log["last_print"] = now
            print(f"  alt={log['alt']:6.2f} m  roll={log['roll']:6.1f}  pitch={log['pitch']:6.1f}  gs={log['gs']:5.1f} m/s  "
                  f"tilt/ail/vtL/vtR={log['servo']}"
                  + (f"  aspd={log['aspd']:4.1f} mot={log['motors']}" if VERBOSE else ""))


def main():
    """The whole test, from reading the options to printing the verdict."""
    # ---- 1. Options ----
    ap = argparse.ArgumentParser(description="Automated flight test of the Stallion in Gazebo SITL.")
    ap.add_argument("--connect", default="udp:127.0.0.1:14550", help="MAVLink connection string")
    ap.add_argument("--climb-throttle", type=int, default=1700, help="throttle PWM during the climb")
    ap.add_argument("--hold-throttle", type=int, default=1500, help="throttle PWM during the hold")
    ap.add_argument("--min-alt", type=float, default=3.0, help="altitude needed to pass the hover test (m)")
    ap.add_argument("--max-tilt", type=float, default=25.0, help="largest roll or pitch allowed in hover (deg)")
    ap.add_argument("--transition", action="store_true",
                    help="after the hover climb, fly forward (FBWB) and check it, then land")
    ap.add_argument("--climb-time", type=float, default=10.0, help="seconds of climb before the hold")
    ap.add_argument("--verbose", action="store_true", help="also print airspeed and motor values")
    ap.add_argument("--csv", help="write a 10 Hz flight log (CSV) to this file")
    args = ap.parse_args()

    # Allow the helper functions to change these global values
    global PRINT_DT, VERBOSE, CSV, PHASE
    if args.csv:
        CSV = open(args.csv, "w", buffering=1)       # buffering=1: write each line straight away
        # column names (gps_alt = GPS height above take-off, the check against alt)
        CSV.write("t,phase,alt,roll,pitch,gs,aspd,tilt,ail,vtail_l,vtail_r,m_fr,m_fl,m_rear,gps_alt\n")
    if args.verbose:
        PRINT_DT, VERBOSE = 0.25, True               # print four times per second

    # ---- 2. Connect and check the autopilot is alive ----
    m = mavutil.mavlink_connection(args.connect)     # open the network connection
    wait_heartbeat(m)
    # Ask the autopilot to send all standard telemetry streams at 10 Hz
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)

    # ---- 3. Hover mode, zero throttle, then arm ----
    set_mode(m, "QHOVER")
    rc_throttle(m, 1000)                             # minimum throttle before arming
    print("Arming...")
    # The autopilot refuses to arm until its sensors agree. We keep trying for up to 3 minutes.
    t0 = time.time()
    last_try = 0
    while not m.motors_armed():
        if time.time() - last_try > 3:               # try again every 3 seconds
            last_try = time.time()
            m.arducopter_arm()                       # MAVLink command: arm the motors
        msg = m.recv_match(type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=1)
        if msg and msg.get_type() == "STATUSTEXT":   # print the autopilot's reason for refusing
            print(f"  [{msg.text}]")
        if time.time() - t0 > 180:
            sys.exit("FAIL: vehicle did not arm")
    print("Armed")

    # ---- 4. The flight. 'log' holds the latest readings for fly() to update ----
    log = {"alt": 0.0, "roll": 0.0, "pitch": 0.0, "max_alt": 0.0, "max_tilt": 0.0, "gs": 0.0, "servo": (0, 0, 0, 0), "motors": (0, 0, 0), "aspd": 0.0, "last_print": 0}
    PHASE = "climb"
    print(f"Climbing (throttle {args.climb_throttle})...")
    fly(m, args.climb_time, args.climb_throttle, log)
    PHASE = "hold"
    print(f"Holding (throttle {args.hold_throttle})...")
    fly(m, 10, args.hold_throttle, log)

    # ---- 5a. Optional forward flight and the way back ----
    if args.transition:
        PHASE = "forward"
        print("Transition to forward flight (FBWB, throttle 1800)...")
        set_mode(m, "FBWB")                          # wings take over; altitude hold
        log["max_tilt"] = 0.0                        # judge forward flight on its own numbers
        log["min_alt_fw"] = 1e9
        t_end = time.time() + 30                     # 30 seconds of forward flight
        max_gs = 0.0
        while time.time() < t_end:
            fly(m, 1, 1800, log)                     # one second at a time, tracking the extremes
            max_gs = max(max_gs, log["gs"])
            log["min_alt_fw"] = min(log["min_alt_fw"], log["alt"])
        # Forward flight passes if: reached 12 m/s, never below 2 m, and tilt within 45 degrees
        fw_ok = max_gs >= 12 and log["min_alt_fw"] > 2 and log["max_tilt"] <= 45
        print(f"\nforward flight: max_gs={max_gs:.1f} m/s  min_alt={log['min_alt_fw']:.1f} m  "
              f"max_tilt={log['max_tilt']:.1f} deg  -> {'PASS' if fw_ok else 'FAIL'}")
        print("Back to QHOVER, then QLAND...")
        PHASE = "back_transition"
        set_mode(m, "QHOVER")                        # rotors back to vertical
        fly(m, 15, 1500, log)
        PHASE = "land"
        set_mode(m, "QLAND")                         # land vertically
        fly(m, 120, 1500, log)                       # long window so the landing can finish
        landed = log["alt"] < 0.5                    # landed = below 0.5 m at the end
        print(f"landing: final alt={log['alt']:.2f} m -> {'LANDED' if landed else 'NOT LANDED'}")
        sys.exit(0 if fw_ok and landed else 1)       # exit code 0 = pass, 1 = fail

    # ---- 5b. Hover-only: land with a short window ----
    PHASE = "land"
    print("Landing (QLAND)...")
    set_mode(m, "QLAND")
    fly(m, 15, 1500, log)                            # short window: landing is NOT checked here

    # ---- 6. Verdict for the hover test ----
    # Pass if the aircraft reached the minimum height and never tilted beyond the limit
    ok = log["max_alt"] >= args.min_alt and log["max_tilt"] <= args.max_tilt
    print(f"\nmax_alt={log['max_alt']:.2f} m  max_tilt={log['max_tilt']:.1f} deg")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


# Run main() only when this file is started directly
if __name__ == "__main__":
    main()
