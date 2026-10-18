#!/usr/bin/env python3
"""
build_stallion_v2_model.py — generate the Gazebo model from the Stallion V2 GLB.

    python3 scripts/build_stallion_v2_model.py stallion_v2_pod_repaired.glb

Writes, for both gazebo/models/stallion_vtol and stallion_vtol_2:
  meshes/v2/*.stl   visual meshes, one per link/colour group, in link frames
  meshes/v2/collision.stl   whole-aircraft shrink-wrap (closed, low-poly)
  model.sdf         links, joints, aero, ArduPilot plugin

Frame: FLU (x fwd, y left, z up). Model origin = CG target from the manual
(60 mm aft of the wing-root leading edge), z at the computed CG height.
Geometry (hinges, motor positions, V-tail angle, areas) is measured from the
CAD; aero coefficients come from the manual (E205 airfoil, 26.5 dm2, MAC 211 mm).
Run scripts/mesh_repair.py on the raw GLB first.
"""
import argparse
import os

import numpy as np
import trimesh

from mass_properties import GLTF_TO_FLU, compute
from mesh_check import load_parts

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.path.join(HERE, "..", "gazebo", "models")

BATTERY_SHIFT = 0.057        # m forward of the CAD's provisional spot -> manual CG
CG_AFT_OF_ROOT_LE = 0.060    # manual

# link name -> list of CAD part-name prefixes (exact names or "NAME [n]")
MOVING = {
    "fl_tilt_link":  ["MOTOR MOUNT FRONT [2]"],
    "fl_motor_link": ["MOTOR LEFT"],
    "fr_tilt_link":  ["MOTOR MOUNT FRONT"],
    "fr_motor_link": ["MOTOR RIGHT"],
    "rear_yaw_link": ["MOTOR MOUNT TAIL"],
    "rear_motor_link": ["MOTOR TAIL"],
    "aileron_left":  ["AILERON 1L", "AILERON 2L"],
    "aileron_right": ["AILERON 1R", "AILERON 2R"],
    "ruddervator_left":  ["RUDDER 1L", "RUDDER 2L"],
    "ruddervator_right": ["RUDDER 1R", "RUDDER 2R"],
}
# base_link visual groups: name -> (colour rgb, predicate)
BASE_GROUPS = {
    "airframe": ((1.0, 0.45, 0.1), lambda n: not any(k in n for k in
                 ["WING", "V TAIL", "CARBON", "VIAL", "SERVO -", "SERVO RIGHT", "SERVO LEFT",
                  "FC -", "RX -", "BATTERY -", "USB"])),
    "wings": ((0.95, 0.95, 0.95), lambda n: ("WING" in n or "V TAIL" in n)),
    "carbon": ((0.12, 0.12, 0.12), lambda n: n.startswith("CARBON")),
    "pod": ((0.3, 0.75, 0.35), lambda n: "VIAL" in n),
    "electronics": ((0.85, 0.15, 0.15), lambda n: any(k in n for k in
                    ["SERVO -", "SERVO RIGHT", "SERVO LEFT", "FC -", "RX -", "BATTERY -", "USB"])),
}
LINK_COLOUR = {"motor": (0.1, 0.1, 0.1), "tilt": (0.3, 0.3, 0.3), "surface": (0.25, 0.55, 0.95)}


def match(parts, prefixes):
    """CAD names are either exact ("AILERON 1L") or "PREFIX - catalogue name"."""
    out = []
    for p in prefixes:
        hits = [n for n in parts if n == p or n.startswith(p + " -")]
        if not hits:
            raise KeyError(p)
        out += hits
    return out


def simplify_part(m, tol):
    """Manifold-preserving simplification of one closed part (falls back to the original)."""
    import manifold3d
    from mesh_check import check
    try:
        man = manifold3d.Manifold(manifold3d.Mesh(m.vertices.astype(np.float32), m.faces.astype(np.uint32)))
        o = man.simplify(tol).to_mesh()
        out = clean_degenerate(trimesh.Trimesh(o.vert_properties[:, :3], o.tri_verts))
        if check(out)["clean"] and len(out.faces) > 0:
            return out
    except Exception:
        pass
    return m


