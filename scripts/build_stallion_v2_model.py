#!/usr/bin/env python3
# ============================================================================
# build_stallion_v2_model.py  —  "Turn the CAD into a flying model for Gazebo"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   This is the most important script in the project. It reads the repaired
#   CAD file of the Stallion V2 aircraft and writes everything Gazebo needs to
#   simulate it:
#     - meshes  : 3D shapes for what you SEE and for COLLISION (touching the ground).
#     - model.sdf : a text file describing the aircraft as a set of
#                   connected parts (links), the joints that move them, the
#                   air forces acting on them (aerodynamics), the propellers,
#                   and the link to the autopilot (ArduPilot).
#
# KEY WORDS (read these first)
#   SDF        : "Simulation Description Format", an XML text file that describes
#                a robot or aircraft for Gazebo. Think of it as a blueprint.
#   Link       : a rigid body (one piece that does not bend), e.g. the fuselage
#                or one propeller motor.
#   Joint      : a connection between two links that lets one rotate relative to
#                the other (a hinge). Servos move joints.
#   Mesh       : the 3D triangle shape of a link (used for display and collision).
#   Collision  : the invisible shape Gazebo uses for contact with the ground.
#   LiftDrag   : a Gazebo plugin that applies air lift and drag on a point of a
#                link, using the air speed and the angle of attack.
#   Plugin     : an add-on program that Gazebo loads (here the ArduPilot bridge
#                and the LiftDrag and joint-state plugins).
#   Angle of attack (AoA): the angle between the wing and the oncoming air.
#   CG         : centre of gravity, the balance point (see mass_properties.py).
#   Origin     : the (0,0,0) point of the model. Here it is the CG target.
#   Servo      : a small motor that moves a joint to a commanded angle.
#   PWM        : the 1000..2000 pulse-width value the autopilot sends to a servo
#                or motor. 1000 = minimum, 2000 = maximum, 1500 = middle.
#   JSON FDM   : the protocol used to exchange sensor and servo data between
#                Gazebo ("the physics", called FDM = flight dynamics model) and
#                ArduPilot ("the autopilot") over UDP network packets.
#
# FRAME USED
#   FLU: x = forward (nose), y = left wing, z = up. Units: metres and kilograms.
#
# WHAT IS MEASURED AND WHAT IS ASSUMED
#   Measured from the CAD : hinge positions, motor positions, V-tail angle, areas.
#   Taken from the manual : aerodynamic coefficients (E205 airfoil, wing area,
#                           chord, aspect ratio).
#   Assumed               : printed mass (1.0 kg), moving-part masses, prop
#                           coefficients, drag area.
#
# HOW TO RUN IT
#   python3 scripts/build_stallion_v2_model.py inputs/stallion_v2_pod_repaired.glb
#   python3 scripts/build_stallion_v2_model.py <glb> --variant nopod
#
# The output is written to gazebo/models/<model name>/. Running it again gives
# byte-identical files (so a clean `git diff` means nothing changed).
# ============================================================================

import argparse   # reads the --variant option
import os         # builds file paths and creates folders

import numpy as np      # array maths
import trimesh          # loads and manipulates 3D meshes

from mass_properties import GLTF_TO_FLU, compute, printed_mass_for_total   # coordinate conversion + mass estimate
from mesh_check import load_parts                  # loads named parts from the GLB

# Folder of this script, and the folder that holds the Gazebo models.
# os.path.abspath makes the path absolute, so the script works from any folder.
HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "gazebo", "models")

# ----------------------------------------------------------------------------
# Fixed design values
# ----------------------------------------------------------------------------
# How far the battery is moved forward (metres) compared with its CAD position.
# This was chosen so that the CG lands at the manual's position. The battery
# moves the same way in both variants, so only the pod's mass changes the CG.
BATTERY_SHIFT = 0.057        # metres
# The manual's CG position: 60 mm behind the leading edge of the wing root.
CG_AFT_OF_ROOT_LE = 0.060    # metres

# ----------------------------------------------------------------------------
# Assumptions taken from the CFD study (Stallion_box_vs_nobox_CFD.pptx, 0.8 mm walls)
# ----------------------------------------------------------------------------
# All-up mass WITH the box. The printed-plastic mass is solved so the model weighs
# exactly this; the same printed mass is then used without the box, which gives
# 2228 g, also the CFD value (the box is 40 g, see mass_properties.py).
TARGET_MASS_WITH_BOX = 2.268     # kg
# Whole-aircraft drag coefficient at 0 deg angle of attack, 20 m/s (CFD slide 4),
# on the CFD reference area. Used to set the drag of each version.
CFD_REF_AREA = 0.22068           # m^2
CFD_CD0 = {"pod": 0.06648, "nopod": 0.05830}
# The wing LiftDrag elements already make some drag at 0 deg (area x cda x a0 =
# 0.265 x 0.13 x 0.063 m^2). The parasite-drag element supplies the rest, so the
# total drag at 0 deg matches the CFD for each version.
WING_DRAG_AREA_0DEG = 0.265 * 0.13 * 0.063   # m^2 (CD x area)
PARASITE_CD = 0.20               # drag coefficient of the parasite element


def parasite_area(variant):
    """Area (m^2) of the parasite-drag element so the total CdA at 0 deg matches the CFD."""
    return (CFD_CD0[variant] * CFD_REF_AREA - WING_DRAG_AREA_0DEG) / PARASITE_CD


