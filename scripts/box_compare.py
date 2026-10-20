#!/usr/bin/env python3
# ============================================================================
# box_compare.py  —  "A few simple numbers: with the box vs without the box"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   Reads the two transition-test logs (with box, without box) and works out a
#   short list of easy-to-read numbers, then draws one chart. It is the simple
#   version of flight_metrics.py.
#
#   Altitude comes from the GPS column (gps_alt), not from the autopilot's own
#   estimate (alt). In an earlier run the estimate drifted by up to 10 m in forward
#   flight, while the GPS stayed close to the true height.
#
# HOW TO RUN IT
#   python3 scripts/box_compare.py results/box_vs_nobox
#   (the folder must contain box/ and nobox/, each with transition_log.csv and console.txt)
#
# OUTPUT
#   <folder>/summary.json   the numbers
#   <folder>/chart.png      altitude and airspeed against time, both versions
# ============================================================================

import argparse
import csv
import json
import os

import numpy as np

VERSIONS = {"box": "with box", "nobox": "without box"}
COLS = ["t", "alt", "roll", "pitch", "gs", "aspd", "tilt", "m_fr", "m_fl", "m_rear", "gps_alt"]


def load(path):
    """Read a flight log CSV into arrays (one per column) plus the phase names."""
    rows = list(csv.DictReader(open(path)))
    d = {k: np.array([float(r[k]) for r in rows]) for k in COLS}
    d["phase"] = np.array([r["phase"] for r in rows])
    d["t"] = d["t"] - d["t"][0]                    # time from the start of the climb
    return d


def thrust_share_rear(m):
    """Share of the hover thrust carried by the rear motor.

    The model's thrust grows with the square of motor speed, and motor speed is
    proportional to (PWM - 1000). So thrust ~ (PWM - 1000)^2 for each motor.
    """
    t = [(m[k] - 1000.0) ** 2 for k in ("m_fr", "m_fl", "m_rear")]
    return t[2] / sum(t)


def summarise(folder):
    """Compute the simple numbers for one version."""
    d = load(os.path.join(folder, "transition_log.csv"))
    ph = d["phase"]
    console = open(os.path.join(folder, "console.txt")).read()

    # --- climb: rate after lift-off, using GPS height ---
    c = ph == "climb"
    tc, hc = d["t"][c], d["gps_alt"][c]
    lift = np.argmax(hc > 0.3)                     # first row more than 0.3 m up
    climb_rate = (hc[-1] - hc[lift]) / (tc[-1] - tc[lift])

    # --- hover hold: how level, and how much motor power ---
    h = ph == "hold"
    tilt_rms = np.sqrt((np.maximum(np.abs(d["roll"][h]), np.abs(d["pitch"][h])) ** 2).mean())
    hover_pwm = np.mean([d[k][h].mean() for k in ("m_fr", "m_fl", "m_rear")])
    rear_share = thrust_share_rear({k: d[k][h].mean() for k in ("m_fr", "m_fl", "m_rear")})

    # --- forward flight: speed, power and height (second half = steady cruise) ---
    f = np.where(ph == "forward")[0]
    steady = f[len(f) // 2:]
    reach = np.where(d["gs"][f] >= 12)[0]
    time_to_12 = d["t"][f][reach[0]] - d["t"][f][0] if len(reach) else None
    cruise_speed = d["aspd"][steady].mean()
    cruise_pwm = (d["m_fr"][steady].mean() + d["m_fl"][steady].mean()) / 2   # the two front (cruise) motors
    height_spread = d["gps_alt"][steady].std()
    est_error = np.abs(d["alt"][f] - d["gps_alt"][f]).max()   # how far the autopilot's estimate was off

    # --- landing: time to get down, and how much it swung ---
    l = ph == "land"
    tl, hl = d["t"][l] - d["t"][l][0], d["gps_alt"][l]
    down = np.where(hl < 0.5)[0]
    land_time = tl[down[0]] if len(down) else None
    land_tilt = np.maximum(np.abs(d["roll"][l]), np.abs(d["pitch"][l])).max()

    return {
        "forward_flight_pass": "forward flight" in console and "-> PASS" in console,
        "landed": "-> LANDED" in console,
        "climb_rate_ms": round(float(climb_rate), 2),
        "hover_tilt_rms_deg": round(float(tilt_rms), 2),
        "hover_motor_pwm": round(float(hover_pwm)),
        "hover_rear_thrust_share_pct": round(100 * float(rear_share), 1),
        "time_to_12ms_s": None if time_to_12 is None else round(float(time_to_12), 1),
        "cruise_airspeed_ms": round(float(cruise_speed), 1),
        "cruise_front_motor_pwm": round(float(cruise_pwm)),
        "cruise_height_spread_m": round(float(height_spread), 2),
        "forward_estimate_error_m": round(float(est_error), 1),
        "landing_time_s": None if land_time is None else round(float(land_time), 1),
        "landing_max_tilt_deg": round(float(land_tilt), 1),
    }


def chart(root, out_png):
    """One picture: GPS height (top) and airspeed (bottom) against time, both versions."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colours = {"box": "#1F5F99", "nobox": "#D9822B"}
    fig, ax = plt.subplots(2, 1, figsize=(10, 5.5), sharex=True)
    for v, label in VERSIONS.items():
        d = load(os.path.join(root, v, "transition_log.csv"))
        ax[0].plot(d["t"], d["gps_alt"], color=colours[v], label=label, lw=1.6)
        ax[1].plot(d["t"], d["aspd"], color=colours[v], label=label, lw=1.6)
    ax[0].set_ylabel("height, GPS (m)")
    ax[1].set_ylabel("airspeed (m/s)")
    ax[1].set_xlabel("time from take-off (s)")
    ax[0].legend(frameon=False)
    for a in ax:
        a.grid(alpha=0.25)
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Simple with-box vs without-box comparison.")
    ap.add_argument("root", help="folder with box/ and nobox/ subfolders")
    args = ap.parse_args()
    result = {v: summarise(os.path.join(args.root, v)) for v in VERSIONS}
    json.dump(result, open(os.path.join(args.root, "summary.json"), "w"), indent=1)
    chart(args.root, os.path.join(args.root, "chart.png"))
    for k in result["box"]:
        print(f"{k:30s} {str(result['box'][k]):>8s}  {str(result['nobox'][k]):>8s}")


if __name__ == "__main__":
    main()
