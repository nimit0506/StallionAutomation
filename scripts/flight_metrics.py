#!/usr/bin/env python3
# ============================================================================
# flight_metrics.py  —  "Turn the raw flight recordings into numbers and charts"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   During a flight, sitl_hover_check.py writes a log: about 10 rows per second,
#   each with the time, the altitude, the tilt (roll and pitch), the speeds and
#   the servo / motor commands. A log is hard to read by eye, so this script
#   summarises it into a few hundred numbers per flight, for each part of the
#   flight (climb, hold, forward flight, landing...), and draws simple charts.
#
# KEY WORDS
#   Phase      : one part of the flight. The log labels every row with its phase.
#   RMS        : "root mean square", the typical size of a value that goes up and
#                down. For tilt, RMS near 0 means the aircraft stayed level.
#   Std        : standard deviation, how much a value wanders around its average.
#   Peak       : the largest value reached.
#   Settle time: how long until the tilt stays within a small limit (here 2 degrees).
#   Steady     : the second half of a phase, after the first changes have passed.
#   Touchdown  : the moment the altitude first drops below 0.5 m.
#
# HOW TO RUN IT
#   python3 scripts/flight_metrics.py results/variants --out results/metrics
#   (results/variants must contain a pod/ and a nopod/ folder, each with
#    hover_log.csv and transition_log.csv)
#
# OUTPUT
#   <out>/metrics.json        all the numbers, per variant, per test, per phase
#   <out>/charts/*.png        charts used in the slides
#
# COLUMN MEANINGS (from sitl_hover_check.py)
#   t          time in seconds since the script started
#   phase      climb, hold, forward, back_transition or land
#   alt        altitude above the take-off point, metres
#   roll, pitch  attitude in degrees (0 = level)
#   gs         ground speed, m/s (speed over the ground)
#   aspd       airspeed, m/s (speed through the air)
#   tilt       tilt servo command, PWM (1000 = rotors up, 2000 = rotors forward)
#   ail        aileron command, PWM
#   vtail_l    left V-tail command, PWM (the right one mirrors it, so the left is enough)
#   m_fr, m_fl, m_rear   motor commands, PWM (front-right, front-left, rear)
# ============================================================================

import argparse     # reads command-line options
import csv          # reads the CSV log files
import json         # writes the metrics as a .json file
import os           # builds file paths and creates folders

import numpy as np  # fast arrays and maths (mean, std, gradient, ...)

VARIANTS = ["pod", "nopod"]                     # the two airframes we compare
TESTS = ["hover_log.csv", "transition_log.csv"]  # the two kinds of test (not used directly below)
# The columns we read from each CSV row
FIELDS = ["t", "alt", "roll", "pitch", "gs", "aspd", "tilt", "ail", "vtail_l", "vtail_r", "m_fr", "m_fl", "m_rear"]


def load(path):
    """Read one flight CSV file.

    Returns a dictionary:
      d["t"], d["alt"], ...  : numpy arrays, one value per log row
      d["phase"]             : numpy array of phase names, one per row
    """
    rows = list(csv.DictReader(open(path)))      # each row becomes a dict: column name -> text
    # For each column, convert the text values into numbers
    d = {k: np.array([float(r[k]) for r in rows]) for k in FIELDS}
    d["phase"] = np.array([r["phase"] for r in rows])   # the phase names stay as text
    return d


def phase_slice(d, name):
    """Return a True/False mask that is True on the rows of one phase.

    Returns None if that phase does not appear in the log at all.
    Usage: d["alt"][mask] gives only the altitudes of that phase.
    """
    m = d["phase"] == name                       # True where the phase label matches
    return m if m.any() else None                # None if no row has that label


def settle_time(t, att, limit=2.0):
    """Seconds from the start of a phase until the tilt stays inside +/- limit degrees.

    t     : times of the rows in the phase.
    att   : the largest of |roll| and |pitch| at each row.
    limit : the tilt limit in degrees (default 2).

    The method: find the LAST moment the tilt was outside the limit. The aircraft
    has settled just after that moment. Returns None if it was still outside at the end.
    """
    bad = np.where(att > limit)[0]               # row numbers where the tilt was too large
    if len(bad) == 0:
        return 0.0                               # never outside the limit: settled at once
    if bad[-1] == len(att) - 1:
        return None                              # still outside at the very end: never settled
    return float(t[bad[-1] + 1] - t[0])          # time from the start to the row after the last bad one


def climb_rate(t, alt):
    """Work out how fast the aircraft climbs.

    Returns (mean rate, peak rate), both in m/s.
      mean rate : (end altitude - start altitude) / time taken.
      peak rate : the fastest climb over any 0.5 s window. The raw rate is noisy,
                  so we smooth it with a moving average first.
    """
    if len(t) < 3:
        return None, None                        # too few points to work out a rate
    rate = np.gradient(alt, t)                   # change of altitude per second at each row
    # Number of rows in 0.5 s, for the moving average window
    k = max(1, int(round(0.5 / np.median(np.diff(t)))))
    smooth = np.convolve(rate, np.ones(k) / k, mode="same")   # moving average
    return float((alt[-1] - alt[0]) / (t[-1] - t[0])), float(smooth.max())


