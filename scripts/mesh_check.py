#!/usr/bin/env python3
"""
mesh_check.py — per-part mesh health check for the Stallion CAD (GLB or STL).

    python3 scripts/mesh_check.py inputs/stallion_v2_equipped_with_pod.glb
    python3 scripts/mesh_check.py <file> --json report.json

Prints one line per CAD part. A part is clean when it is watertight, has
consistent winding, is not inside-out, and has no degenerate, duplicate or
non-manifold faces. Also used as a library by mesh_repair.py, mass_properties.py
and build_stallion_v2_model.py (check() and load_parts()).
"""
import argparse
import json
import sys

import numpy as np
import trimesh


def check(mesh):
    """Topology report for one mesh. Returns a dict, with r["clean"] = True when usable."""
    edges = mesh.edges_sorted                       # every edge, sorted endpoints
    _, counts = np.unique(edges, axis=0, return_counts=True)   # faces sharing each edge
    areas = mesh.area_faces
    faces_sorted = np.sort(mesh.faces, axis=1)      # so duplicates match regardless of order
    _, fcounts = np.unique(faces_sorted, axis=0, return_counts=True)
    r = {
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),     # every edge shared by exactly 2 faces
        "winding": bool(mesh.is_winding_consistent),  # all faces oriented the same way
        "inverted": bool(mesh.is_watertight and mesh.volume < 0),  # closed but inside-out
        "degenerate": int((areas < 1e-12).sum()),   # zero-area triangles
        "duplicate": int((fcounts > 1).sum()),      # the same triangle twice
        "nonmanifold": int((counts > 2).sum()),     # an edge shared by 3+ faces
        "open_edges": int((counts == 1).sum()),     # edges with only one face (holes)
        "sheet": bool(min(mesh.extents) < 0.0015),  # thinner than 1.5 mm in some direction
        "extents_mm": [round(float(e) * 1000, 1) for e in mesh.extents],
    }
    r["clean"] = (r["watertight"] and r["winding"] and not r["inverted"] and r["degenerate"] == 0
                  and r["duplicate"] == 0 and r["nonmanifold"] == 0)
    return r


def load_parts(path):
    """Load a file as {part name: Trimesh}, with each part placed by its scene transform.

    GLB keeps the CAD's part hierarchy, so each node becomes one part.
    STL is a single mesh, returned under its file path.
    """
    loaded = trimesh.load(path, process=False)
    if isinstance(loaded, trimesh.Trimesh):
        loaded.merge_vertices()   # STL stores each triangle separately: weld before checking topology
        return {path: loaded}
    parts = {}
    for node in loaded.graph.nodes_geometry:
        transform, geom = loaded.graph[node]
        m = loaded.geometry[geom].copy()
        m.apply_transform(transform)   # bake the node's position into the vertices
        parts[node] = m
    return parts


def main():
    """Print a table of every part, flag the ones that need repair, and optionally save JSON."""
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
        json.dump(report, open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
