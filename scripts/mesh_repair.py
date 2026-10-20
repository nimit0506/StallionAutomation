#!/usr/bin/env python3
# ============================================================================
# mesh_repair.py  —  "Fix the broken CAD parts and save a clean GLB"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   mesh_check.py tells us which parts of the aircraft are broken. This script
#   repairs them and writes a new GLB file where every part is a closed solid.
#
#   It treats each part on its own, in the cheapest way that works:
#     1. Already clean          -> copied unchanged.
#     2. Basic repair works     -> small fixes that keep the exact shape.
#     3. Otherwise              -> "shrink-wrap": we rebuild the part as a
#                                  closed skin around its volume. This always
#                                  gives a solid, but sharp edges get slightly
#                                  rounded.
#
# KEY WORDS
#   Voxel    : a tiny 3D cube (like a Minecraft block). We fill space with voxels.
#   Pitch    : the size of one voxel, here 1.5 mm by default.
#   Marching cubes : an algorithm that draws a smooth surface around a voxel blob.
#   Taubin smoothing : a gentle smoothing filter that removes the stair-steps.
#
# HOW TO RUN IT
#   python3 scripts/mesh_repair.py inputs/stallion_v2_equipped_with_pod.glb repaired.glb
#   python3 scripts/mesh_repair.py in.glb out.glb --pitch 0.0015
#
# NOTE: the repaired file used by the simulation is in inputs/stallion_v2_pod_repaired.glb
# ============================================================================

import argparse   # reads command-line options

import numpy as np      # array maths (imported; used indirectly by trimesh)
import trimesh          # 3D mesh library: repairs, voxels, scenes, export

# Import the checker from mesh_check.py (same folder).
#   check(mesh)      -> the health report of one mesh
#   load_parts(path) -> {part name: mesh} for a GLB or STL file
from mesh_check import check, load_parts


def basic_repair(m):
    """Cheap, shape-preserving fixes. Returns a repaired COPY of the mesh.

    Every step below only tidies up the triangles; it never moves the surface.
    """
    m = m.copy()                                     # never change the original in place

    # Join corners that sit at the same point (digits_vertex=6 = match to 1 micrometre)
    m.merge_vertices(digits_vertex=6)

    # Remove triangles that appear twice
    m.update_faces(m.unique_faces())

    # Remove triangles with zero area (they are slivers, and cause errors)
    m.update_faces(m.nondegenerate_faces(height=1e-9))

    # Delete corner points that no triangle uses any more
    m.remove_unreferenced_vertices()

    # Make all triangles point the same way ("winding" = the order of corners)
    trimesh.repair.fix_winding(m)

    # If the whole part is turned inside out, flip it back
    trimesh.repair.fix_inversion(m)

    # Close small holes by adding triangles across the boundary loop
    trimesh.repair.fill_holes(m)

    # Recalculate each triangle's "outside" direction so lighting and collisions work
    trimesh.repair.fix_normals(m)
    return m


def shrink_wrap(m, pitch):
    """Replace a broken part with a closed skin that wraps its volume.

    Plain English: fill the part's space with tiny cubes (voxels), then draw a
    smooth outer skin around the filled cubes. The skin is always closed.
    The cost: sharp edges become slightly rounded (about one voxel = 1.5 mm).
    """
    # A thin sheet thinner than one voxel would disappear completely,
    # so the grid must be fine enough to keep it (we rely on the default pitch).
    vox = m.voxelized(pitch=pitch)                   # turn the surface into a grid of voxels
    vox = vox.fill()                                 # fill the inside of the voxel shape solid
    skin = vox.marching_cubes                        # draw the outer surface around the voxels
    skin.apply_transform(vox.transform)              # convert voxel units back to metres
    trimesh.smoothing.filter_taubin(skin, iterations=10)   # smooth away the blocky steps
    skin.merge_vertices()                            # join duplicated corners
    trimesh.repair.fix_normals(skin)                 # make the outside direction consistent
    return skin


def repair(m, pitch):
    """Decide how to repair one part.

    First try the cheap fixes. Only if the result is still not clean,
    use shrink-wrap. Returns (repaired mesh, name of the method used).
    """
    fixed = basic_repair(m)
    if check(fixed)["clean"]:
        return fixed, "basic"
    return shrink_wrap(m, pitch), "shrink-wrap"


def main():
    """Read every part from the input file, repair the broken ones, and save one GLB."""
    ap = argparse.ArgumentParser(description="Repair broken CAD parts and write a clean GLB.")
    ap.add_argument("src", help="input GLB or STL with the raw CAD parts")
    ap.add_argument("dst", help="output GLB file to write")
    ap.add_argument("--pitch", type=float, default=0.0015,
                    help="voxel size for shrink-wrap, in metres (default 1.5 mm)")
    args = ap.parse_args()

    # A "scene" is a container that holds many named meshes with their positions.
    scene = trimesh.Scene()

    for name, m in load_parts(args.src).items():
        if check(m)["clean"]:
            out, how = m, "ok"                       # already fine: keep it as it is
        else:
            out, how = repair(m, args.pitch)         # broken: repair it

        r = check(out)                               # check the result again
        if how != "ok":
            # Print one line per part that needed work, so the user can see what changed
            print(f"{name[:44]:44s} {how:12s} -> {'clean' if r['clean'] else 'STILL BAD'} "
                  f"({len(m.faces)} -> {len(out.faces)} faces)")

        # Put the repaired part back into the scene under its ORIGINAL name.
        # The simulation build looks parts up by name, so the names must not change.
        scene.add_geometry(out, node_name=name, geom_name=name)

    # Save the whole scene as one GLB file
    scene.export(args.dst)
    print(f"wrote {args.dst}")


# Run main() only when this file is started directly, not when it is imported.
if __name__ == "__main__":
    main()