def clean_degenerate(m):
    """Collapse zero-area slivers by welding near-coincident vertices (keeps the mesh closed)."""
    m.merge_vertices(digits_vertex=5)
    m.update_faces(m.nondegenerate_faces(height=1e-9))
    m.remove_unreferenced_vertices()
    m.merge_vertices()
    trimesh.repair.fill_holes(m)
    trimesh.repair.fix_normals(m)
    return m


def group_mesh(parts, names, tol):
    """Simplify each part separately (so every part stays a clean solid), then combine."""
    from mesh_check import check
    pieces = [simplify_part(parts[n], tol) for n in names]
    bad = [n for n, p in zip(names, pieces) if not check(p)["clean"]]
    if bad:
        raise RuntimeError(f"unclean parts: {bad}")
    return trimesh.util.concatenate(pieces), len(names)


def hinge(meshes, flip=False):
    """Hinge = forward edge of a control surface, axis = its span direction."""
    v = np.vstack([m.vertices for m in meshes])
    c = v.mean(0)
    w, U = np.linalg.eigh((v - c).T @ (v - c))
    axis = U[:, -1] / np.linalg.norm(U[:, -1])
    if axis[1] < 0:            # point spanwise toward +y ...
        axis = -axis
    if flip:                   # ... except right V-tail panel (keeps +angle = TE up)
        axis = -axis
    front = v[v[:, 0] > np.percentile(v[:, 0], 90)].mean(0)
    pos = np.array([front[0], c[1], c[2]])
    return pos, axis


def shrink_wrap_points(mesh_list, pitch, tol=0.001):
    """Closed outer skin: rasterise surface samples, close gaps, fill, thicken by one
    voxel (so thin plates stay manifold), marching cubes, then manifold-preserving
    simplification. Result is watertight with no non-manifold edges."""
    import manifold3d
    from scipy import ndimage
    from skimage import measure
    pts = np.vstack([m.sample(max(2000, int(m.area / pitch**2 * 4)), seed=0) for m in mesh_list])
    lo = pts.min(0) - 3 * pitch
    idx = np.floor((pts - lo) / pitch).astype(int)
    grid = np.zeros(idx.max(0) + 4, bool)
    grid[tuple(idx.T)] = True
    grid = ndimage.binary_closing(grid, iterations=1)
    grid = ndimage.binary_fill_holes(grid)
    grid = ndimage.binary_dilation(grid, iterations=1)
    grid = ndimage.binary_opening(grid, structure=np.ones((2, 2, 2)))   # drop edge-only voxel contacts
    labels, n = ndimage.label(grid)
    grid = labels == (np.argmax(ndimage.sum(grid, labels, range(1, n + 1))) + 1)
    v, f, _, _ = measure.marching_cubes(np.pad(grid, 1).astype(np.uint8), 0.5)
    skin = trimesh.Trimesh((v - 1) * pitch + lo, f)
    skin.merge_vertices()
    if skin.volume < 0:
        skin.invert()
    from mesh_check import check
    m = manifold3d.Manifold(manifold3d.Mesh(skin.vertices.astype(np.float32), skin.faces.astype(np.uint32)))
    # try a few tolerances; keep the lightest result that is fully clean
    for t in (tol * 1.5, tol, tol * 0.75, tol * 0.5):
        o = m.simplify(t).to_mesh()
        out = trimesh.Trimesh(o.vert_properties[:, :3], o.tri_verts)
        if check(out)["clean"]:
            return out
    return skin


def f3(v):
    return " ".join(f"{x:.4f}" for x in v)


def visual(name, uri, rgb):
    r, g, b = rgb
    return f"""      <visual name="{name}">
        <geometry><mesh><uri>{uri}</uri></mesh></geometry>
        <material><ambient>{r} {g} {b} 1</ambient><diffuse>{r} {g} {b} 1</diffuse><specular>0.2 0.2 0.2 1</specular></material>
      </visual>
"""


