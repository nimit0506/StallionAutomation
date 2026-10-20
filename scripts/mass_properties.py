#!/usr/bin/env python3
"""
mass_properties.py — estimate mass, CG and inertia of the Stallion from the GLB.

    python3 scripts/mass_properties.py stallion_v2_pod_repaired.glb [--json out.json]
    python3 scripts/mass_properties.py stallion_v2_pod_repaired.glb --drop "VIAL POD"   # no pod

Frame: FLU (x forward, y left, z up), metres, same as Gazebo.
Printed parts: CAD solids are printed as thin shells, so their mass is spread
by surface area (total = --printed-mass). Carbon: mesh volume x 1.6 g/cm3.
Electronics: catalogue masses below, placed at their CAD positions.
Parts missing from the CAD (props, ESCs, wiring) are added as point masses.
"""
import argparse
import json

import numpy as np

from mesh_check import load_parts

# glTF (y-up, right-handed) -> FLU (x forward, y left, z up).
# Each row gives the FLU axis as a combination of glTF axes:
#   x_flu = -z_gltf, y_flu = -x_gltf, z_flu = y_gltf.
GLTF_TO_FLU = np.eye(4)
GLTF_TO_FLU[:3, :3] = [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]

# kg — catalogue / typical values. A CAD part whose name contains one of these
# keys gets the fixed mass instead of an area-based share of the printed mass.
COMPONENT_MASS = {
    "MOTOR RIGHT": 0.048, "MOTOR LEFT": 0.048, "MOTOR TAIL": 0.048,       # EMAX ECO II 2807
    "TILT SERVO RIGHT": 0.0134, "TILT SERVO LEFT": 0.0134,               # TowerPro MG90D
    "AILERON SERVO": 0.012, "V-TAIL SERVO": 0.012,                       # EMAX ES08MA II
    "FC -": 0.010, "RX -": 0.019, "USB EXT": 0.005,
    "BATTERY -": 0.730,                                                  # 4S 8000 mAh
    "VIAL POD": 0.075,                                                   # each of the 2 pod parts
}
CARBON_DENSITY = 1600.0  # kg/m3

# Parts that are not in the CAD at all: (name, total kg, CAD parts they sit on).
# The mass is split evenly over the anchor parts and placed at their centroids.
EXTRA_POINT_MASSES = [
    ("props x3", 0.036, ["MOTOR RIGHT", "MOTOR LEFT", "MOTOR TAIL"]),
    ("ESCs x3", 0.075, ["MOTOR MOUNT FRONT", "MOTOR MOUNT FRONT [2]", "MOTOR MOUNT TAIL"]),
    ("wiring", 0.080, ["FC - Holybro Kakute F405-Wing Mini"]),
]


def part_mass(name, mesh, printed_kg_per_m2):
    """Mass of one CAD part: fixed catalogue value, carbon volume, or printed area."""
    for key, kg in COMPONENT_MASS.items():
        if key in name:
            return kg
    if name.startswith("CARBON"):
        return abs(mesh.volume) * CARBON_DENSITY
    return mesh.area * printed_kg_per_m2


def is_printed(name):
    """True for parts that are printed plastic (not a catalogue item, not carbon)."""
    return not any(k in name for k in COMPONENT_MASS) and not name.startswith("CARBON")


def compute(path, printed_mass, battery_shift_x=0.0, drop=()):
    """Return mass, CG (FLU, metres), inertia about the CG, and CG position vs the wing root.

    drop: substrings; any CAD part whose name contains one of them is ignored
          (e.g. "VIAL POD" for the variant without the pod).
    """
    parts = load_parts(path)
    parts = {n: m for n, m in parts.items() if not any(d in n for d in drop)}
    for m in parts.values():
        m.apply_transform(GLTF_TO_FLU)
    for n, m in parts.items():
        if n.startswith("BATTERY -"):
            # Move the battery forward to bring the CG to the manual's position
            m.apply_translation([battery_shift_x, 0, 0])
    # Printed mass is spread by area, so compute the total printed area first
    printed_area = sum(m.area for n, m in parts.items() if is_printed(n))
    k = printed_mass / printed_area  # kg per m2 of printed surface

    masses, points, inertias = [], [], []
    for n, m in parts.items():
        mass = part_mass(n, m, k)
        # centre of mass of a closed solid; centroid of an open surface otherwise
        c = m.center_mass if m.is_watertight else m.centroid
        masses.append(mass)
        points.append(c)
        # treat each part as a box of its extents for its own inertia
        e = m.extents
        inertias.append(mass / 12.0 * np.diag([e[1]**2 + e[2]**2, e[0]**2 + e[2]**2, e[0]**2 + e[1]**2]))
    for _, kg, anchors in EXTRA_POINT_MASSES:
        for a in anchors:
            # a point mass at the anchor part's centroid (ignored if the anchor was dropped)
            hits = [m for n, m in parts.items() if n == a or n.startswith(a + " ")]
            if not hits:
                continue
            masses.append(kg / len(anchors))
            points.append(hits[0].centroid)
            inertias.append(np.zeros((3, 3)))

    masses = np.array(masses)
    points = np.array(points)
    total = masses.sum()
    # CG = mass-weighted average of all part positions
    cg = (masses[:, None] * points).sum(0) / total
    # Parallel-axis theorem: shift each part's own inertia to the overall CG
    inertia = np.zeros((3, 3))
    for mass, p, i_local in zip(masses, points, inertias):
        d = p - cg
        inertia += i_local + mass * (np.dot(d, d) * np.eye(3) - np.outer(d, d))

    root_le_x = parts["WING ROOT L"].bounds[1, 0]  # leading edge = max x of the wing root
    return {
        "mass_kg": float(total),
        "cg_flu_m": cg.tolist(),
        "inertia_about_cg": inertia.tolist(),
        "wing_root_le_x": float(root_le_x),
        "cg_aft_of_root_le_mm": float((root_le_x - cg[0]) * 1000),
        "battery_x": float(parts[[n for n in parts if n.startswith("BATTERY -")][0]].centroid[0]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    ap.add_argument("--printed-mass", type=float, default=1.0, help="printed airframe mass (kg)")
    ap.add_argument("--battery-shift", type=float, default=0.0, help="move battery forward (+x, m)")
    ap.add_argument("--drop", action="append", default=[], help="ignore CAD parts whose name contains this")
    ap.add_argument("--json", help="write the full result to this file")
    args = ap.parse_args()
    r = compute(args.glb, args.printed_mass, args.battery_shift, args.drop)
    cg = r["cg_flu_m"]
    print(f"AUW            {r['mass_kg']*1000:.0f} g  (manual: 1500-3000 g)")
    print(f"CG (FLU)       x={cg[0]:.4f}  y={cg[1]:.4f}  z={cg[2]:.4f} m")
    print(f"CG position    {r['cg_aft_of_root_le_mm']:.1f} mm aft of wing-root LE  (manual: 60 mm)")
    I = np.array(r["inertia_about_cg"])
    print(f"Inertia        ixx={I[0,0]:.4f} iyy={I[1,1]:.4f} izz={I[2,2]:.4f} ixz={I[0,2]:.4f} kg m^2")
    if args.json:
        json.dump(r, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
