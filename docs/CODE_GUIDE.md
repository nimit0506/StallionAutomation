# Stallion V2 simulation — code guide

This explains every piece of the code in this repo, in the order you would use it:
turn the CAD into a physics model, check the model, fly it, and render the results.
The steps to rerun everything are in [`README.md`](../README.md).

---

## 1. The big picture

```
inputs/stallion_v2_equipped_with_pod.glb   CAD export (96 parts, glTF, y-up)
        │  scripts/mesh_check.py          which parts are bad? (open, non-manifold, sheets…)
        │  scripts/mesh_repair.py         fix bad parts (basic repair, else shrink-wrap)
        ▼
inputs/stallion_v2_pod_repaired.glb       all 96 parts clean
        │  scripts/mass_properties.py     mass, centre of gravity, inertia
        │  scripts/build_stallion_v2_model.py
        ▼
gazebo/models/stallion_vtol/              model.sdf (links, joints, aerodynamics, autopilot link)
                                          meshes/v2/*.stl (visual + one collision skin)
        │
        │  gazebo/worlds/stallion_runway.sdf loads the model
        ▼
Gazebo (physics, 1 kHz)  ◀──── JSON over UDP 9002 ────▶  ArduPlane SITL (autopilot)
        │                                                    │ MAVLink TCP 5760
        │                                                    ▼
        │                                              MAVProxy → UDP 14550
        │                                                    ▼
        │                                          scripts/sitl_hover_check.py
        │                                          (arm, climb, hold, transition, land)
        ▼                                                    ▼
  scripts/run_headless_test.sh starts all of this    logs/ and results/*.csv
                                                             ▼
                                   scripts/render_sim_images.sh → results/images/
```

Two things are simulated by two programs that talk every step:

- **Gazebo** computes the aircraft's motion from its mass, shape and aerodynamic
  model. It has no idea how to fly the aircraft.
- **ArduPlane SITL** is the real ArduPilot flight code, compiled for a PC. It reads
  the simulated sensors (accelerometer, gyro, GPS) and sends back motor and servo
  commands, exactly as it would on the flight controller. The only thing that differs
  from a real aircraft is that the sensor data comes from Gazebo.

The two talk over UDP in **lock-step**: Gazebo waits for the autopilot's servo
packet before it advances physics, and the autopilot waits for the sensor packet. That
keeps the test repeatable at any simulation speed.

---

## 2. Folder map

| Path | What it is |
|---|---|
| `inputs/` | The raw CAD export and the repaired version the model is built from |
| `scripts/mesh_check.py` | Topology check for each CAD part; also the loader used by the other scripts |
| `scripts/mesh_repair.py` | Repairs the parts that fail the check |
| `scripts/mass_properties.py` | Mass, centre of gravity and inertia estimate |
| `scripts/build_stallion_v2_model.py` | Generates the Gazebo model from the repaired GLB |
| `scripts/sim_model.scad` | OpenSCAD scene for the sim images (uses the same meshes) |
| `scripts/render_sim_images.sh` | Renders five views into `results/images/` |
| `scripts/sitl_hover_check.py` | The automated flight test |
| `scripts/run_headless_test.sh` | Starts Gazebo + SITL + MAVProxy and runs the flight test |
| `scripts/launch_gazebo_only.sh`, `scripts/launch_sitl_only.sh` | Same setup by hand, with GUI |
| `gazebo/worlds/stallion_runway.sdf` | World: flat ground, both airframes placed on the runway |
| `gazebo/models/stallion_vtol/` | Airframe 1, flown by SITL on UDP 9002 |
| `gazebo/models/stallion_vtol_2/` | Airframe 2, identical copy, spawned but not connected to an autopilot |
| `params/stallion_vtol_sitl.parm` | ArduPlane parameters (QuadPlane, tilt-rotor, servo mapping, tuning) |
| `docs/` | This guide and the slides |
| `results/` | Flight logs, summary, mesh checks, sim images |

---

## 3. The CAD and the mesh tools

The CAD export has 96 named parts (for example `FUS 2L`, `AILERON 1L`, `MOTOR LEFT`,
`BATTERY - …`). Each part is a separate triangle mesh.

### 3.1 `mesh_check.py`

`check(mesh)` tests one part and returns a dictionary. A part is **clean** when all of
these hold:

- `watertight`: every edge is shared by exactly two faces (no holes).
- `winding`: all faces are oriented consistently.
- `inverted`: the volume is not negative (faces point inward).
- `degenerate`, `duplicate`: no zero-area or doubled triangles.
- `nonmanifold`: no edge shared by more than two faces.

