#!/usr/bin/env python3
"""
mesh_repair.py — repair every part of a GLB and write a repaired GLB.

    python3 scripts/mesh_repair.py in.glb out.glb [--pitch 0.0015]

Per part:
  1. merge duplicate vertices, drop duplicate / degenerate faces
  2. fix winding + outward normals, fill small holes
  3. if still not a clean closed solid (non-manifold edges, big holes,
     zero-thickness sheets): shrink-wrap it — voxelise at --pitch, fill the
     inside, re-mesh the outer surface (marching cubes) and smooth it.
     This gives a closed, manifold skin that hugs the original shape.
Check the result with scripts/mesh_check.py.
"""
import argparse

import numpy as np
import trimesh

from mesh_check import check, load_parts


def basic_repair(m):
    m = m.copy()
    m.merge_vertices(digits_vertex=6)
    m.update_faces(m.unique_faces())
    m.update_faces(m.nondegenerate_faces(height=1e-9))
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_winding(m)
    trimesh.repair.fix_inversion(m)
    trimesh.repair.fill_holes(m)
    trimesh.repair.fix_normals(m)
    return m


def shrink_wrap(m, pitch):
    # A sheet thinner than the voxel grid would vanish: give it at least 2 voxels
    vox = m.voxelized(pitch=pitch)
    vox = vox.fill()
    skin = vox.marching_cubes
    skin.apply_transform(vox.transform)
    trimesh.smoothing.filter_taubin(skin, iterations=10)
    skin.merge_vertices()
    trimesh.repair.fix_normals(skin)
    return skin


def repair(m, pitch):
    fixed = basic_repair(m)
    if check(fixed)["clean"]:
        return fixed, "basic"
    return shrink_wrap(m, pitch), "shrink-wrap"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--pitch", type=float, default=0.0015, help="shrink-wrap voxel size (m)")
    args = ap.parse_args()

    scene = trimesh.Scene()
    for name, m in load_parts(args.src).items():
        if check(m)["clean"]:
            out, how = m, "ok"
        else:
            out, how = repair(m, args.pitch)
        r = check(out)
        if how != "ok":
            print(f"{name[:44]:44s} {how:12s} -> {'clean' if r['clean'] else 'STILL BAD'} "
                  f"({len(m.faces)} -> {len(out.faces)} faces)")
        scene.add_geometry(out, node_name=name, geom_name=name)
    scene.export(args.dst)
    print(f"wrote {args.dst}")


if __name__ == "__main__":
    main()