# Which CAD parts each variant removes, and which models it writes.
#   "pod"   : the normal aircraft (with the box). Writes two models, stallion_vtol
#             (flown) and stallion_vtol_2 (a second copy that sits on the runway).
#   "nopod" : the aircraft without the box. Writes stallion_vtol_nopod.
# Each entry is (model folder name, ArduPilot JSON port). The port is the UDP
# number the autopilot talks to for that airframe.
VARIANTS = {
    "pod": {"drop": [], "models": [("stallion_vtol", 9002), ("stallion_vtol_2", 9012)]},
    "nopod": {"drop": ["VIAL POD"], "models": [("stallion_vtol_nopod", 9002)]},
}


def solve_mass_and_battery(glb):
    """Printed mass and battery shift for the CFD target mass, CG at the manual position.

    Both are solved on the WITH-box aircraft and then used for both versions, so the
    only difference between them is the box itself (its 40 g and its drag).
    The battery shift is found with two quick evaluations: the CG moves in a straight
    line with the battery position, so two points give the exact answer.
    """
    shift = BATTERY_SHIFT
    for _ in range(2):
        printed = printed_mass_for_total(glb, TARGET_MASS_WITH_BOX, shift)
        mp = compute(glb, printed, shift)
        err = mp["cg_aft_of_root_le_mm"] / 1000 - CG_AFT_OF_ROOT_LE   # + = CG too far aft
        # Moving the battery forward by d moves the CG forward by d * m_batt / M
        shift += err * mp["mass_kg"] / 0.730
    printed = printed_mass_for_total(glb, TARGET_MASS_WITH_BOX, shift)
    return printed, shift

# ----------------------------------------------------------------------------
# MOVING: which CAD parts belong to which moving link.
# Key = name of the link in the model. Value = CAD part names (exact, or the
# start of a name). Each CAD part is used exactly once; leftovers go to BASE_GROUPS.
# ----------------------------------------------------------------------------
MOVING = {
    "fl_tilt_link":  ["MOTOR MOUNT FRONT [2]"],     # front-left motor mount (tilts)
    "fl_motor_link": ["MOTOR LEFT"],                # front-left motor (spins)
    "fr_tilt_link":  ["MOTOR MOUNT FRONT"],         # front-right motor mount (tilts)
    "fr_motor_link": ["MOTOR RIGHT"],               # front-right motor (spins)
    "rear_yaw_link": ["MOTOR MOUNT TAIL"],          # rear motor mount (swivels sideways)
    "rear_motor_link": ["MOTOR TAIL"],              # rear motor (spins)
    "aileron_left":  ["AILERON 1L", "AILERON 2L"],  # left aileron (roll control)
    "aileron_right": ["AILERON 1R", "AILERON 2R"],  # right aileron
    "ruddervator_left":  ["RUDDER 1L", "RUDDER 2L"],    # left V-tail surface (pitch + yaw)
    "ruddervator_right": ["RUDDER 1R", "RUDDER 2R"],    # right V-tail surface
}

# ----------------------------------------------------------------------------
# BASE_GROUPS: the parts that do NOT move, grouped by colour for display.
# Key = group name. Value = (colour as RGB 0..1, a test function that says
# whether a part name belongs in this group).
# ----------------------------------------------------------------------------
BASE_GROUPS = {
    # everything not in another group = the orange body (fuselage, booms, etc.)
    "airframe": ((1.0, 0.45, 0.1), lambda n: not any(k in n for k in
                 ["WING", "V TAIL", "CARBON", "VIAL", "SERVO -", "SERVO RIGHT", "SERVO LEFT",
                  "FC -", "RX -", "BATTERY -", "USB"])),
    "wings": ((0.95, 0.95, 0.95), lambda n: ("WING" in n or "V TAIL" in n)),       # white
    "carbon": ((0.12, 0.12, 0.12), lambda n: n.startswith("CARBON")),              # black
    "pod": ((0.3, 0.75, 0.35), lambda n: "VIAL" in n),                             # green
    "electronics": ((0.85, 0.15, 0.15), lambda n: any(k in n for k in              # red
                    ["SERVO -", "SERVO RIGHT", "SERVO LEFT", "FC -", "RX -", "BATTERY -", "USB"])),
}
# Colours used for the moving links in the simulator's view
LINK_COLOUR = {"motor": (0.1, 0.1, 0.1), "tilt": (0.3, 0.3, 0.3), "surface": (0.25, 0.55, 0.95)}


def match(parts, prefixes):
    """Find the CAD part names that match a list of prefixes.

    A CAD name is either exact ("AILERON 1L") or "PREFIX - catalogue name"
    (for example "BATTERY - GenX 4S 8000mAh"). If a prefix matches nothing,
    we raise KeyError so a renamed part fails loudly instead of silently.
    """
    out = []
    for p in prefixes:
        hits = [n for n in parts if n == p or n.startswith(p + " -")]
        if not hits:
            raise KeyError(p)
        out += hits
    return out