It also reports `open_edges` and a `sheet` flag for parts thinner than 1.5 mm (a
collision mesh cannot be built from a sheet that thin).

`load_parts(path)` loads a GLB into one mesh per part. It welds the vertices first,
because STL stores each triangle separately and would look "open" otherwise. It also
applies each part's scene transform, so every part sits where the CAD put it.

Run it with `python3 scripts/mesh_check.py <file.glb>`. It prints one line per part, and
the lines marked `<-- needs repair` are the ones `mesh_repair.py` will touch.

### 3.2 `mesh_repair.py`

For each part that fails the check, `repair()` tries two things in order:

1. **Basic repair** (`basic_repair`): merge vertices, drop duplicate and degenerate
   faces, fix winding, fill holes, fix normals. This is the cheap, faithful fix, and
   it keeps the shape exactly.
2. **Shrink-wrap** (`shrink_wrap`), only if step 1 still fails: voxelise the part at
   1.5 mm, fill the voxels, and rebuild a closed surface with marching cubes (smoothed
   with Taubin filtering). This always produces a closed solid, but it slightly rounds
   sharp edges. A thin sheet gets at least two voxels so it does not vanish.

On the raw export, 28 of 96 parts needed repair (see
`results/mesh/mesh_check_before.txt`). Basic repair fixed some of them. Shrink-wrap was
needed for the rest, mostly the nose, booms and hatches, which had holes or
non-manifold edges. After repair all 96 are clean
(`results/mesh/mesh_check_after.txt`). The result is written as a new GLB.

### 3.3 `mass_properties.py`

Mass, centre of gravity (CG) and inertia are estimated from the repaired GLB. The
estimate is in the flight-control frame (x forward, y left, z up), converted from glTF
with `GLTF_TO_FLU`.

- **Printed parts** are only a surface area, so their total mass is spread in
  proportion to surface area. The total is an **assumed** 1.0 kg for the printed
  airframe. That number has not been weighed. Replacing it with the real printed mass
  is the most useful correction to make.
- **Carbon** parts use their volume × 1.6 g/cm³.
- **Electronics** (motors 48 g, servos 13.4 g and 12 g, flight controller 10 g, receiver
  19 g, battery 730 g, pod 75 g each) use catalogue masses, placed at their CAD positions.
- **Parts that are not in the CAD** (three propellers 36 g in total, three ESCs 75 g,
  wiring 80 g) are added as point masses at their mounting parts.

The battery is moved forward by `--battery-shift` (0.057 m in the build) so the CG
lands where the manual puts it: 60 mm aft of the wing-root leading edge.

Result (from `results/mesh/mass.json`):

- Total mass (all-up weight): **2451 g** (estimate)
- CG: **60.0 mm** aft of the wing-root leading edge

---

## 4. Building the Gazebo model: `build_stallion_v2_model.py`

This is the most important script. It generates `gazebo/models/stallion_vtol/model.sdf`
and the meshes, from the repaired GLB. Run `python3 scripts/build_stallion_v2_model.py
inputs/stallion_v2_pod_repaired.glb`. It takes about 6 seconds, and the output is
byte-identical to the committed model, so the build is repeatable.

Edit the script, not the generated files. Each run overwrites them.

### 4.1 Frame and origin

- The model origin is the **CG target**: 60 mm aft of the wing-root leading edge
  (`CG_AFT_OF_ROOT_LE`), at the CG height from `mass_properties`.
- The base link's z-offset puts the lowest point of the collision skin 2 mm above the
  ground.

### 4.2 Moving parts: joints from the CAD

Each moving part is one link, joined to its parent by a joint. The joint positions are
measured from the CAD, not typed in:

| Link | Parent | Joint type | Axis | Range | What it is |
|---|---|---|---|---|---|
| `fl_tilt_link`, `fr_tilt_link` | base | revolute | y | 0 → 90° | Front motor tilt (hover = 0, cruise = 90°) |
| `fl_motor_link`, `fr_motor_link` | tilt link | revolute (spin) | z | free | Front motor spin |
| `rear_yaw_link` | base | revolute | x | ±30° | Rear motor sideways tilt (yaw control) |
| `rear_motor_link` | yaw link | revolute (spin) | z | free | Rear motor spin |
| `aileron_left/right` | base | revolute | span | ±23° | Ailerons on the wings |
| `ruddervator_left/right` | base | revolute | span | ±23° | V-tail surfaces (elevator + rudder mixed) |

