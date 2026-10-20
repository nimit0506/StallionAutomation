#!/usr/bin/env python3
# ============================================================================
# mass_properties.py  —  "How heavy is the aircraft, where is its balance point,
#                          and how hard is it to rotate it?"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   A simulator needs three numbers about the aircraft:
#     1. MASS        : how heavy it is, in kilograms.
#     2. CG          : the centre of gravity, the single point where all the
#                      weight acts. If the CG is in the wrong place the aircraft
#                      tips nose-up or nose-down.
#     3. INERTIA     : how hard it is to start or stop a rotation. A big inertia
#                      means the aircraft turns slowly and smoothly; a small one
#                      means it turns quickly.
#   The CAD file does not contain weights, so this script estimates them:
#     - Printed plastic parts: their area is known, so the total printed mass
#       (an assumed 1.0 kg) is shared out according to area.
#     - Carbon parts: mass = volume x density (1600 kg per cubic metre).
#     - Electronics and motors: standard catalogue masses, placed at their CAD position.
#     - Parts missing from the CAD (propellers, speed controllers, wiring):
#       added as point masses at a nearby part.
#
# KEY WORDS
#   FLU frame : x = forward (nose), y = left wing, z = up. This is the standard
#               frame for aircraft and for Gazebo.
#   glTF frame: the GLB file uses y = up. We convert it to FLU with a matrix.
#   Inertia tensor: a 3x3 table describing rotation resistance about x, y, z.
#   Parallel-axis theorem: moves a part's inertia to the aircraft's CG.
#
# HOW TO RUN IT
#   python3 scripts/mass_properties.py inputs/stallion_v2_pod_repaired.glb --battery-shift 0.057
#   python3 scripts/mass_properties.py <glb> --drop "VIAL POD"     (aircraft without the pod)
#   add --json out.json to save everything to a file
# ============================================================================

import argparse   # reads command-line options
import json       # writes results to a .json file

import numpy as np            # array maths: vectors, matrices, sums

from mesh_check import load_parts   # reads the GLB into a dictionary of named parts

# ----------------------------------------------------------------------------
# Coordinate conversion matrix (glTF y-up  ->  FLU x-forward, y-left, z-up)
# ----------------------------------------------------------------------------
# A 4x4 matrix moves points from one frame to another (4 = 3 numbers + 1 for "move").
# np.eye(4) is the identity matrix (does nothing) and we overwrite the rotation part.
GLTF_TO_FLU = np.eye(4)
# Each row says where one new axis comes from:
#   new x (forward) = -old z,  new y (left) = -old x,  new z (up) = old y
GLTF_TO_FLU[:3, :3] = [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]

# ----------------------------------------------------------------------------
# Catalogue masses (kilograms) for parts we can name in the CAD.
# If a part's name CONTAINS one of these keys, it gets this fixed mass
# instead of a share of the printed mass.
# ----------------------------------------------------------------------------
COMPONENT_MASS = {
    "MOTOR RIGHT": 0.048, "MOTOR LEFT": 0.048, "MOTOR TAIL": 0.048,       # EMAX ECO II 2807 motors
    "TILT SERVO RIGHT": 0.0134, "TILT SERVO LEFT": 0.0134,               # TowerPro MG90D tilt servos
    "AILERON SERVO": 0.012, "V-TAIL SERVO": 0.012,                       # EMAX ES08MA II surface servos
    "FC -": 0.010, "RX -": 0.019, "USB EXT": 0.005,                      # flight controller, receiver, USB lead
    "BATTERY -": 0.730,                                                  # 4S 8000 mAh battery
    # The box (vial pod) is 2 parts. The CFD study's mass model (LW-PLA, 0.8 mm walls)
    # gives the box 40 g in total, so each part is 20 g.
    "VIAL POD": 0.020,
}
CARBON_DENSITY = 1600.0  # kg per cubic metre (typical carbon fibre composite)

