#!/usr/bin/env python3
# ============================================================================
# mesh_check.py  —  "Is this 3D part a valid solid?"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   The aircraft CAD file is a 3D model made of many small triangles.
#   For a simulator, every part must be a *closed solid*: like a sealed
#   plastic toy with no holes. This script checks every part of the CAD
#   file and tells you which ones are broken (holes, flipped triangles,
#   paper-thin sheets, and so on).
#
# KEY WORDS
#   Mesh     : a 3D shape made of triangles (faces) joined at corners (vertices).
#   Part     : one named piece of the aircraft, e.g. "FUS 2L" or "AILERON 1L".
#   GLB      : a common 3D file format that keeps the parts and their positions.
#   STL      : a simpler 3D format with one mesh and no part names.
#   Watertight: a closed surface where every edge is shared by exactly two
#              triangles. "Water cannot leak out", so it has a clear inside.
#
# HOW TO RUN IT
#   python3 scripts/mesh_check.py inputs/stallion_v2_equipped_with_pod.glb
#   python3 scripts/mesh_check.py <file.glb> --json report.json
#
# OTHER SCRIPTS USE THIS FILE
#   mesh_repair.py, mass_properties.py and build_stallion_v2_model.py import
#   check() and load_parts() from here.
# ============================================================================

import argparse   # reads command-line options such as --json
import json       # writes the report to a .json file
import sys        # (imported for completeness; not needed by the current code)

import numpy as np      # fast array maths: used to count edges and faces
import trimesh          # library for 3D meshes: loads files, measures volume, etc.


def check(mesh):
    """Check one mesh and return a dictionary (report) describing its health.

    The key result is r["clean"]: True means the mesh is a usable solid.
    """
    # --- Step 1: list every edge (a line between two corners of a triangle) ---
    edges = mesh.edges_sorted                       # each edge as two sorted corner IDs
    # np.unique(..., return_counts=True) tells us how many triangles share each edge.
    #   count 1 -> the edge is on a hole (open)
    #   count 2 -> normal, the surface continues smoothly
    #   count 3+ -> non-manifold: three or more sheets meet at one line (not a valid solid)
    _, counts = np.unique(edges, axis=0, return_counts=True)

    # --- Step 2: how big is each triangle? ---
    areas = mesh.area_faces                         # area of every triangle, in m^2

    # --- Step 3: find triangles that appear twice (duplicates) ---
    faces_sorted = np.sort(mesh.faces, axis=1)      # sort corner IDs so order does not matter
    _, fcounts = np.unique(faces_sorted, axis=0, return_counts=True)

    r = {
        # Number of triangles in the part.
        "faces": int(len(mesh.faces)),
        # True = closed surface with no holes (every edge has exactly two faces).
        "watertight": bool(mesh.is_watertight),
        # True = all triangles point the same way (their "front" faces are consistent).
        "winding": bool(mesh.is_winding_consistent),
        # True = closed, but the normals point INWARD (the part is turned inside out).
        "inverted": bool(mesh.is_watertight and mesh.volume < 0),
        # Number of zero-area triangles (squashed to a line or point: useless, must go).
        "degenerate": int((areas < 1e-12).sum()),
        # Number of triangles that exist twice (they make the surface "double").
        "duplicate": int((fcounts > 1).sum()),
        # Number of edges shared by 3 or more triangles (invalid for a solid).
        "nonmanifold": int((counts > 2).sum()),
        # Number of edges with only one triangle (these are the edges of holes).
        "open_edges": int((counts == 1).sum()),
        # True if the part is thinner than 1.5 mm in some direction ("a sheet").
        # Sheets are a problem for the collision skin, so we flag them.
        "sheet": bool(min(mesh.extents) < 0.0015),
        # Size of the part's bounding box in millimetres (x, y, z).
        "extents_mm": [round(float(e) * 1000, 1) for e in mesh.extents],
    }

    # A part counts as "clean" only if ALL the important checks pass.
    # (We do not require "sheet" to be false here: sheets are a warning, not an error.)
    r["clean"] = (r["watertight"] and r["winding"] and not r["inverted"] and r["degenerate"] == 0
                  and r["duplicate"] == 0 and r["nonmanifold"] == 0)
    return r


def load_parts(path):
    """Load a 3D file and return a dictionary: {part name: mesh}.

    - For a GLB file, each named node in the scene becomes one part.
      The node's position/rotation (its "transform") is applied to the vertices,
      so every part sits exactly where the CAD put it.
    - For an STL file (a single mesh), the file path is used as the only name.
    """
    # process=False keeps the file exactly as it is (no automatic cleaning).
    loaded = trimesh.load(path, process=False)

    # Case 1: the file is a single mesh (STL)
    if isinstance(loaded, trimesh.Trimesh):
        # An STL stores every triangle separately, so the same corner appears
        # several times. merge_vertices() joins them, which is needed before
        # checking whether the surface is closed.
        loaded.merge_vertices()
        return {path: loaded}

    # Case 2: the file is a scene with many named parts (GLB)
    parts = {}
    # graph.nodes_geometry lists the nodes that actually hold geometry.
    for node in loaded.graph.nodes_geometry:
        transform, geom = loaded.graph[node]          # position of this node + which mesh it uses
        m = loaded.geometry[geom].copy()              # copy so we don't change the original
        m.apply_transform(transform)                  # move the vertices to their place in the scene
        parts[node] = m                               # store under the node's name
    return parts


def main():
    """Command-line entry point: check every part and print a table."""
    ap = argparse.ArgumentParser(description="Check every part of a CAD file for mesh problems.")
    ap.add_argument("path", help="the GLB or STL file to check")
    ap.add_argument("--json", help="optional: save the full report to this .json file")
    args = ap.parse_args()

    # Load all parts and check each one
    parts = load_parts(args.path)
    report = {name: check(m) for name, m in parts.items()}
    # Keep only the parts that failed
    bad = {n: r for n, r in report.items() if not r["clean"]}

    # Print the table header. Columns:
    #   faces = triangle count, wt = watertight, wind = winding ok, inv = inside-out,
    #   degen = zero-area triangles, dup = duplicate triangles, nonman = non-manifold edges,
    #   open = open edges (holes), sheet = paper-thin
    print(f"{'part':44s} {'faces':>7s} wt  wind inv  degen dup  nonman open  sheet")
    for n, r in report.items():
        flag = "" if r["clean"] else "  <-- needs repair"
        print(f"{n[:44]:44s} {r['faces']:7d} {'Y' if r['watertight'] else 'n':3s} "
              f"{'Y' if r['winding'] else 'n':4s} {'Y' if r['inverted'] else '-':4s} "
              f"{r['degenerate']:5d} {r['duplicate']:4d} {r['nonmanifold']:6d} {r['open_edges']:5d}  "
              f"{'Y' if r['sheet'] else '-'}{flag}")

    # Summary line at the end
    print(f"\n{len(report)} parts, {len(report) - len(bad)} clean, {len(bad)} need repair")

    # Optionally save everything to a JSON file
    if args.json:
        json.dump(report, open(args.json, "w"), indent=1)


# This is the standard Python idiom: run main() only when this file is executed
# directly (python3 mesh_check.py ...), not when another script imports it.
if __name__ == "__main__":
    main()