- **Tilt pivot**: at the motor's x and y, and 6 mm above the lowest point of its mount.
- **Control-surface hinge** (`hinge`): the forward edge of the surface (its 90th
  percentile in x), with the axis along the span. The span direction is the
  largest-variance direction of the surface's vertices (principal component). The sign
  is chosen so +y points out to the side. With this rule a positive angle moves the
  trailing edge up on both V-tail panels, which the mixing relies on.

### 4.3 Meshes

- Each moving link gets its own mesh, offset so its origin is at its joint.
- The rest of the airframe is split into five colour groups: `airframe` (orange),
  `wings` (white), `carbon` (black), `pod` (green), `electronics` (red).
- `group_mesh` simplifies each CAD part separately with manifold3d (tolerance
  0.2 mm), so every part stays a clean solid, and then joins them. A simplified part is
  kept only if it is still clean. Otherwise the original is used.
- `collision.stl` is one **shrink-wrapped skin** around the whole aircraft
  (`shrink_wrap_points`). It samples the surface, voxelises it at 8 mm, closes gaps,
  keeps the largest connected piece, rebuilds the surface with marching cubes, and
  then simplifies it (tolerance 1.5 mm, then tighter if needed) until it is clean.
  Gazebo uses this for contact with the ground, so it must be closed.

### 4.4 Mass and inertia in the SDF

- The 6 moving links are given fixed guessed masses (tilt 30 g, motors 60 g, rear yaw
  30 g, surfaces 10 g each). The **base link gets the rest**, so the total still
  equals the mass from `mass_properties`.
- Inertia of the base link comes from `mass_properties`. The moving links use tiny
  placeholder inertias.

### 4.5 Aerodynamics: LiftDrag plugins

Gazebo's `LiftDrag` plugin applies a lift and drag force at a point on a link, using
the local air speed and angle of attack. Each plugin uses:

- `a0`: zero-lift angle of attack, `cla`: lift slope per radian, `cda`: drag, `stall`:
  stall angle.
- `area`, `cp` (centre of pressure), `upward` (direction of lift).
- Optionally a **control joint** and `rad_to_cl`, which adds lift when a control
  surface moves.

Values come from the manual (airfoil E205, wing area 0.265 m², mean chord 0.211 m,
aspect ratio 5.6). The wing has five elements:

- Centre section under the fuselage: area 0.068 m².
- Left and right inboard panels: 0.038 m² each.
- Left and right outboard panels with the aileron: 0.0605 m² each. Ailerons change
  the lift of these panels (`rad_to_cl = -1.6`).

The total is 0.265 m², which matches the manual.

The **V-tail** is two panels at 35° dihedral, 0.0322 m² each. They carry the
ruddervator angle as a control joint (`rad_to_cl = -1.5`). Positive ruddervator angle
means the trailing edge goes up.

**Parasite drag** (fuselage, pod, booms, motors) is one element with zero lift, drag
coefficient 0.20 and 0.054 m² frontal area (5.4 dm²). Those two values are choices
made in the code, not taken from the manual.

### 4.6 Propellers: blade-element LiftDrag

Each motor has two LiftDrag elements, placed 66.7 mm from the spin axis. Each one
produces thrust from the spin speed of the motor, so thrust rises with the square of
the speed. The constants (`PROP_R`, `PROP_A0`, `PROP_CLA`, `PROP_AREA`) were tuned so
that the static thrust matches the motor and prop combination (EMAX 2807 1300 KV,
4S, 7×4 prop). **The code comment quotes about 17 N of static thrust per motor; that
figure has not been checked against the motor datasheet, so verify it before quoting
it.** The maximum motor speed is 1610 rad/s (about 15,400 rpm).

### 4.7 The autopilot link and channel mapping

The `ArduPilotPlugin` (`libArduPilotPlugin.so`) is the bridge to SITL:

- It listens on UDP **9002** for servo packets from SITL. The second airframe uses 9012.
- `lock_step 1`: Gazebo waits for each servo packet before it moves on.
- `modelXYZToAirplaneXForwardZDown` and `gazeboXYZToNED` rotate the frames so the
  autopilot's sensors and attitude match the aircraft.
- `imu_sensor` is the IMU the autopilot reads (on the base link, 1 kHz).

Each PWM channel (0–7) of the JSON packet drives one joint. The mapping is written in
the SDF and in `params/stallion_vtol_sitl.parm`:

