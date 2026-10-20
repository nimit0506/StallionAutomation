#!/usr/bin/env python3
"""
flight_metrics.py — flight-dynamics metrics from the 10 Hz flight logs.

    python3 scripts/flight_metrics.py results/variants --out results/metrics

Reads, for each variant folder (pod, nopod):
    hover_log.csv       hover test (climb, hold, QLAND)
    transition_log.csv  hover + forward flight (FBWB) + back to hover + landing
Writes:
    <out>/metrics.json  every number, per variant and phase
    <out>/charts/*.png  time-series charts used in the deck

Column meanings (from sitl_hover_check.py): t (s), phase, alt (m), roll and pitch (deg),
gs ground speed (m/s), aspd airspeed (m/s), tilt (PWM, 1000 = hover, 2000 = forward),
ail (PWM), vtail_l / vtail_r (PWM), m_fr / m_fl / m_rear (motor PWM).
"""
import argparse
import csv
import json
import os

import numpy as np

VARIANTS = ["pod", "nopod"]
TESTS = ["hover_log.csv", "transition_log.csv"]
FIELDS = ["t", "alt", "roll", "pitch", "gs", "aspd", "tilt", "ail", "vtail_l", "vtail_r", "m_fr", "m_fl", "m_rear"]


def load(path):
    """Read a flight CSV into numpy arrays, plus the phase label of each row."""
    rows = list(csv.DictReader(open(path)))
    d = {k: np.array([float(r[k]) for r in rows]) for k in FIELDS}
    d["phase"] = np.array([r["phase"] for r in rows])
    return d


def phase_slice(d, name):
    """Boolean mask of the rows that belong to one phase (or None if the phase is absent)."""
    m = d["phase"] == name
    return m if m.any() else None


def settle_time(t, att, limit=2.0):
    """Seconds from the start of a phase until |roll| and |pitch| stay within `limit` degrees.

    None if the attitude never settles within the phase.
    """
    bad = np.where(att > limit)[0]
    if len(bad) == 0:
        return 0.0
    if bad[-1] == len(att) - 1:
        return None                      # still out of limits at the end of the phase
    return float(t[bad[-1] + 1] - t[0])


def climb_rate(t, alt):
    """Mean climb rate (m/s) and peak climb rate (m/s, from a 0.5 s smoothed slope)."""
    if len(t) < 3:
        return None, None
    rate = np.gradient(alt, t)
    k = max(1, int(round(0.5 / np.median(np.diff(t)))))          # ~0.5 s window
    smooth = np.convolve(rate, np.ones(k) / k, mode="same")
    return float((alt[-1] - alt[0]) / (t[-1] - t[0])), float(smooth.max())


def hover_phase(d, name):
    """Metrics for a hover-style phase: altitude, attitude, control effort and settling."""
    m = phase_slice(d, name)
    if m is None:
        return None
    t, alt = d["t"][m], d["alt"][m]
    roll, pitch = d["roll"][m], d["pitch"][m]
    att = np.maximum(np.abs(roll), np.abs(pitch))
    motors = np.vstack([d["m_fr"][m], d["m_fl"][m], d["m_rear"][m]])
    mean_rate, peak_rate = climb_rate(t, alt)
    out = {
        "duration_s": round(float(t[-1] - t[0]), 1),
        "alt_start_m": round(float(alt[0]), 2),
        "alt_end_m": round(float(alt[-1]), 2),
        "alt_mean_m": round(float(alt.mean()), 2),
        "alt_std_m": round(float(alt.std()), 3),
        "alt_min_m": round(float(alt.min()), 2),
        "alt_max_m": round(float(alt.max()), 2),
        "mean_vertical_rate_ms": None if mean_rate is None else round(mean_rate, 2),
        "peak_vertical_rate_ms": None if peak_rate is None else round(peak_rate, 2),
        "roll_rms_deg": round(float(np.sqrt((roll ** 2).mean())), 2),
        "pitch_rms_deg": round(float(np.sqrt((pitch ** 2).mean())), 2),
        "max_abs_roll_deg": round(float(np.abs(roll).max()), 2),
        "max_abs_pitch_deg": round(float(np.abs(pitch).max()), 2),
        "settle_2deg_s": settle_time(t, att),
        "motor_mean_pwm": [round(float(x), 0) for x in motors.mean(1)],
        "motor_std_pwm": [round(float(x), 1) for x in motors.std(1)],
        "tilt_mean_pwm": round(float(d["tilt"][m].mean()), 0),
        "aileron_std_pwm": round(float(d["ail"][m].std()), 1),
        "vtail_std_pwm": round(float((d["vtail_l"][m] - d["vtail_r"][m]).std()), 1),
    }
    return out