def inertial(mass, i=(1e-5, 1e-5, 1e-5), pose="0 0 0 0 0 0", ixz=0.0):
    return f"""      <inertial>
        <pose>{pose}</pose>
        <mass>{mass:.4f}</mass>
        <inertia><ixx>{i[0]:.5f}</ixx><ixy>0</ixy><ixz>{ixz:.5f}</ixz><iyy>{i[1]:.5f}</iyy><iyz>0</iyz><izz>{i[2]:.5f}</izz></inertia>
      </inertial>
"""


def joint(name, parent, child, pos, axis, lower, upper, damping=0.01):
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


# Prop blade-element model calibrated to EMAX ECO II 2807 1300KV, 4S, 7x4 prop:
# 15,400 rpm loaded (1610 rad/s), element at 75% radius, ~17 N static thrust per motor.
PROP_R, PROP_A0, PROP_CLA, PROP_AREA, MOTOR_OMEGA_MAX = 0.0667, 0.28, 5.0, 0.000874, 1610


def prop_liftdrag(link, sign):
    """Two blade elements per prop."""
    out = ""
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
    if kind == "VELOCITY":
        g = """        <type>VELOCITY</type>
        <p_gain>0.20</p_gain><i_gain>0</i_gain><d_gain>0</d_gain><i_max>0</i_max><i_min>0</i_min>
        <cmd_max>2.5</cmd_max><cmd_min>-2.5</cmd_min>
        <controlVelocitySlowdownSim>1</controlVelocitySlowdownSim>"""
    else:
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