def simplify_part(m, tol):
    """Make one closed part simpler (fewer triangles) without breaking it.

    Uses the 'manifold3d' library, which only simplifies in ways that keep the
    surface closed. If the result is not clean, we keep the original part.
    """
    import manifold3d                                # imported here: only needed in this function
    from mesh_check import check
    try:
        # Convert to manifold3d's format (float32 corners, uint32 triangle indices)
        man = manifold3d.Manifold(manifold3d.Mesh(m.vertices.astype(np.float32), m.faces.astype(np.uint32)))
        o = man.simplify(tol).to_mesh()              # reduce triangles; tol = allowed error in metres
        out = clean_degenerate(trimesh.Trimesh(o.vert_properties[:, :3], o.tri_verts))
        if check(out)["clean"] and len(out.faces) > 0:
            return out
    except Exception:
        pass                                         # any failure: fall through and keep the original
    return m


def clean_degenerate(m):
    """Remove zero-area triangles by joining corners that are almost on top of each other.

    This keeps the mesh closed after simplification.
    """
    m.merge_vertices(digits_vertex=5)                # join corners within 10 micrometres
    m.update_faces(m.nondegenerate_faces(height=1e-9))   # drop zero-area triangles
    m.remove_unreferenced_vertices()
    m.merge_vertices()
    trimesh.repair.fill_holes(m)                     # close any hole the cleanup made
    trimesh.repair.fix_normals(m)                    # make all outward directions consistent
    return m


def group_mesh(parts, names, tol):
    """Simplify each named part on its own, then join them into one mesh.

    Simplifying each part separately means every part stays a clean solid.
    If any part is still not clean, we stop with an error rather than
    exporting a broken model.
    """
    from mesh_check import check
    pieces = [simplify_part(parts[n], tol) for n in names]
    bad = [n for n, p in zip(names, pieces) if not check(p)["clean"]]
    if bad:
        raise RuntimeError(f"unclean parts: {bad}")
    return trimesh.util.concatenate(pieces), len(names)   # join the pieces into one mesh


def hinge(meshes, flip=False):
    """Find where a control surface hinges and which way it turns.

    Returns (position, axis):
      position : the point on the surface's front edge, in the middle of its span.
      axis     : the direction of the hinge line (along the span, i.e. across the wing).

    How the axis is found: the surface is a long thin shape, so the direction in
    which its points are spread the most (its 'principal component') is the span.
    """
    v = np.vstack([m.vertices for m in meshes])      # all corner points of the surface
    c = v.mean(0)                                    # average point = centre of the surface
    # Eigen-decomposition of the spread of the points: the largest eigenvalue
    # belongs to the direction of greatest spread.
    w, U = np.linalg.eigh((v - c).T @ (v - c))
    axis = U[:, -1] / np.linalg.norm(U[:, -1])       # unit vector along the span
    if axis[1] < 0:                                  # make the axis point towards +y (left)
        axis = -axis
    if flip:                                         # optional: reverse it (not used now)
        axis = -axis
    # The front edge = the average of the points in the front 10% (largest x)
    front = v[v[:, 0] > np.percentile(v[:, 0], 90)].mean(0)
    pos = np.array([front[0], c[1], c[2]])           # hinge at the front edge, mid-span, mid-height
    return pos, axis


def shrink_wrap_points(mesh_list, pitch, tol=0.001):
    """Build ONE closed outer skin around several meshes (used for collision).

    The collision skin is what the ground touches, so it has to be closed and
    simple. Steps, in plain words:
      1. Scatter points over every surface.
      2. Put them into a grid of cubes (voxels), each 'pitch' metres wide.
      3. Close small gaps and fill holes, so the blob has no openings.
      4. Keep only the largest blob (drops stray bits).
      5. Draw a smooth outer surface around the blob (marching cubes).
      6. Simplify it while keeping it closed.
    """
    import manifold3d
    from scipy import ndimage                        # image-processing tools for the voxel grid
    from skimage import measure                      # marching cubes (surface from a voxel blob)
    # Sample points on every part. More points on bigger parts. seed=0 makes it repeatable.
    pts = np.vstack([m.sample(max(2000, int(m.area / pitch**2 * 4)), seed=0) for m in mesh_list])
    lo = pts.min(0) - 3 * pitch                      # corner of the grid, with a little margin
    idx = np.floor((pts - lo) / pitch).astype(int)   # which voxel each point falls into
    grid = np.zeros(idx.max(0) + 4, bool)            # empty voxel grid (True = filled)
    grid[tuple(idx.T)] = True                        # mark the voxels that contain a point
    grid = ndimage.binary_closing(grid, iterations=1)    # close small gaps between voxels
    grid = ndimage.binary_fill_holes(grid)           # fill enclosed empty spaces
    grid = ndimage.binary_dilation(grid, iterations=1)   # grow the blob by one voxel (thin plates survive)
    # Opening removes voxels that only touch at an edge (they would make the skin non-manifold)
    grid = ndimage.binary_opening(grid, structure=np.ones((2, 2, 2)))
    labels, n = ndimage.label(grid)                  # give each separate blob a number
    # Keep only the biggest blob
    grid = labels == (np.argmax(ndimage.sum(grid, labels, range(1, n + 1))) + 1)
    # Marching cubes: draw the surface around the voxels. pad() adds an empty border
    # so the surface closes at the edges.
    v, f, _, _ = measure.marching_cubes(np.pad(grid, 1).astype(np.uint8), 0.5)
    skin = trimesh.Trimesh((v - 1) * pitch + lo, f)  # convert voxel units back to metres
    skin.merge_vertices()
    if skin.volume < 0:                              # inside-out? flip it
        skin.invert()
    from mesh_check import check
    # Simplify the skin, trying a few tolerances from coarse to fine.
    m = manifold3d.Manifold(manifold3d.Mesh(skin.vertices.astype(np.float32), skin.faces.astype(np.uint32)))
    # keep the lightest result that is still fully clean
    for t in (tol * 1.5, tol, tol * 0.75, tol * 0.5):
        o = m.simplify(t).to_mesh()
        out = trimesh.Trimesh(o.vert_properties[:, :3], o.tri_verts)
        if check(out)["clean"]:
            return out
    return skin                                      # fall back to the unsimplified skin