def forward_phase(d, name="forward"):
    """Metrics for the forward-flight (FBWB) phase, using the second half to judge steady flight."""
    m = phase_slice(d, name)
    if m is None:
        return None
    t = d["t"][m]
    gs, aspd, alt = d["gs"][m], d["aspd"][m], d["alt"][m]
    roll, pitch = d["roll"][m], d["pitch"][m]
    half = len(t) // 2                       # steady part = after the first half
    reach = np.where(gs >= 12)[0]            # first moment the ground speed reaches 12 m/s
    return {
        "duration_s": round(float(t[-1] - t[0]), 1),
        "time_to_12ms_s": None if len(reach) == 0 else round(float(t[reach[0]] - t[0]), 1),
        "gs_max_ms": round(float(gs.max()), 2),
        "gs_mean_steady_ms": round(float(gs[half:].mean()), 2),
        "airspeed_max_ms": round(float(aspd.max()), 2),
        "airspeed_mean_steady_ms": round(float(aspd[half:].mean()), 2),
        "alt_min_m": round(float(alt.min()), 2),
        "alt_max_m": round(float(alt.max()), 2),
        "alt_mean_steady_m": round(float(alt[half:].mean()), 2),
        "alt_std_steady_m": round(float(alt[half:].std()), 3),
        "roll_rms_steady_deg": round(float(np.sqrt((roll[half:] ** 2).mean())), 2),
        "pitch_rms_steady_deg": round(float(np.sqrt((pitch[half:] ** 2).mean())), 2),
        "max_abs_roll_deg": round(float(np.abs(roll).max()), 2),
        "max_abs_pitch_deg": round(float(np.abs(pitch).max()), 2),
        "tilt_pwm_mean": round(float(d["tilt"][m].mean()), 0),
        "aileron_std_pwm": round(float(d["ail"][m].std()), 1),
        "vtail_std_pwm": round(float((d["vtail_l"][m] - d["vtail_r"][m]).std()), 1),
    }


def landing_phase(d, name="land"):
    """Metrics for the QLAND phase: descent rate, whether it finished, and attitude while landing."""
    m = phase_slice(d, name)
    if m is None:
        return None
    t, alt = d["t"][m], d["alt"][m]
    roll, pitch = d["roll"][m], d["pitch"][m]
    rate = np.gradient(alt, t)
    below = np.where(alt < 0.5)[0]           # first moment the aircraft is below 0.5 m
    return {
        "duration_s": round(float(t[-1] - t[0]), 1),
        "alt_start_m": round(float(alt[0]), 2),
        "alt_final_m": round(float(alt[-1]), 2),
        "touchdown_s": None if len(below) == 0 else round(float(t[below[0]] - t[0]), 1),
        "mean_descent_rate_ms": round(float(-rate[alt > 0.5].mean()), 2) if (alt > 0.5).any() else None,
        "max_descent_rate_ms": round(float(-rate.min()), 2),
        "max_abs_roll_deg": round(float(np.abs(roll).max()), 2),
        "max_abs_pitch_deg": round(float(np.abs(pitch).max()), 2),
        "settle_2deg_s": settle_time(t, np.maximum(np.abs(roll), np.abs(pitch))),
    }


def analyse(path, is_transition):
    """All metrics for one flight CSV."""
    d = load(path)
    out = {
        "climb": hover_phase(d, "climb"),
        "hold": hover_phase(d, "hold"),
    }
    if is_transition:
        out["forward"] = forward_phase(d)
        out["back_transition"] = hover_phase(d, "back_transition")
    out["land"] = landing_phase(d)
    return out


def charts(root, out_dir):
    """Time-series charts comparing the two variants (matplotlib, PNG)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(out_dir, exist_ok=True)
    colours = {"pod": "#1f77b4", "nopod": "#d62728"}
    for test in ["hover", "transition"]:
        fig, ax = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        for v in VARIANTS:
            d = load(os.path.join(root, v, f"{test}_log.csv"))
            label = "with pod" if v == "pod" else "without pod"
            ax[0].plot(d["t"], d["alt"], color=colours[v], label=label)
            ax[1].plot(d["t"], d["roll"], color=colours[v], label=label)
            ax[2].plot(d["t"], d["pitch"], color=colours[v], label=label)
        ax[0].set_ylabel("altitude (m)")
        ax[1].set_ylabel("roll (deg)")
        ax[2].set_ylabel("pitch (deg)")
        ax[2].set_xlabel("time (s)")
        ax[0].legend()
        for a in ax:
            a.grid(alpha=0.3)
        fig.suptitle(f"{test} flight: altitude and attitude")
        fig.tight_layout()
        fig.savefig(os.path.join(out_dir, f"{test}_timeseries.png"), dpi=150)
        plt.close(fig)
    # speed and tilt for the transition, which is where the two variants differ most
    fig, ax = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    for v in VARIANTS:
        d = load(os.path.join(root, v, "transition_log.csv"))
        label = "with pod" if v == "pod" else "without pod"
        ax[0].plot(d["t"], d["aspd"], color=colours[v], label=label)
        ax[1].plot(d["t"], d["tilt"], color=colours[v], label=label)
    ax[0].set_ylabel("airspeed (m/s)")
    ax[1].set_ylabel("tilt servo (PWM)")
    ax[1].set_xlabel("time (s)")
    ax[0].legend()
    for a in ax:
        a.grid(alpha=0.3)
    fig.suptitle("Transition flight: airspeed and tilt command")
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "transition_speed_tilt.png"), dpi=150)
    plt.close(fig)


def main():
    """Compute metrics for both variants and write the JSON and charts."""
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="folder that holds pod/ and nopod/ subfolders")
    ap.add_argument("--out", default="results/metrics")
    args = ap.parse_args()
    result = {}
    for v in VARIANTS:
        result[v] = {
            "hover": analyse(os.path.join(args.root, v, "hover_log.csv"), is_transition=False),
            "transition": analyse(os.path.join(args.root, v, "transition_log.csv"), is_transition=True),
        }
    os.makedirs(args.out, exist_ok=True)
    json.dump(result, open(os.path.join(args.out, "metrics.json"), "w"), indent=1)
    charts(args.root, os.path.join(args.out, "charts"))
    print(json.dumps(result, indent=1)[:2000])
    print(f"\nwrote {args.out}/metrics.json and charts/")


if __name__ == "__main__":
    main()