# ----------------------------------------------------------------------------
# Parts that are NOT in the CAD at all.
# Each entry: (name, total mass in kg, list of CAD parts to attach it to).
# The mass is split evenly between the attachment parts and placed at their centres.
# ----------------------------------------------------------------------------
EXTRA_POINT_MASSES = [
    ("props x3", 0.036, ["MOTOR RIGHT", "MOTOR LEFT", "MOTOR TAIL"]),
    ("ESCs x3", 0.075, ["MOTOR MOUNT FRONT", "MOTOR MOUNT FRONT [2]", "MOTOR MOUNT TAIL"]),
    ("wiring", 0.080, ["FC - Holybro Kakute F405-Wing Mini"]),
]


def part_mass(name, mesh, printed_kg_per_m2):
    """Return the mass of one CAD part, in kilograms.

    Priority:
      1. A catalogue name (motor, servo, battery...) -> fixed catalogue mass.
      2. A carbon part -> volume x carbon density.
      3. Anything else (printed plastic) -> its surface area x the printed mass per m^2.
    """
    for key, kg in COMPONENT_MASS.items():          # check each catalogue key
        if key in name:
            return kg
    if name.startswith("CARBON"):                   # carbon parts are named "CARBON ..."
        return abs(mesh.volume) * CARBON_DENSITY    # abs() because volume can be negative if inside-out
    return mesh.area * printed_kg_per_m2            # printed plastic: share by surface area


def is_printed(name):
    """True for parts that are printed plastic: not a catalogue item and not carbon."""
    return not any(k in name for k in COMPONENT_MASS) and not name.startswith("CARBON")


def compute(path, printed_mass, battery_shift_x=0.0, drop=()):
    """Estimate mass, CG and inertia from the GLB file.

    Parameters
      path            : the GLB file (repaired version)
      printed_mass    : total mass of all printed plastic parts, in kg (assumed, e.g. 1.0)
      battery_shift_x : how far to move the battery forward (+x, metres), to place the CG
      drop            : words; any part whose name contains one of them is ignored
                        (for example "VIAL POD" builds the aircraft without the pod)

    Returns a dictionary with the mass, CG position, inertia and a few reference numbers.
    """
    # --- 1. Load every part and remove the ones we were asked to drop ---
    parts = load_parts(path)
    parts = {n: m for n, m in parts.items() if not any(d in n for d in drop)}

    # --- 2. Convert all parts from the GLB frame to the flight frame (FLU) ---
    for m in parts.values():
        m.apply_transform(GLTF_TO_FLU)

    # --- 3. Move the battery forward so the CG lands where the manual says ---
    for n, m in parts.items():
        if n.startswith("BATTERY -"):
            m.apply_translation([battery_shift_x, 0, 0])

    # --- 4. Work out the mass per square metre of printed plastic ---
    # First add up the surface area of all printed parts...
    printed_area = sum(m.area for n, m in parts.items() if is_printed(n))
    # ...then divide the assumed printed mass by that area.
    k = printed_mass / printed_area                 # kilograms per square metre

    # --- 5. For every part: its mass, its position, and its own inertia ---
    masses, points, inertias = [], [], []
    for n, m in parts.items():
        mass = part_mass(n, m, k)
        # Position of the part's mass: centre of mass for a closed solid,
        # plain centroid (average point) for an open surface.
        c = m.center_mass if m.is_watertight else m.centroid
        masses.append(mass)
        points.append(c)
        # Inertia of this part about its own centre, treating it as a simple box
        # with the part's size (extents). Formula: m/12 * (b^2 + c^2) for each axis.
        e = m.extents
        inertias.append(mass / 12.0 * np.diag([e[1]**2 + e[2]**2, e[0]**2 + e[2]**2, e[0]**2 + e[1]**2]))

    # --- 6. Add the parts that are not in the CAD (as point masses) ---
    for _, kg, anchors in EXTRA_POINT_MASSES:
        for a in anchors:
            # Find the CAD part this extra mass is attached to.
            # If it was dropped (for example the pod), skip it.
            hits = [m for n, m in parts.items() if n == a or n.startswith(a + " ")]
            if not hits:
                continue
            masses.append(kg / len(anchors))        # share the extra mass between the anchors
            points.append(hits[0].centroid)         # place it at the anchor's centre
            inertias.append(np.zeros((3, 3)))       # a point mass has no own inertia

    # --- 7. Combine everything into one aircraft ---
    masses = np.array(masses)
    points = np.array(points)
    total = masses.sum()                            # total mass of the aircraft
    # CG = weighted average position: heavy parts pull the balance point towards them
    cg = (masses[:, None] * points).sum(0) / total

    # --- 8. Total inertia about the CG ---
    # Each part's own inertia is shifted to the CG with the parallel-axis theorem:
    #   I_cg = I_own + m * (d^2 * identity - d d^T)
    # where d is the offset from the part to the CG.
    inertia = np.zeros((3, 3))
    for mass, p, i_local in zip(masses, points, inertias):
        d = p - cg
        inertia += i_local + mass * (np.dot(d, d) * np.eye(3) - np.outer(d, d))

    # --- 9. Reference numbers ---
    # The wing root leading edge is the front edge of the wing where it meets the fuselage.
    # The manual puts the CG a fixed distance behind it, so we report the CG relative to it.
    root_le_x = parts["WING ROOT L"].bounds[1, 0]   # largest x of the left wing root = its front edge
    return {
        "mass_kg": float(total),
        "cg_flu_m": cg.tolist(),                    # CG position [x, y, z] in metres (FLU frame)
        "inertia_about_cg": inertia.tolist(),       # 3x3 inertia matrix, kg m^2
        "wing_root_le_x": float(root_le_x),
        "cg_aft_of_root_le_mm": float((root_le_x - cg[0]) * 1000),  # how far behind the LE the CG is
        "battery_x": float(parts[[n for n in parts if n.startswith("BATTERY -")][0]].centroid[0]),
    }