| JSON ch | SERVO | Joint(s) | Mapping |
|---|---|---|---|
| 0 | SERVO1 (function 33) | `fr_motor_joint` | PWM 1000–2000 → 0 … 1610 rad/s |
| 1 | SERVO2 (function 34) | `fl_motor_joint` | same, opposite spin direction |
| 2 | SERVO3 (function 36) | `rear_motor_joint` | same |
| 3 | SERVO4 (function 41) | `fl_tilt_joint`, `fr_tilt_joint` | PWM 1000 = 0° (hover), 2000 = 90° (forward) |
| 4 | SERVO5 (function 39) | `rear_yaw_joint` | ±15° around 1500 |
| 5 | SERVO6 (function 4) | aileron L and R | opposite signs, ±20° |
| 6 | SERVO7 (function 79) | `ruddervator_left_joint` | ±20° |
| 7 | SERVO8 (function 80) | `ruddervator_right_joint` | ±20° |

Each servo uses a `control` block: `POSITION` (PD) for the tilt, yaw and surfaces, and
`VELOCITY` for the motors. The `multiplier` converts the normalised PWM into the joint
unit, and `offset` centres it.

---

## 5. The world and the second airframe

`gazebo/worlds/stallion_runway.sdf` is a flat ground plane with physics at a 1 ms step
and real-time factor 1. It spawns:

- `stallion_vtol` at (0, −2.5, 0.08), flown by the SITL test;
- `stallion_vtol_2` at (0, +2.5, 0.08). This is a copy of the same model on port 9012.
  No autopilot connects to it, so it sits on the runway. It is kept because the world
  loads it, and removing it would change the setup that was tested.

---

## 6. Autopilot parameters: `params/stallion_vtol_sitl.parm`

Loaded on top of ArduPilot's default `plane.parm`. The sections:

1. **QuadPlane core**: `Q_ENABLE 1`, `Q_FRAME_CLASS 7` (tricopter with tilt),
   `Q_TILT_ENABLE 1`, `Q_TILT_MASK 3` (both front motors tilt, the rear does not).
2. **Tilt limits**: `Q_TILT_MAX 45`. The earlier hardware parameter file (removed in the
   cleanup) used 90°. With 90° the simulated aircraft dived during transition, so 45° was
   set here. `Q_TILT_RATE_UP/DN 40`.
3. **Transition**: `Q_TRANSITION_MS 5000`, `ARSPD_FBW_MIN 12`, `ARSPD_FBW_MAX 25`.
4. **Servo functions**: the mapping in section 4.7.
5. **Hover**: `Q_M_THST_HOVER 0.55` (throttle fraction for hover, starting value).
6. **PID tuning** (`Q_A_ANG_*`, `Q_A_RAT_*`): attitude gains 6.0 (roll/pitch) and 2.5 (yaw),
   rate gains 0.25 P and I with small D. These are the values the runs used.
   They are tuned for the 2.45 kg estimate, which has not been verified.
7. **Simulation overrides**: `ARMING_CHECK 0`, `BAT_MONITOR 0` (no false battery
   failsafe), `SCHED_LOOP_RATE 400` (QuadPlane needs at least 400 Hz), EKF3 on,
   `INS_USE1 1` (one IMU), compass on in the simulator.

---

## 7. The automated flight test: `sitl_hover_check.py`

It connects to MAVLink on UDP 14550 and runs a fixed sequence of flight modes:

1. **Arm**: sets `QHOVER`, sends throttle 1000, and retries arming every 3 s for up to
   180 s. SITL refuses to arm while its sensors settle, and the retry loop waits that out.
2. **Climb**: 10 s at throttle 1700 (`--climb-throttle`, `--climb-time`).
3. **Hold**: 10 s at throttle 1500 (`--hold-throttle`).
4. **Transition** (only with `--transition`): switches to `FBWB` (fixed-wing, altitude
   hold) at throttle 1800 for 30 s. The forward-flight check passes when the
   ground speed reaches 12 m/s, the altitude stays above 2 m, and the tilt stays at
   or below 45°.
5. **Back to hover**: `QHOVER` at throttle 1500 for 15 s.
6. **Land**: `QLAND`. It waits 120 s in transition mode and 15 s in hover-only mode.

**Pass criteria**

- Hover-only run: the highest altitude reached is at least `--min-alt` (3 m) and the
  maximum roll or pitch is at most `--max-tilt` (25°). **The hover verdict does not
  check that the aircraft has landed.** The landing window of 15 s is often too short
  for a 2.45 kg aircraft to get down.
- Transition run: forward flight passes (above), **and** the final altitude is below
  0.5 m, which is the landing check.

**Output**: a line every second with altitude, roll, pitch, ground speed and the
servo values. With `--csv FILE` it also writes a 10 Hz log with these columns:

```
t, phase, alt, roll, pitch, gs, aspd, tilt, ail, vtail_l, vtail_r, m_fr, m_fl, m_rear
```

`phase` is one of `climb`, `hold`, `forward`, `back_transition`, `land`. Angles are in
degrees, altitude in metres, speed in m/s, servo values are PWM, and motor values are
PWM too.

---

## 8. Running it: `run_headless_test.sh` and the launchers

`run_headless_test.sh` runs everything that the manual steps do, with no GUI:

1. Kills any stale Gazebo, SITL or MAVProxy processes.
2. Starts the Gazebo server on the world (`gz sim -s -r`) and waits 8 s.
3. Starts ArduPlane SITL with the JSON backend, the Stallion parameters and the
   Chennai home location (13.0827° N, 80.2707° E). It runs in `logs/`, so the EEPROM
   file does not end up in the repo.
4. Starts MAVProxy (TCP 5760 → UDP 14550) and waits 25 s.
5. Checks that SITL has received physics (`JSON received` in `logs/sitl.log`). If it
   has not, it stops and exits with code 3. Otherwise a start-up race can hang the test
   for the whole arming timeout. We saw this once, and a second run started cleanly.
6. Runs `sitl_hover_check.py` with the arguments you pass. Its exit code is returned
   (0 = pass).

The logs (`gz.log`, `sitl.log`, `mavproxy.log`) are written to `logs/`, which is
git-ignored.

`launch_gazebo_only.sh` and `launch_sitl_only.sh` do the same thing in two terminals,
with the GUI, and `sitl_only` opens the MAVProxy console so you can fly by hand (`mode
QHOVER`, `arm throttle`, `rc 3 1600`).

---

## 9. Images: `sim_model.scad` and `render_sim_images.sh`

`sim_model.scad` imports the same v2 meshes Gazebo uses, one colour per group, so the
pictures match the simulated aircraft. `render_sim_images.sh` renders five views with
OpenSCAD: isometric (perspective), top, side, front (orthographic) and rear
(perspective), at 2400×1500 px. The camera positions are in the script.

---

## 10. Results

All numbers below come from the files in `results/`. The two runs were made on the
cleaned repo with `run_headless_test.sh`.

- **Hover** (`results/clean_repo_rerun/`, run with the defaults): PASS, max altitude 3.85 m,
  max tilt 10.6°. The landing was still in progress when the 15 s window ended (last
  altitude 0.97 m, last tilt 8.6°). The deck run (`results/deck_run/`) gave the same
  verdict: max altitude 4.28 m, max tilt 10.9°, last altitude 1.63 m.
- **Transition, forward flight and landing** (run with `--transition --climb-time 30 --climb-throttle 1800`):
  - Clean-repo re-run: forward flight PASS (max ground speed 20.1 m/s, min altitude 16.6 m,
    max tilt 7.0°), landed (final altitude −0.02 m).
  - Deck run: forward flight PASS (20.8 m/s, 15.6 m, 7.9°), landed (−0.32 m).

  Both runs agree. The first re-run attempt used the default 10 s climb, which only
  reached about 2 m, so it did not land. The 30 s climb is what the deck used.

`results/summary.json` holds the per-phase summary. It was computed by an analysis
script that is not in this repo, so **trust the CSV logs** over the summary.

---

## 11. What is estimated, and what to check before you trust it

| Item | Status |
|---|---|
| Printed airframe mass (1.0 kg) | **Assumed, not weighed.** It drives the total mass and CG. |
| Total mass and CG | Follow from the assumed printed mass, and the battery move that places the CG at the manual's 60 mm. |
| Propeller thrust (~17 N static, per the code comment) | **Not checked against the datasheet.** |
| Aerodynamic coefficients | From the manual (airfoil E205). **Not checked against wind-tunnel data or flight.** |
| Moving-part masses in the SDF | Guessed (30–60 g each). The total is still right. |
| Hover PID gains | Set for the 2.45 kg estimate. Not tuned on a real aircraft. |
| Hover landing | The 15 s landing window is too short in hover-only mode. Use the transition run for landing. |
| Second airframe | Spawned, never flown. |

---

## 12. What was removed in the cleanup

Everything that was not part of the V2 simulation was removed from the working tree:
the original CAD folders, firmware and HIL/CAN/swarm code, the autotune CI, v1 meshes,
the duplicate model folder, missions, terrain data, hardware and drone-2 parameter
files, and the drone-2 launcher. All of it is still in git history. The last commit
before the cleanup is `8d0a300`:

```bash
git show 8d0a300:<path>        # view a removed file
git checkout 8d0a300 -- <path> # restore it
```
