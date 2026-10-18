#!/usr/bin/env python3
"""
mass_properties.py — estimate mass, CG and inertia of the Stallion from the GLB.

    python3 scripts/mass_properties.py stallion_v2_pod_repaired.glb [--json out.json]

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

GLTF_TO_FLU = np.eye(4)
GLTF_TO_FLU[:3, :3] = [[0, 0, -1], [-1, 0, 0], [0, 1, 0]]

# kg — catalogue / typical values
COMPONENT_MASS = {
    "MOTOR RIGHT": 0.048, "MOTOR LEFT": 0.048, "MOTOR TAIL": 0.048,       # EMAX ECO II 2807
    "TILT SERVO RIGHT": 0.0134, "TILT SERVO LEFT": 0.0134,               # TowerPro MG90D
    "AILERON SERVO": 0.012, "V-TAIL SERVO": 0.012,                       # EMAX ES08MA II
    "FC -": 0.010, "RX -": 0.019, "USB EXT": 0.005,
    "BATTERY -": 0.730,                                                  # 4S 8000 mAh
    "VIAL POD": 0.075,                                                   # each of the 2 pod parts
}
CARBON_DENSITY = 1600.0  # kg/m3

# Not in the CAD: (name, kg, glTF-frame anchor part or fixed FLU point)
EXTRA_POINT_MASSES = [
    ("props x3", 0.036, ["MOTOR RIGHT", "MOTOR LEFT", "MOTOR TAIL"]),
    ("ESCs x3", 0.075, ["MOTOR MOUNT FRONT", "MOTOR MOUNT FRONT [2]", "MOTOR MOUNT TAIL"]),
    ("wiring", 0.080, ["FC - Holybro Kakute F405-Wing Mini"]),
]


def part_mass(name, mesh, printed_kg_per_m2):
    for key, kg in COMPONENT_MASS.items():
        if key in name:
            return kg
    if name.startswith("CARBON"):
        return abs(mesh.volume) * CARBON_DENSITY
    return mesh.area * printed_kg_per_m2


def is_printed(name):
    return not any(k in name for k in COMPONENT_MASS) and not name.startswith("CARBON")


def compute(path, printed_mass, battery_shift_x=0.0):
    parts = load_parts(path)
    for m in parts.values():
        m.apply_transform(GLTF_TO_FLU)
    for n, m in parts.items():
        if n.startswith("BATTERY -"):
            m.apply_translation([battery_shift_x, 0, 0])
    printed_area = sum(m.area for n, m in parts.items() if is_printed(n))
    k = printed_mass / printed_area

    masses, points, inertias = [], [], []
    for n, m in parts.items():
        mass = part_mass(n, m, k)
        c = m.center_mass if m.is_watertight else m.centroid
        masses.append(mass)
        points.append(c)
        # treat each part as a box of its extents for its own inertia
        e = m.extents
        inertias.append(mass / 12.0 * np.diag([e[1]**2 + e[2]**2, e[0]**2 + e[2]**2, e[0]**2 + e[1]**2]))
    for _, kg, anchors in EXTRA_POINT_MASSES:
        for a in anchors:
            masses.append(kg / len(anchors))
            points.append(next(m for n, m in parts.items() if n == a or n.startswith(a + " ")).centroid)
            inertias.append(np.zeros((3, 3)))

    masses = np.array(masses)
    points = np.array(points)
    total = masses.sum()
    cg = (masses[:, None] * points).sum(0) / total
    inertia = np.zeros((3, 3))
    for mass, p, i_local in zip(masses, points, inertias):
        d = p - cg
        inertia += i_local + mass * (np.dot(d, d) * np.eye(3) - np.outer(d, d))

    root_le_x = parts["WING ROOT L"].bounds[1, 0]
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
    ap.add_argument("--json")
    args = ap.parse_args()
    r = compute(args.glb, args.printed_mass, args.battery_shift)
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
