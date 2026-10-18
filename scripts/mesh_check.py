#!/usr/bin/env python3
"""
mesh_check.py — mesh health report for a GLB/STL/OBJ (whole scene, per part).

    python3 scripts/mesh_check.py model.glb [--json report.json]

Per part it checks:
  watertight      every edge shared by exactly 2 faces (closed solid)
  winding         face winding consistent across the surface
  inverted        closed but with negative volume (normals point inward)
  degenerate      zero-area faces
  duplicate       identical faces
  nonmanifold     edges shared by more than 2 faces
  open_edges      boundary edges (holes)
  sheet           thinnest extent < 1.5 mm (zero-thickness / plate geometry)
Exit code is 0 if every part is clean, 1 otherwise.
"""
import argparse
import json
import sys

import numpy as np
import trimesh


def check(mesh):
    edges = mesh.edges_sorted
    _, counts = np.unique(edges, axis=0, return_counts=True)
    areas = mesh.area_faces
    faces_sorted = np.sort(mesh.faces, axis=1)
    _, fcounts = np.unique(faces_sorted, axis=0, return_counts=True)
    r = {
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding": bool(mesh.is_winding_consistent),
        "inverted": bool(mesh.is_watertight and mesh.volume < 0),
        "degenerate": int((areas < 1e-12).sum()),
        "duplicate": int((fcounts > 1).sum()),
        "nonmanifold": int((counts > 2).sum()),
        "open_edges": int((counts == 1).sum()),
        "sheet": bool(min(mesh.extents) < 0.0015),
        "extents_mm": [round(float(e) * 1000, 1) for e in mesh.extents],
    }
    r["clean"] = (r["watertight"] and r["winding"] and not r["inverted"] and r["degenerate"] == 0
                  and r["duplicate"] == 0 and r["nonmanifold"] == 0)
    return r


def load_parts(path):
    loaded = trimesh.load(path, process=False)
    if isinstance(loaded, trimesh.Trimesh):
        loaded.merge_vertices()   # STL stores each triangle separately: weld before checking topology
        return {path: loaded}
    parts = {}
    for node in loaded.graph.nodes_geometry:
        transform, geom = loaded.graph[node]
        m = loaded.geometry[geom].copy()
        m.apply_transform(transform)
        parts[node] = m
    return parts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json")
    args = ap.parse_args()

    parts = load_parts(args.path)
    report = {name: check(m) for name, m in parts.items()}
    bad = {n: r for n, r in report.items() if not r["clean"]}

    print(f"{'part':44s} {'faces':>7s} wt  wind inv  degen dup  nonman open  sheet")
    for n, r in report.items():
        flag = "" if r["clean"] else "  <-- needs repair"
        print(f"{n[:44]:44s} {r['faces']:7d} {'Y' if r['watertight'] else 'n':3s} "
              f"{'Y' if r['winding'] else 'n':4s} {'Y' if r['inverted'] else '-':4s} "
              f"{r['degenerate']:5d} {r['duplicate']:4d} {r['nonmanifold']:6d} {r['open_edges']:5d}  "
              f"{'Y' if r['sheet'] else '-'}{flag}")
    print(f"\n{len(report)} parts, {len(report) - len(bad)} clean, {len(bad)} need repair")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    sys.exit(0 if not bad else 1)


if __name__ == "__main__":
    main()
