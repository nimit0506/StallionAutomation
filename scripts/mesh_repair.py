#!/usr/bin/env python3
"""
mesh_repair.py — repair the CAD parts that fail mesh_check, write a new GLB.

    python3 scripts/mesh_repair.py inputs/stallion_v2_equipped_with_pod.glb repaired.glb
    python3 scripts/mesh_repair.py in.glb out.glb --pitch 0.0015

Each part is handled on its own:
  1. clean already        -> copied unchanged
  2. basic repair works   -> small fixes only, shape preserved
  3. otherwise            -> shrink-wrap (voxelise and re-mesh; closed but slightly rounded)
"""
import argparse

import numpy as np
import trimesh

from mesh_check import check, load_parts


def basic_repair(m):
    """Cheap, shape-preserving fixes. Returns a repaired copy."""
    m = m.copy()
    m.merge_vertices(digits_vertex=6)                 # weld vertices that are the same point
    m.update_faces(m.unique_faces())                  # drop duplicated triangles
    m.update_faces(m.nondegenerate_faces(height=1e-9))  # drop zero-area triangles
    m.remove_unreferenced_vertices()
    trimesh.repair.fix_winding(m)                     # make face orientation consistent
    trimesh.repair.fix_inversion(m)                   # flip the mesh if it is inside-out
    trimesh.repair.fill_holes(m)                      # close small boundary loops
    trimesh.repair.fix_normals(m)
    return m


def shrink_wrap(m, pitch):
    """Replace a part by a closed skin around its voxelised volume (rounds sharp edges).

    The voxel fill makes the solid watertight even when the original was a set of
    open or self-intersecting sheets.
    """
    # A sheet thinner than the voxel grid would vanish: give it at least 2 voxels
    vox = m.voxelized(pitch=pitch)
    vox = vox.fill()                                  # fill the interior of the voxel grid
    skin = vox.marching_cubes                         # surface of the filled voxels
    skin.apply_transform(vox.transform)               # back to metres
    trimesh.smoothing.filter_taubin(skin, iterations=10)  # smooth the staircase
    skin.merge_vertices()
    trimesh.repair.fix_normals(skin)
    return skin


def repair(m, pitch):
    """Try the basic repair first; use shrink-wrap only if that is not enough.

    Returns (repaired mesh, method name).
    """
    fixed = basic_repair(m)
    if check(fixed)["clean"]:
        return fixed, "basic"
    return shrink_wrap(m, pitch), "shrink-wrap"


def main():
    """Repair every part of src and write them all into one scene at dst."""
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--pitch", type=float, default=0.0015, help="shrink-wrap voxel size (m)")
    args = ap.parse_args()

    scene = trimesh.Scene()
    for name, m in load_parts(args.src).items():
        if check(m)["clean"]:
            out, how = m, "ok"                        # already fine, keep as-is
        else:
            out, how = repair(m, args.pitch)
        r = check(out)
        if how != "ok":
            print(f"{name[:44]:44s} {how:12s} -> {'clean' if r['clean'] else 'STILL BAD'} "
                  f"({len(m.faces)} -> {len(out.faces)} faces)")
        # keep the part name so the rest of the pipeline can find it again
        scene.add_geometry(out, node_name=name, geom_name=name)
    scene.export(args.dst)
    print(f"wrote {args.dst}")


if __name__ == "__main__":
    main()