def f3(v):
    """Format a list of numbers as one string with spaces, e.g. '0.1000 0.0000 0.0500'."""
    return " ".join(f"{x:.4f}" for x in v)


def visual(name, uri, rgb):
    """Write one <visual> block: what the link LOOKS like (a mesh with a flat colour).

    <ambient>/<diffuse> are the colour values; <specular> is how shiny it is.
    """
    r, g, b = rgb
    return f"""      <visual name="{name}">
        <geometry><mesh><uri>{uri}</uri></mesh></geometry>
        <material><ambient>{r} {g} {b} 1</ambient><diffuse>{r} {g} {b} 1</diffuse><specular>0.2 0.2 0.2 1</specular></material>
      </visual>
"""


def inertial(mass, i=(1e-5, 1e-5, 1e-5), pose="0 0 0 0 0 0", ixz=0.0):
    """Write one <inertial> block: the link's mass and how hard it is to rotate.

    mass : kilograms. i : (Ixx, Iyy, Izz) in kg m^2. pose : where the centre of mass is.
    ixz  : the cross term between x and z (usually small).
    """
    return f"""      <inertial>
        <pose>{pose}</pose>
        <mass>{mass:.4f}</mass>
        <inertia><ixx>{i[0]:.5f}</ixx><ixy>0</ixy><ixz>{ixz:.5f}</ixz><iyy>{i[1]:.5f}</iyy><iyz>0</iyz><izz>{i[2]:.5f}</izz></inertia>
      </inertial>
"""


def joint(name, parent, child, pos, axis, lower, upper, damping=0.01):
    """Write one <joint> block: a hinge between a parent link and a child link.

    pos   : where the hinge is, relative to the parent.
    axis  : the direction the child rotates around.
    lower, upper : the angle limits in radians (the joint cannot go past them).
    damping : friction-like resistance that makes the joint move smoothly.
    """
    return f"""    <joint name="{name}" type="revolute">
      <pose relative_to="{parent}">{f3(pos)} 0 0 0</pose>
      <parent>{parent}</parent>
      <child>{child}</child>
      <axis>
        <xyz>{f3(axis)}</xyz>
        <limit><lower>{lower}</lower><upper>{upper}</upper></limit>
        <dynamics><damping>{damping}</damping></dynamics>
      </axis>
    </joint>
"""


def liftdrag(comment, link, cp, area, upward, a0, cla, cda, stall, cj=None, rad_to_cl=0.0,
             forward=(1, 0, 0), cla_stall=-2.0, cda_stall=1.0):
    """Write one LiftDrag plugin block: an air-force element on a link.

    Inputs, in plain words:
      comment   : a note written into the file for humans.
      link      : which link the force acts on.
      cp        : the point on the link where the force acts (centre of pressure).
      area      : the effective area (m^2) of the surface.
      upward    : the direction of the lift force.
      a0        : the angle of attack (radians) at which lift is zero.
      cla       : how much lift per radian of angle of attack (the 'lift slope').
      cda       : drag coefficient.
      stall     : the angle (radians) where the lift stops growing (stall).
      cj        : optional name of a joint (a control surface) that adds lift when it moves.
      rad_to_cl : how much lift is added per radian of that joint's angle.
    """
    # Control-surface part: only written when the element is linked to a joint
    ctrl = (f"\n      <control_joint_name>{cj}</control_joint_name>"
            f"\n      <control_joint_rad_to_cl>{rad_to_cl}</control_joint_rad_to_cl>") if cj else ""
    return f"""    <!-- {comment} -->
    <plugin filename="gz-sim-lift-drag-system" name="gz::sim::systems::LiftDrag">
      <a0>{a0}</a0><cla>{cla}</cla><cda>{cda}</cda><cma>0.0</cma>
      <alpha_stall>{stall}</alpha_stall><cla_stall>{cla_stall}</cla_stall><cda_stall>{cda_stall}</cda_stall><cma_stall>0.0</cma_stall>
      <area>{area}</area><air_density>1.2041</air_density>
      <cp>{f3(cp)}</cp><forward>{f3(forward)}</forward><upward>{f3(upward)}</upward>
      <link_name>{link}</link_name>{ctrl}
    </plugin>
"""


# ----------------------------------------------------------------------------
# Propeller model. Each propeller is modelled as two "blade elements" (one at
# each side of the hub). Air is pushed by the spinning blade and the reaction
# gives thrust. The numbers are chosen to match the EMAX 2807 motor with a
# 7x4 prop on 4S (see the comment below).
# ----------------------------------------------------------------------------
# PROP_R      : distance of each blade element from the hub (m)
# PROP_A0     : zero-lift angle of attack of the blade (rad)
# PROP_CLA    : lift slope of the blade (per rad)
# PROP_AREA   : area of each blade element (m^2)
# MOTOR_OMEGA_MAX : top spin speed in rad/s (1610 rad/s ~ 15,400 rpm)
PROP_R, PROP_A0, PROP_CLA, PROP_AREA, MOTOR_OMEGA_MAX = 0.0667, 0.28, 5.0, 0.000874, 1610


