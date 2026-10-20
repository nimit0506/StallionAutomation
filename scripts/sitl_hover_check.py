#!/usr/bin/env python3
"""
sitl_hover_check.py — automated hover test for the Stallion VTOL in Gazebo SITL.

Run with Gazebo + SITL already up (scripts/run_headless_test.sh starts both):
    python3 scripts/sitl_hover_check.py --connect udp:127.0.0.1:14550

Sequence: QHOVER -> arm -> climb with throttle -> hold -> QLAND.
With --transition: ... -> hold -> FBWB forward flight -> QHOVER -> QLAND.
Prints altitude/attitude while flying and a PASS/FAIL verdict at the end.
"""
import argparse
import math
import sys
import time

from pymavlink import mavutil

# Module-level state shared by the helper functions (set once in main())
PRINT_DT = 1.0      # seconds between console lines
VERBOSE = False     # also print airspeed and motor outputs
CSV = None          # open file when --csv is given
T0 = time.time()    # reference time for the CSV "t" column
PHASE = "init"      # current flight phase, written to the CSV


def wait_heartbeat(m, timeout=60):
    """Wait until the autopilot sends a heartbeat; exit if it never does."""
    hb = m.wait_heartbeat(timeout=timeout)
    if hb is None:
        sys.exit("FAIL: no heartbeat from SITL")
    print(f"Heartbeat from system {m.target_system}")


def set_mode(m, mode, timeout=10):
    """Request a flight mode and wait until the heartbeat confirms it."""
    m.set_mode(mode)
    t0 = time.time()
    while time.time() - t0 < timeout:
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb and mavutil.mode_string_v10(hb) == mode:
            return
    sys.exit(f"FAIL: could not enter {mode}")


def rc_throttle(m, pwm):
    """Override RC channel 3 (throttle) with a PWM value. Other channels are released (0)."""
    # Channel 3 override, others released (0 = no override, 65535 = ignore)
    m.mav.rc_channels_override_send(m.target_system, m.target_component,
                                    0, 0, pwm, 0, 0, 0, 0, 0)


def fly(m, seconds, throttle, log):
    """Hold a throttle for `seconds`, reading telemetry and updating `log` as it arrives.

    `log` is a dict that keeps the latest values plus running maxima:
    alt (m), roll/pitch (deg), gs (m/s), aspd (m/s), servo/motors (PWM), max_tilt, max_alt.
    """
    t_end = time.time() + seconds
    while time.time() < t_end:
        rc_throttle(m, throttle)   # re-send the throttle every loop; RC override expires otherwise
        msg = m.recv_match(type=["GLOBAL_POSITION_INT", "ATTITUDE", "VFR_HUD", "SERVO_OUTPUT_RAW"], blocking=True, timeout=0.2)
        if msg is None:
            continue
        if msg.get_type() == "SERVO_OUTPUT_RAW":
            # servo4 = tilt, servo6 = aileron, servo7/8 = V-tail L/R; servo1-3 = motors
            log["servo"] = (msg.servo4_raw, msg.servo6_raw, msg.servo7_raw, msg.servo8_raw)
            log["motors"] = (msg.servo1_raw, msg.servo2_raw, msg.servo3_raw)
            continue
        if msg.get_type() == "VFR_HUD":
            log["gs"] = msg.groundspeed
            log["aspd"] = msg.airspeed
            continue
        if msg.get_type() == "ATTITUDE":
            log["roll"] = math.degrees(msg.roll)
            log["pitch"] = math.degrees(msg.pitch)
            log["max_tilt"] = max(log["max_tilt"], abs(log["roll"]), abs(log["pitch"]))
        else:
            # GLOBAL_POSITION_INT: relative altitude in mm
            log["alt"] = msg.relative_alt / 1000.0
            log["max_alt"] = max(log["max_alt"], log["alt"])
        now = time.time()
        # Write a CSV row at most every 0.1 s (10 Hz)
        if CSV and now - log.get("last_csv", 0) > 0.1:
            log["last_csv"] = now
            CSV.write(f"{now - T0:.2f},{PHASE},{log['alt']:.3f},{log['roll']:.2f},{log['pitch']:.2f},"
                      f"{log['gs']:.2f},{log['aspd']:.2f},{','.join(map(str, log['servo']))},"
                      f"{','.join(map(str, log['motors']))}\n")
        # Console line at most every PRINT_DT seconds
        if now - log["last_print"] > PRINT_DT:
            log["last_print"] = now
            print(f"  alt={log['alt']:6.2f} m  roll={log['roll']:6.1f}  pitch={log['pitch']:6.1f}  gs={log['gs']:5.1f} m/s  "
                  f"tilt/ail/vtL/vtR={log['servo']}"
                  + (f"  aspd={log['aspd']:4.1f} mot={log['motors']}" if VERBOSE else ""))