def build(glb):
    parts = load_parts(glb)
    for m in parts.values():
        m.apply_transform(GLTF_TO_FLU)
    root_le_x = parts["WING ROOT L"].bounds[1, 0]
    mp = compute(glb, 1.0, BATTERY_SHIFT)
    origin = np.array([root_le_x - CG_AFT_OF_ROOT_LE, 0.0, mp["cg_flu_m"][2]])
    for n, m in parts.items():
        m.apply_translation(-origin)
        if n.startswith("BATTERY -"):
            m.apply_translation([BATTERY_SHIFT, 0, 0])

    # ---------- joints from CAD ----------
    def centre(prefixes):
        return trimesh.util.concatenate([parts[n] for n in match(parts, prefixes)]).bounds.mean(0)

    j = {}
    for side, mount, motor in (("fl", "MOTOR MOUNT FRONT [2]", "MOTOR LEFT"), ("fr", "MOTOR MOUNT FRONT", "MOTOR RIGHT")):
        mb = trimesh.util.concatenate([parts[n] for n in match(parts, [mount])]).bounds
        mc = centre([motor])
        j[f"{side}_tilt"] = np.array([mc[0], mc[1], mb[0, 2] + 0.006])     # pivot near mount base
        j[f"{side}_motor"] = mc
    tb = trimesh.util.concatenate([parts[n] for n in match(parts, ["MOTOR MOUNT TAIL"])]).bounds
    j["rear_yaw"] = np.array([centre(["MOTOR TAIL"])[0], 0.0, tb.mean(0)[2]])
    j["rear_motor"] = centre(["MOTOR TAIL"])
    surf = {}
    for link, flip in (("aileron_left", False), ("aileron_right", False),
                       ("ruddervator_left", False), ("ruddervator_right", False)):
        surf[link] = hinge([parts[n] for n in match(parts, MOVING[link])], flip=flip)
    link_origin = {
        "fl_tilt_link": j["fl_tilt"], "fl_motor_link": j["fl_motor"],
        "fr_tilt_link": j["fr_tilt"], "fr_motor_link": j["fr_motor"],
        "rear_yaw_link": j["rear_yaw"], "rear_motor_link": j["rear_motor"],
        **{k: v[0] for k, v in surf.items()},
    }

    # ---------- meshes ----------
    used = set()
    meshes = {}
    for link, prefixes in MOVING.items():
        names = match(parts, prefixes)
        used.update(names)
        m, _ = group_mesh(parts, names, 0.0002)
        m.apply_translation(-link_origin[link])
        meshes[link] = m
    for g, (_, pred) in BASE_GROUPS.items():
        names = [n for n in parts if n not in used and pred(n)]
        used.update(names)
        meshes[g], _ = group_mesh(parts, names, 0.0002)
    left = [n for n in parts if n not in used]
    assert not left, left

    # whole-aircraft shrink-wrap for collision
    meshes["collision"] = shrink_wrap_points(list(parts.values()), pitch=0.008, tol=0.0015)
    skin = meshes["collision"]
    lowest_z = skin.bounds[0, 2]

    # ---------- SDF ----------
    def sdf(model_name, port):
        uri = lambda n: f"model://{model_name}/meshes/v2/{n}.stl"
        base_vis = "".join(visual(g, uri(g), c) for g, (c, _) in BASE_GROUPS.items())
        I = np.array(mp["inertia_about_cg"])
        moving_mass = 0.0
        links = ""
        J = ""
        spec = [
            ("fl_tilt_link", "base_link", "fl_tilt_joint", (0, 1, 0), 0.0, 1.5708, 0.05, "tilt", 0.03),
            ("fl_motor_link", "fl_tilt_link", "fl_motor_joint", (0, 0, 1), -1e16, 1e16, 0.0001, "motor", 0.06),
            ("fr_tilt_link", "base_link", "fr_tilt_joint", (0, 1, 0), 0.0, 1.5708, 0.05, "tilt", 0.03),
            ("fr_motor_link", "fr_tilt_link", "fr_motor_joint", (0, 0, 1), -1e16, 1e16, 0.0001, "motor", 0.06),
            ("rear_yaw_link", "base_link", "rear_yaw_joint", (1, 0, 0), -0.524, 0.524, 0.05, "tilt", 0.03),
            ("rear_motor_link", "rear_yaw_link", "rear_motor_joint", (0, 0, 1), -1e16, 1e16, 0.0001, "motor", 0.06),
        ]
        for link, parent, jn, axis, lo, hi, damp, kind, mass in spec:
            rel = link_origin[link] - (link_origin[parent] if parent != "base_link" else 0)
            J += joint(jn, parent, link, rel, axis, lo, hi, damp)
            moving_mass += mass
            prop = ""
            if kind == "motor":
                prop = """      <visual name="prop">
        <pose>0 0 0.025 0 0 0</pose>
        <geometry><cylinder><radius>0.089</radius><length>0.002</length></cylinder></geometry>
        <material><ambient>0.1 0.1 0.1 0.35</ambient><diffuse>0.1 0.1 0.1 0.35</diffuse></material>
        <transparency>0.6</transparency>
      </visual>
"""
            ii = (0.0001, 0.0001, 0.0001) if kind == "tilt" else (2e-5, 2e-5, 3e-5)
            links += f"""    <link name="{link}">
      <pose relative_to="{jn}">0 0 0 0 0 0</pose>
{inertial(mass, ii)}{visual(link + "_visual", uri(link), LINK_COLOUR[kind])}{prop}    </link>
"""
        for link, (pos, axis) in surf.items():
            jn = link + "_joint"
            J += joint(jn, "base_link", link, pos, axis, -0.4, 0.4)
            links += f"""    <link name="{link}">
      <pose relative_to="{jn}">0 0 0 0 0 0</pose>
{inertial(0.01)}{visual(link + "_visual", uri(link), LINK_COLOUR["surface"])}    </link>
"""
        base_mass = mp["mass_kg"] - moving_mass - 0.04

        # ---- aero (manual: S=0.265 m2, MAC 0.211, E205, AR 5.6) ----
        # 3D lift slope 4.3/rad, zero-lift offset 0.063 rad (E205 Cl0 ~0.27)
        aero = ""
        aero += liftdrag("Wing centre section (under fuselage)", "base_link", (0.0, 0, 0.02), 0.068,
                         (0, 0, 1), 0.063, 4.3, 0.13, 0.19)
        for s, y in (("left", 1), ("right", -1)):
            aero += liftdrag(f"Wing inboard panel {s}", "base_link", (0.008, 0.23 * y, 0.025), 0.038,
                             (0, 0, 1), 0.063, 4.3, 0.13, 0.19)
            aero += liftdrag(f"Wing outboard panel {s} + aileron", "base_link", (-0.004, 0.47 * y, 0.028), 0.0605,
                             (0, 0, 1), 0.063, 4.3, 0.13, 0.19, cj=f"aileron_{s}_joint", rad_to_cl=-1.6)
        # V-tail: 35 deg panels, measured normals; positive ruddervator angle = TE up
        dih = np.radians(35.0)
        for s, y in (("left", 1), ("right", -1)):
            n = (0, -np.sin(dih) * y, np.cos(dih))
            aero += liftdrag(f"V-tail panel {s} + ruddervator", "base_link", (-0.55, 0.115 * y, 0.085), 0.0322,
                             n, 0.0, 3.0, 0.10, 0.30, cj=f"ruddervator_{s}_joint", rad_to_cl=-1.5)
        # Parasite drag (fuselage, pod, booms, motors): LiftDrag drag is ~cda*|alpha|,
        # so a no-lift element with a0 = 1 rad gives a near-constant CdA = 0.054*0.20.
        aero += liftdrag("Parasite drag: frontal area 5.4 dm2 x Cd 0.20 (no lift)", "base_link", (0, 0, 0),
                         0.054, (0, 0, 1), 1.0, 0.0, 0.20, 10.0, cla_stall=0.0, cda_stall=0.0)

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
        return f"""<?xml version="1.0"?>
<sdf version="1.9">
  <!--
    Flightory Stallion V2 VTOL (with vial pod) — GENERATED by scripts/build_stallion_v2_model.py
    from the repaired CAD (GLB). Do not hand-edit: change the script and re-run.
    Origin = CG target (manual: 60 mm aft of wing-root LE). AUW {mp['mass_kg']*1000:.0f} g (estimate).
    Battery assumed {BATTERY_SHIFT*1000:.0f} mm forward of the CAD's provisional position to hit that CG.
  -->
  <model name="{model_name}">
    <self_collide>false</self_collide>
    <link name="base_link">
      <pose>0 0 {-lowest_z + 0.002:.4f} 0 0 0</pose>
{inertial(base_mass, (I[0,0], I[1,1], I[2,2]), f"{f3([0, 0, 0])} 0 0 0", ixz=I[0,2])}      <collision name="shrinkwrap_collision">
        <geometry><mesh><uri>{uri("collision")}</uri></mesh></geometry>
        <surface><friction><ode><mu>0.8</mu><mu2>0.8</mu2></ode></friction></surface>
      </collision>
{base_vis}      <sensor name="imu_sensor" type="imu">
        <pose>0 0 0 3.141593 0 0</pose>
        <always_on>1</always_on>
        <update_rate>1000.0</update_rate>
      </sensor>
    </link>
{J}{links}
    <plugin name="gz::sim::systems::JointStatePublisher" filename="gz-sim-joint-state-publisher-system"/>
{prop_liftdrag("fl_motor_link", 1)}{prop_liftdrag("fr_motor_link", -1)}{prop_liftdrag("rear_motor_link", -1)}
{aero}
{ap}  </model>
</sdf>
"""

    for model_name, port in (("stallion_vtol", 9002), ("stallion_vtol_2", 9012)):
        d = os.path.join(MODELS, model_name, "meshes", "v2")
        os.makedirs(d, exist_ok=True)
        for n, m in meshes.items():
            m.export(os.path.join(d, f"{n}.stl"))
        with open(os.path.join(MODELS, model_name, "model.sdf"), "w") as f:
            f.write(sdf(model_name, port))
        print(f"wrote {model_name}: {len(meshes)} meshes, "
              f"{sum(len(m.faces) for m in meshes.values())} faces")
    print("joints:", {k: np.round(v, 3).tolist() for k, v in link_origin.items()})
    print("surface axes:", {k: np.round(v[1], 3).tolist() for k, v in surf.items()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("glb")
    build(ap.parse_args().glb)