def hover_phase(d, name):
    """Compute the metrics for one phase of a hover-style test (climb, hold, back transition).

    Returns a dictionary of numbers, or None if the phase is not in the log.
    """
    m = phase_slice(d, name)                     # rows that belong to this phase
    if m is None:
        return None
    t, alt = d["t"][m], d["alt"][m]              # times and altitudes of this phase
    roll, pitch = d["roll"][m], d["pitch"][m]    # attitudes of this phase
    att = np.maximum(np.abs(roll), np.abs(pitch))  # largest tilt at each row (roll or pitch)
    # The three motor commands stacked as rows: one row per motor
    motors = np.vstack([d["m_fr"][m], d["m_fl"][m], d["m_rear"][m]])
    mean_rate, peak_rate = climb_rate(t, alt)    # climb rates (see climb_rate)
    out = {
        "duration_s": round(float(t[-1] - t[0]), 1),          # how long the phase lasted
        "alt_start_m": round(float(alt[0]), 2),               # altitude at the start
        "alt_end_m": round(float(alt[-1]), 2),                # altitude at the end
        "alt_mean_m": round(float(alt.mean()), 2),            # average altitude
        "alt_std_m": round(float(alt.std()), 3),              # how much altitude wandered
        "alt_min_m": round(float(alt.min()), 2),
        "alt_max_m": round(float(alt.max()), 2),
        "mean_vertical_rate_ms": None if mean_rate is None else round(mean_rate, 2),
        "peak_vertical_rate_ms": None if peak_rate is None else round(peak_rate, 2),
        # RMS = typical size of the tilt. 0 = perfectly level.
        "roll_rms_deg": round(float(np.sqrt((roll ** 2).mean())), 2),
        "pitch_rms_deg": round(float(np.sqrt((pitch ** 2).mean())), 2),
        "max_abs_roll_deg": round(float(np.abs(roll).max()), 2),   # largest roll, either direction
        "max_abs_pitch_deg": round(float(np.abs(pitch).max()), 2), # largest pitch, either direction
        "settle_2deg_s": settle_time(t, att),                      # time to settle within 2 degrees
        "motor_mean_pwm": [round(float(x), 0) for x in motors.mean(1)],  # average command per motor
        "motor_std_pwm": [round(float(x), 1) for x in motors.std(1)],    # how much each motor moved
        "tilt_mean_pwm": round(float(d["tilt"][m].mean()), 0),           # average tilt command
        "aileron_std_pwm": round(float(d["ail"][m].std()), 1),           # how hard the ailerons worked
        "vtail_std_pwm": round(float(d["vtail_l"][m].std()), 1),         # how hard the V-tail worked
    }
    return out


def forward_phase(d, name="forward"):
    """Compute the metrics for the forward-flight phase (FBWB, wings carry the aircraft).

    The 'steady' numbers use only the second half of the phase, because the
    first half includes the acceleration and the settling.
    """
    m = phase_slice(d, name)
    if m is None:
        return None
    t = d["t"][m]
    gs, aspd, alt = d["gs"][m], d["aspd"][m], d["alt"][m]
    roll, pitch = d["roll"][m], d["pitch"][m]
    half = len(t) // 2                           # index of the middle row of the phase
    reach = np.where(gs >= 12)[0]                # rows where the ground speed is 12 m/s or more
    return {
        "duration_s": round(float(t[-1] - t[0]), 1),
        # How long it took to first reach 12 m/s after the phase started
        "time_to_12ms_s": None if len(reach) == 0 else round(float(t[reach[0]] - t[0]), 1),
        "gs_max_ms": round(float(gs.max()), 2),
        "gs_mean_steady_ms": round(float(gs[half:].mean()), 2),   # ground speed, second half
        "airspeed_max_ms": round(float(aspd.max()), 2),
        "airspeed_mean_steady_ms": round(float(aspd[half:].mean()), 2),
        "alt_min_m": round(float(alt.min()), 2),
        "alt_max_m": round(float(alt.max()), 2),
        "alt_mean_steady_m": round(float(alt[half:].mean()), 2),
        "alt_std_steady_m": round(float(alt[half:].std()), 3),    # how much height wandered, second half
        "roll_rms_steady_deg": round(float(np.sqrt((roll[half:] ** 2).mean())), 2),
        "pitch_rms_steady_deg": round(float(np.sqrt((pitch[half:] ** 2).mean())), 2),
        "max_abs_roll_deg": round(float(np.abs(roll).max()), 2),
        "max_abs_pitch_deg": round(float(np.abs(pitch).max()), 2),
        "tilt_pwm_mean": round(float(d["tilt"][m].mean()), 0),
        "aileron_std_pwm": round(float(d["ail"][m].std()), 1),
        "vtail_std_pwm": round(float(d["vtail_l"][m].std()), 1),
    }