def main():
    """Parse options, run the flight sequence, print the verdict, and set the exit code."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--connect", default="udp:127.0.0.1:14550", help="MAVLink connection string")
    ap.add_argument("--climb-throttle", type=int, default=1700, help="RC throttle PWM during the climb")
    ap.add_argument("--hold-throttle", type=int, default=1500, help="RC throttle PWM during the hold")
    ap.add_argument("--min-alt", type=float, default=3.0, help="altitude needed to pass (m)")
    ap.add_argument("--max-tilt", type=float, default=25.0, help="max roll/pitch allowed (deg)")
    ap.add_argument("--transition", action="store_true",
                    help="after the hover climb, transition to forward flight (FBWB, altitude hold) and check it flies")
    ap.add_argument("--climb-time", type=float, default=10.0, help="seconds of climb before the hold")
    ap.add_argument("--verbose", action="store_true", help="print 4x/s incl. airspeed and motor outputs")
    ap.add_argument("--csv", help="write a 10 Hz flight log (CSV) for plotting")
    args = ap.parse_args()
    global PRINT_DT, VERBOSE, CSV, PHASE
    if args.csv:
        CSV = open(args.csv, "w", buffering=1)   # line-buffered so a crash keeps the data so far
        CSV.write("t,phase,alt,roll,pitch,gs,aspd,tilt,ail,vtail_l,vtail_r,m_fr,m_fl,m_rear\n")
    if args.verbose:
        PRINT_DT, VERBOSE = 0.25, True

    m = mavutil.mavlink_connection(args.connect)
    wait_heartbeat(m)
    # Ask the autopilot for all telemetry streams at 10 Hz
    m.mav.request_data_stream_send(m.target_system, m.target_component,
                                   mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)

    # Hover mode with throttle at zero, then arm
    set_mode(m, "QHOVER")
    rc_throttle(m, 1000)
    print("Arming...")
    # Retry: pre-arm checks (EKF, IMU consistency) can take a while to settle after boot
    t0 = time.time()
    last_try = 0
    while not m.motors_armed():
        if time.time() - last_try > 3:
            last_try = time.time()
            m.arducopter_arm()               # MAV_CMD arm (works for ArduPlane too)
        msg = m.recv_match(type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=1)
        if msg and msg.get_type() == "STATUSTEXT":
            print(f"  [{msg.text}]")
        if time.time() - t0 > 180:
            sys.exit("FAIL: vehicle did not arm")
    print("Armed")

    # Running state for the whole flight; fly() updates it
    log = {"alt": 0.0, "roll": 0.0, "pitch": 0.0, "max_alt": 0.0, "max_tilt": 0.0, "gs": 0.0, "servo": (0, 0, 0, 0), "motors": (0, 0, 0), "aspd": 0.0, "last_print": 0}
    PHASE = "climb"
    print(f"Climbing (throttle {args.climb_throttle})...")
    fly(m, args.climb_time, args.climb_throttle, log)
    PHASE = "hold"
    print(f"Holding (throttle {args.hold_throttle})...")
    fly(m, 10, args.hold_throttle, log)

    if args.transition:
        PHASE = "forward"
        print("Transition to forward flight (FBWB, throttle 1800)...")
        set_mode(m, "FBWB")                  # fixed-wing mode with altitude hold
        log["max_tilt"] = 0.0                # judge forward flight on its own
        log["min_alt_fw"] = 1e9
        t_end = time.time() + 30
        max_gs = 0.0
        while time.time() < t_end:
            fly(m, 1, 1800, log)
            max_gs = max(max_gs, log["gs"])
            log["min_alt_fw"] = min(log["min_alt_fw"], log["alt"])
        # Forward flight passes if it reaches 12 m/s, stays above 2 m and keeps tilt <= 45 deg
        fw_ok = max_gs >= 12 and log["min_alt_fw"] > 2 and log["max_tilt"] <= 45
        print(f"\nforward flight: max_gs={max_gs:.1f} m/s  min_alt={log['min_alt_fw']:.1f} m  "
              f"max_tilt={log['max_tilt']:.1f} deg  -> {'PASS' if fw_ok else 'FAIL'}")
        print("Back to QHOVER, then QLAND...")
        PHASE = "back_transition"
        set_mode(m, "QHOVER")
        fly(m, 15, 1500, log)
        PHASE = "land"
        set_mode(m, "QLAND")
        fly(m, 120, 1500, log)               # long window: the landing has to finish here
        landed = log["alt"] < 0.5            # landed = below 0.5 m at the end
        print(f"landing: final alt={log['alt']:.2f} m -> {'LANDED' if landed else 'NOT LANDED'}")
        sys.exit(0 if fw_ok and landed else 1)
    PHASE = "land"
    print("Landing (QLAND)...")
    set_mode(m, "QLAND")
    fly(m, 15, 1500, log)                    # hover-only: short window, landing is not checked

    # Hover verdict: reached the minimum altitude and kept attitude within the limit
    ok = log["max_alt"] >= args.min_alt and log["max_tilt"] <= args.max_tilt
    print(f"\nmax_alt={log['max_alt']:.2f} m  max_tilt={log['max_tilt']:.1f} deg")
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