def prop_liftdrag(link, sign):
    """Write the two LiftDrag blocks for one propeller.

    The air a blade meets comes from the link spinning, so thrust grows with the
    spin speed. 'sign' sets the direction of the in-plane airflow, which depends
    on which way the motor spins.
    """
    out = ""
    # two blade elements: one at +R and one at -R (opposite sides of the hub)
    for cp, fwd in ((PROP_R, -sign), (-PROP_R, sign)):
        out += f"""    <plugin filename="gz-sim-lift-drag-system" name="gz::sim::systems::LiftDrag">
      <a0>{PROP_A0}</a0><alpha_stall>1.4</alpha_stall><cla>{PROP_CLA}</cla><cda>0.10</cda><cma>0.00</cma>
      <cla_stall>-0.025</cla_stall><cda_stall>0.0</cda_stall><cma_stall>0.0</cma_stall>
      <area>{PROP_AREA}</area><air_density>1.2041</air_density>
      <cp>{cp} 0 0</cp><forward>0 {fwd} 0</forward><upward>0 0 1</upward>
      <link_name>{link}</link_name>
    </plugin>
"""
    return out


def control(ch, joint_name, kind, mult, offset=-0.5, gains=None):
    """Write one <control> block: connect one autopilot PWM channel to one joint.

    The autopilot sends PWM values for channel `ch` (1000..2000). Gazebo turns
    that into a command for the joint:
        normalised = (PWM - 1000) / 1000        -> 0.0 .. 1.0
        command    = (normalised + offset) * mult

    kind:
      "VELOCITY" : the joint is a motor; the command is a spin speed (rad/s).
      "POSITION" : the joint is a servo; the command is an angle (rad), driven
                   by a PD controller (P = stiffness, D = damping).
    """
    if kind == "VELOCITY":
        # Motor: velocity control, with a gentle proportional gain
        g = """        <type>VELOCITY</type>
        <p_gain>0.20</p_gain><i_gain>0</i_gain><d_gain>0</d_gain><i_max>0</i_max><i_min>0</i_min>
        <cmd_max>2.5</cmd_max><cmd_min>-2.5</cmd_min>
        <controlVelocitySlowdownSim>1</controlVelocitySlowdownSim>"""
    else:
        # Servo: position control. gains = (P, D, max command)
        p, d, cmax = gains or (2.0, 0.02, 2.0)
        g = f"""        <type>POSITION</type>
        <p_gain>{p}</p_gain><i_gain>0</i_gain><d_gain>{d}</d_gain><i_max>0</i_max><i_min>0</i_min>
        <cmd_max>{cmax}</cmd_max><cmd_min>-{cmax}</cmd_min>"""
    return f"""      <control channel="{ch}">
        <jointName>{joint_name}</jointName>
        <useForce>1</useForce>
        <multiplier>{mult}</multiplier>
        <offset>{offset}</offset>
        <servo_min>1000</servo_min>
        <servo_max>2000</servo_max>
{g}
      </control>
"""