def landing_phase(d, name="land"):
    """Compute the metrics for the landing (QLAND), the vertical descent at the end of a test."""
    m = phase_slice(d, name)
    if m is None:
        return None
    t, alt = d["t"][m], d["alt"][m]
    roll, pitch = d["roll"][m], d["pitch"][m]
    rate = np.gradient(alt, t)                   # altitude change per second (negative = going down)
    below = np.where(alt < 0.5)[0]               # rows where the aircraft is below 0.5 m
    return {
        "duration_s": round(float(t[-1] - t[0]), 1),
        "alt_start_m": round(float(alt[0]), 2),
        "alt_final_m": round(float(alt[-1]), 2),
        # Time until the first row below 0.5 m = the touchdown time
        "touchdown_s": None if len(below) == 0 else round(float(t[below[0]] - t[0]), 1),
        # Average descent speed while still above 0.5 m (sign flipped so "down" is positive)
        "mean_descent_rate_ms": round(float(-rate[alt > 0.5].mean()), 2) if (alt > 0.5).any() else None,
        # Fastest descent in the whole landing (also sign flipped)
        "max_descent_rate_ms": round(float(-rate.min()), 2),
        "max_abs_roll_deg": round(float(np.abs(roll).max()), 2),
        "max_abs_pitch_deg": round(float(np.abs(pitch).max()), 2),
        "settle_2deg_s": settle_time(t, np.maximum(np.abs(roll), np.abs(pitch))),
    }


def analyse(path, is_transition):
    """Compute all the metrics for one flight log.

    is_transition = True also includes the forward flight and the return to hover.
    """
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
    """Draw the charts (PNG pictures) that the slides use. Uses matplotlib."""
    import matplotlib
    matplotlib.use("Agg")                        # draw to files; no window needed (works on servers)
    import matplotlib.pyplot as plt
    os.makedirs(out_dir, exist_ok=True)
    colours = {"pod": "#1f77b4", "nopod": "#d62728"}   # blue = with pod, red = without pod
    # Two charts: the hover test, and the transition test. Each has three panels.
    for test in ["hover", "transition"]:
        # three panels stacked, sharing the same time axis
        fig, ax = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
        for v in VARIANTS:
            d = load(os.path.join(root, v, f"{test}_log.csv"))
            label = "with pod" if v == "pod" else "without pod"
            ax[0].plot(d["t"], d["alt"], color=colours[v], label=label)     # top: altitude
            ax[1].plot(d["t"], d["roll"], color=colours[v], label=label)    # middle: roll
            ax[2].plot(d["t"], d["pitch"], color=colours[v], label=label)   # bottom: pitch
        ax[0].set_ylabel("altitude (m)")
        ax[1].set_ylabel("roll (deg)")
        ax[2].set_ylabel("pitch (deg)")
        ax[2].set_xlabel("time (s)")
        ax[0].legend()
        for a in ax:
            a.grid(alpha=0.3)                    # faint grid lines
        fig.suptitle(f"{test} flight: altitude and attitude")
        fig.tight_layout()                       # stop labels overlapping
        fig.savefig(os.path.join(out_dir, f"{test}_timeseries.png"), dpi=150)
        plt.close(fig)                           # free the memory
    # One more chart: airspeed and tilt command for the transition (where the variants differ most)
    fig, ax = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    for v in VARIANTS:
        d = load(os.path.join(root, v, "transition_log.csv"))
        label = "with pod" if v == "pod" else "without pod"
        ax[0].plot(d["t"], d["aspd"], color=colours[v], label=label)   # top: airspeed
        ax[1].plot(d["t"], d["tilt"], color=colours[v], label=label)   # bottom: tilt command
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
    """Read both variants, compute every metric, save JSON, draw the charts."""
    ap = argparse.ArgumentParser(description="Flight-dynamics metrics and charts from the flight logs.")
    ap.add_argument("root", help="folder that holds the pod/ and nopod/ subfolders")
    ap.add_argument("--out", default="results/metrics", help="where to write metrics.json and charts/")
    args = ap.parse_args()
    result = {}
    # Build a nested dictionary: result["pod"]["hover"]["hold"]["alt_mean_m"] etc.
    for v in VARIANTS:
        result[v] = {
            "hover": analyse(os.path.join(args.root, v, "hover_log.csv"), is_transition=False),
            "transition": analyse(os.path.join(args.root, v, "transition_log.csv"), is_transition=True),
        }
    os.makedirs(args.out, exist_ok=True)
    json.dump(result, open(os.path.join(args.out, "metrics.json"), "w"), indent=1)
    charts(args.root, os.path.join(args.out, "charts"))
    print(json.dumps(result, indent=1)[:2000])   # show the start of the result on screen
    print(f"\nwrote {args.out}/metrics.json and charts/")


# Run main() only when this file is started directly
if __name__ == "__main__":
    main()