def printed_mass_for_total(path, total_kg, battery_shift_x=0.0, drop=()):
    """Return the printed-plastic mass (kg) that makes the aircraft weigh total_kg.

    Everything except printed plastic has a fixed mass (catalogue parts, carbon,
    extras). So: printed mass = wanted total - mass of everything else.
    We get "everything else" by running compute() with zero printed mass.
    """
    rest = compute(path, 0.0, battery_shift_x, drop)["mass_kg"]
    return total_kg - rest


def main():
    """Command-line entry point: print the key numbers and optionally save JSON."""
    ap = argparse.ArgumentParser(description="Estimate mass, CG and inertia from the aircraft GLB.")
    ap.add_argument("glb", help="the repaired GLB file")
    ap.add_argument("--printed-mass", type=float, default=1.0,
                    help="total printed plastic mass in kg (assumed; default 1.0)")
    ap.add_argument("--battery-shift", type=float, default=0.0,
                    help="move the battery forward by this many metres (default 0)")
    ap.add_argument("--drop", action="append", default=[],
                    help="ignore parts whose name contains this text (repeat for several)")
    ap.add_argument("--json", help="save the full result to this .json file")
    args = ap.parse_args()

    r = compute(args.glb, args.printed_mass, args.battery_shift, args.drop)
    cg = r["cg_flu_m"]
    # Print the results in a readable form
    print(f"AUW            {r['mass_kg']*1000:.0f} g  (manual: 1500-3000 g)")          # all-up weight
    print(f"CG (FLU)       x={cg[0]:.4f}  y={cg[1]:.4f}  z={cg[2]:.4f} m")          # balance point
    print(f"CG position    {r['cg_aft_of_root_le_mm']:.1f} mm aft of wing-root LE  (manual: 60 mm)")
    I = np.array(r["inertia_about_cg"])
    print(f"Inertia        ixx={I[0,0]:.4f} iyy={I[1,1]:.4f} izz={I[2,2]:.4f} ixz={I[0,2]:.4f} kg m^2")
    if args.json:
        json.dump(r, open(args.json, "w"), indent=1)


# Run main() only when this file is started directly.
if __name__ == "__main__":
    main()