def build(glb, variant="pod"):
    """Build all meshes and model files for one variant. This is the main workflow.

    Steps: load parts -> move to the flight frame -> place the origin at the CG
    -> find joints from the CAD -> make meshes -> make collision skin -> write SDF.
    """
    drop = VARIANTS[variant]["drop"]
    # --- 1. Load the repaired GLB and remove the parts this variant does not use ---
    parts = load_parts(glb)
    parts = {n: m for n, m in parts.items() if not any(d in n for d in drop)}
    # --- 2. Convert every part to the flight frame (x forward, y left, z up) ---
    for m in parts.values():
        m.apply_transform(GLTF_TO_FLU)
    # The leading edge of the left wing root is our reference for the CG position
    root_le_x = parts["WING ROOT L"].bounds[1, 0]
    # --- 3. Mass, CG and inertia for this variant ---
    # Printed mass and battery position come from the CFD target mass (with box),
    # and are the same for both versions.
    printed, shift = solve_mass_and_battery(glb)
    mp = compute(glb, printed, shift, drop)
    # --- 4. Put the model origin at the CG target ---
    # x: 60 mm behind the wing-root leading edge; z: the computed CG height; y: centre line
    origin = np.array([root_le_x - CG_AFT_OF_ROOT_LE, 0.0, mp["cg_flu_m"][2]])
    for n, m in parts.items():
        m.apply_translation(-origin)                 # shift everything so the origin is at (0,0,0)
        if n.startswith("BATTERY -"):
            m.apply_translation([shift, 0, 0])       # move the battery as described above
    # The real CG relative to the origin. Zero for the pod version (within rounding);
    # for the no-pod version it is a few tenths of a millimetre. Gazebo needs it
    # so the simulated balance is correct.
    cg_offset = np.array(mp["cg_flu_m"]) - origin

    # --- 5. Joint positions, measured from the CAD ---
    def centre(prefixes):
        """Centre of the bounding box of one or more named parts."""
        return trimesh.util.concatenate([parts[n] for n in match(parts, prefixes)]).bounds.mean(0)

    j = {}
    # Front motors: the tilt joint is at the motor's x and y, 6 mm above the bottom of its mount
    for side, mount, motor in (("fl", "MOTOR MOUNT FRONT [2]", "MOTOR LEFT"), ("fr", "MOTOR MOUNT FRONT", "MOTOR RIGHT")):
        mb = trimesh.util.concatenate([parts[n] for n in match(parts, [mount])]).bounds
        mc = centre([motor])
        j[f"{side}_tilt"] = np.array([mc[0], mc[1], mb[0, 2] + 0.006])     # tilt pivot
        j[f"{side}_motor"] = mc                                             # motor spin axis
    # Rear motor: the yaw joint sits at the motor's x, centre line, mid-height of the mount
    tb = trimesh.util.concatenate([parts[n] for n in match(parts, ["MOTOR MOUNT TAIL"])]).bounds
    j["rear_yaw"] = np.array([centre(["MOTOR TAIL"])[0], 0.0, tb.mean(0)[2]])
    j["rear_motor"] = centre(["MOTOR TAIL"])
    # Control surfaces: find each hinge with the hinge() function
    surf = {}
    for link, flip in (("aileron_left", False), ("aileron_right", False),
                       ("ruddervator_left", False), ("ruddervator_right", False)):
        surf[link] = hinge([parts[n] for n in match(parts, MOVING[link])], flip=flip)
    # Where each link's origin sits (used to re-centre its mesh on its joint)
    link_origin = {
        "fl_tilt_link": j["fl_tilt"], "fl_motor_link": j["fl_motor"],
        "fr_tilt_link": j["fr_tilt"], "fr_motor_link": j["fr_motor"],
        "rear_yaw_link": j["rear_yaw"], "rear_motor_link": j["rear_motor"],
        **{k: v[0] for k, v in surf.items()},
    }

    # --- 6. Meshes: one per link, one per colour group, plus the collision skin ---
    used = set()                                     # names of parts already assigned
    meshes = {}
    # Moving links: join and simplify their parts, then re-centre on the joint
    for link, prefixes in MOVING.items():
        names = match(parts, prefixes)
        used.update(names)
        m, _ = group_mesh(parts, names, 0.0002)      # tol 0.2 mm
        m.apply_translation(-link_origin[link])
        meshes[link] = m
    # Fixed parts, grouped by colour. Empty groups (e.g. pod in the no-pod variant) are skipped.
    for g, (_, pred) in BASE_GROUPS.items():
        names = [n for n in parts if n not in used and pred(n)]
        if not names:
            continue
        used.update(names)
        meshes[g], _ = group_mesh(parts, names, 0.0002)
    left = [n for n in parts if n not in used]
    assert not left, left                            # safety check: every part must be used once
    # Collision skin: one closed shape around the whole aircraft
    meshes["collision"] = shrink_wrap_points(list(parts.values()), pitch=0.008, tol=0.0015)
    skin = meshes["collision"]
    lowest_z = skin.bounds[0, 2]                     # lowest point of the skin (the belly/wheels)

    # --- 7. Write the SDF text (the model's blueprint) ---
    def sdf(model_name, port):
        """Return the full text of model.sdf for one model folder."""
        # Mesh addresses inside Gazebo: model://<name>/meshes/v2/<part>.stl
        uri = lambda n: f"model://{model_name}/meshes/v2/{n}.stl"
        # Only write visuals for groups that exist (the no-pod variant has no pod group)
        base_vis = "".join(visual(g, uri(g), c) for g, (c, _) in BASE_GROUPS.items() if g in meshes)
        I = np.array(mp["inertia_about_cg"])         # total inertia matrix from mass_properties
        moving_mass = 0.0                            # running total of the guessed moving-part masses
        links = ""                                   # text of all the <link> blocks
        J = ""                                       # text of all the <joint> blocks
        # Description of every moving motor/servo link:
        # (link, parent, joint, axis, lower limit, upper limit, damping, kind, guessed mass kg)
        spec = [
            ("fl_tilt_link", "base_link", "fl_tilt_joint", (0, 1, 0), 0.0, 1.5708, 0.05, "tilt", 0.03),
            ("fl_motor_link", "fl_tilt_link", "fl_motor_joint", (0, 0, 1), -1e16, 1e16, 0.0001, "motor", 0.06),
            ("fr_tilt_link", "base_link", "fr_tilt_joint", (0, 1, 0), 0.0, 1.5708, 0.05, "tilt", 0.03),
            ("fr_motor_link", "fr_tilt_link", "fr_motor_joint", (0, 0, 1), -1e16, 1e16, 0.0001, "motor", 0.06),
            ("rear_yaw_link", "base_link", "rear_yaw_joint", (1, 0, 0), -0.524, 0.524, 0.05, "tilt", 0.03),
            ("rear_motor_link", "rear_yaw_link", "rear_motor_joint", (0, 0, 1), -1e16, 1e16, 0.0001, "motor", 0.06),
        ]
        for link, parent, jn, axis, lo, hi, damp, kind, mass in spec:
            # joint position relative to the parent link (base_link is the frame origin)
            rel = link_origin[link] - (link_origin[parent] if parent != "base_link" else 0)
            J += joint(jn, parent, link, rel, axis, lo, hi, damp)
            moving_mass += mass
            prop = ""
            if kind == "motor":
                # A transparent disc, drawn on motor links, to show where the propeller sweeps
                prop = """      <visual name="prop">
        <pose>0 0 0.025 0 0 0</pose>
        <geometry><cylinder><radius>0.089</radius><length>0.002</length></cylinder></geometry>
        <material><ambient>0.1 0.1 0.1 0.35</ambient><diffuse>0.1 0.1 0.1 0.35</diffuse></material>
        <transparency>0.6</transparency>
      </visual>
"""
            # Small inertias for the moving links (they are light and short)
            ii = (0.0001, 0.0001, 0.0001) if kind == "tilt" else (2e-5, 2e-5, 3e-5)
            links += f"""    <link name="{link}">
      <pose relative_to="{jn}">0 0 0 0 0 0</pose>
{inertial(mass, ii)}{visual(link + "_visual", uri(link), LINK_COLOUR[kind])}{prop}    </link>
"""
        # Control surfaces: revolute joints on base_link, each with a small guessed mass
        for link, (pos, axis) in surf.items():
            jn = link + "_joint"
            J += joint(jn, "base_link", link, pos, axis, -0.4, 0.4)   # about +/-23 degrees
            links += f"""    <link name="{link}">
      <pose relative_to="{jn}">0 0 0 0 0 0</pose>
{inertial(0.01)}{visual(link + "_visual", uri(link), LINK_COLOUR["surface"])}    </link>
"""
        # The body (base_link) takes all the mass that is left after the moving parts
        # (0.04 kg = the four control surfaces)
        base_mass = mp["mass_kg"] - moving_mass - 0.04

        # ---- Aerodynamics: the air forces on the wings, V-tail and body ----
        # Manual values: wing area 0.265 m^2, mean chord 0.211 m, E205 airfoil, aspect ratio 5.6.
        # 3D lift slope 4.3 per radian, zero-lift angle 0.063 rad (about 3.6 degrees).
        aero = ""
        # Wing: three spanwise elements per side (centre, inboard, outboard with aileron)
        aero += liftdrag("Wing centre section (under fuselage)", "base_link", (0.0, 0, 0.02), 0.068,
                         (0, 0, 1), 0.063, 4.3, 0.13, 0.19)
        for s, y in (("left", 1), ("right", -1)):   # left (+y) and right (-y) sides
            aero += liftdrag(f"Wing inboard panel {s}", "base_link", (0.008, 0.23 * y, 0.025), 0.038,
                             (0, 0, 1), 0.063, 4.3, 0.13, 0.19)
            # Outboard panel: its lift also depends on the aileron angle (rad_to_cl = -1.6)
            aero += liftdrag(f"Wing outboard panel {s} + aileron", "base_link", (-0.004, 0.47 * y, 0.028), 0.0605,
                             (0, 0, 1), 0.063, 4.3, 0.13, 0.19, cj=f"aileron_{s}_joint", rad_to_cl=-1.6)
        # V-tail: two panels at 35 degrees, each driven by its ruddervator joint.
        # A positive ruddervator angle turns the trailing edge UP.
        dih = np.radians(35.0)
        for s, y in (("left", 1), ("right", -1)):
            n = (0, -np.sin(dih) * y, np.cos(dih))   # lift direction: tilted by the dihedral angle
            aero += liftdrag(f"V-tail panel {s} + ruddervator", "base_link", (-0.55, 0.115 * y, 0.085), 0.0322,
                             n, 0.0, 3.0, 0.10, 0.30, cj=f"ruddervator_{s}_joint", rad_to_cl=-1.5)
        # Parasite drag: the drag of the fuselage, box, booms and motors (not lift).
        # A zero-lift element with a0 = 1 rad gives drag that is almost constant.
        # Its area is set per version so the whole aircraft matches the CFD drag at
        # 0 deg: with the box CD 0.0665, without 0.0583 (on 0.2207 m^2).
        pa = parasite_area(variant)
        aero += liftdrag(f"Parasite drag: {pa:.4f} m2 x Cd {PARASITE_CD} (no lift), matches CFD CD0 {CFD_CD0[variant]}",
                         "base_link", (0, 0, 0), round(pa, 4), (0, 0, 1), 1.0, 0.0, PARASITE_CD, 10.0,
                         cla_stall=0.0, cda_stall=0.0)

        # ---- The autopilot link (ArduPilot JSON bridge) ----
        # ArduPilot runs as a separate program. This plugin exchanges packets with it:
        #   Gazebo -> autopilot: IMU, GPS, position, attitude.
        #   autopilot -> Gazebo: PWM values for all motors and servos (the control channels).
        ap = f"""    <plugin name="ArduPilotPlugin" filename="libArduPilotPlugin.so">
      <fdm_addr>127.0.0.1</fdm_addr>
      <fdm_port_in>{port}</fdm_port_in>
      <connectionTimeoutMaxCount>5</connectionTimeoutMaxCount>
      <lock_step>1</lock_step>
      <no_time_sync>1</no_time_sync>
      <have_32_channels>0</have_32_channels>
      <modelXYZToAirplaneXForwardZDown degrees="true">0 0 0 180 0 0</modelXYZToAirplaneXForwardZDown>
      <gazeboXYZToNED degrees="true">0 0 0 180 0 0</gazeboXYZToNED>
      <imuName>imu_sensor</imuName>
      <!-- ch0 SERVO1 Motor1 front-right (CCW) / ch1 SERVO2 Motor2 front-left (CW) / ch2 SERVO3 Motor4 rear (CCW) -->
{control(0, "fr_motor_joint", "VELOCITY", MOTOR_OMEGA_MAX, 0)}{control(1, "fl_motor_joint", "VELOCITY", -MOTOR_OMEGA_MAX, 0)}{control(2, "rear_motor_joint", "VELOCITY", MOTOR_OMEGA_MAX, 0)}      <!-- ch3 SERVO4 tilt: 1000 = up (hover), 2000 = forward -->
{control(3, "fl_tilt_joint", "POSITION", 1.5708, 0, (10.0, 0.5, 10.0))}{control(3, "fr_tilt_joint", "POSITION", 1.5708, 0, (10.0, 0.5, 10.0))}      <!-- ch4 SERVO5 rear yaw servo -->
{control(4, "rear_yaw_joint", "POSITION", -0.524, -0.5, (10.0, 0.5, 10.0))}      <!-- ch5 SERVO6 ailerons: roll right = left TE down, right TE up -->
{control(5, "aileron_left_joint", "POSITION", -0.70)}{control(5, "aileron_right_joint", "POSITION", 0.70)}      <!-- ch6 SERVO7 V-tail left (79), ch7 SERVO8 V-tail right (80): PWM up = TE up -->
{control(6, "ruddervator_left_joint", "POSITION", 0.70)}{control(7, "ruddervator_right_joint", "POSITION", 0.70)}    </plugin>
"""
        # Assemble the whole model.sdf document
        return f"""<?xml version="1.0"?>
<!-- SDF file: a blueprint for Gazebo. Generated by build_stallion_v2_model.py. Do not edit by hand. -->
<sdf version="1.9">
  <!--
    Flightory Stallion V2 VTOL ({variant}) — GENERATED by scripts/build_stallion_v2_model.py
    from the repaired CAD (GLB). Do not hand-edit: change the script and re-run.
    Origin = CG target (manual: 60 mm aft of wing-root LE). AUW {mp['mass_kg']*1000:.0f} g (estimate).
    Mass and drag from the CFD study (0.8 mm walls): printed plastic {printed*1000:.0f} g, box 40 g.
    Battery assumed {shift*1000:.0f} mm forward of the CAD's provisional position to hit that CG.
  -->
  <model name="{model_name}">
    <self_collide>false</self_collide>           <!-- parts of the aircraft do not collide with each other -->
    <link name="base_link">                      <!-- the main body: fuselage, wings, V-tail, sensors -->
      <pose>0 0 {-lowest_z + 0.002:.4f} 0 0 0</pose>   <!-- lift the model so its lowest point is 2 mm above the ground -->
{inertial(base_mass, (I[0,0], I[1,1], I[2,2]), f"{f3(cg_offset)} 0 0 0", ixz=I[0,2])}      <collision name="shrinkwrap_collision">   <!-- what the ground touches -->
        <geometry><mesh><uri>{uri("collision")}</uri></mesh></geometry>
        <surface><friction><ode><mu>0.8</mu><mu2>0.8</mu2></ode></friction></surface>   <!-- grip with the ground -->
      </collision>
{base_vis}      <sensor name="imu_sensor" type="imu">   <!-- virtual IMU: gyro + accelerometer read by the autopilot -->
        <pose>0 0 0 3.141593 0 0</pose>
        <always_on>1</always_on>
        <update_rate>1000.0</update_rate>            <!-- 1000 samples per second -->
      </sensor>
    </link>
{J}{links}
    <plugin name="gz::sim::systems::JointStatePublisher" filename="gz-sim-joint-state-publisher-system"/>  <!-- publishes joint angles -->
{prop_liftdrag("fl_motor_link", 1)}{prop_liftdrag("fr_motor_link", -1)}{prop_liftdrag("rear_motor_link", -1)}
{aero}
{ap}  </model>
</sdf>
"""

    # --- 8. Write the files for every model in this variant ---
    for model_name, port in VARIANTS[variant]["models"]:
        d = os.path.join(MODELS, model_name, "meshes", "v2")
        os.makedirs(d, exist_ok=True)                # create the folders if missing
        for n, m in meshes.items():                  # export every mesh as an STL file
            m.export(os.path.join(d, f"{n}.stl"))
        with open(os.path.join(MODELS, model_name, "model.sdf"), "w") as f:
            f.write(sdf(model_name, port))           # write the blueprint
        print(f"wrote {model_name}: {len(meshes)} meshes, "
              f"{sum(len(m.faces) for m in meshes.values())} faces, AUW {mp['mass_kg']*1000:.0f} g, "
              f"CG offset from origin {np.round(cg_offset * 1000, 1).tolist()} mm")
    # Useful summary printed at the end
    print("joints:", {k: np.round(v, 3).tolist() for k, v in link_origin.items()})
    print("surface axes:", {k: np.round(v[1], 3).tolist() for k, v in surf.items()})


# Run only when started directly from the command line
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the Gazebo model of the Stallion V2 from the repaired GLB.")
    ap.add_argument("glb", help="the repaired GLB file (inputs/stallion_v2_pod_repaired.glb)")
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="pod",
                    help="pod = with vial pod (default), nopod = without the pod")
    args = ap.parse_args()
    build(args.glb, args.variant)
