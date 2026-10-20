# Stallion V2 VTOL — Gazebo + ArduPlane SITL

## New to this project? Read in this order

Every script starts with a plain-language header that explains what it does,
the key words it uses, and how to run it. Read them in this order:

1. `docs/CODE_GUIDE.md`: the whole project in one document.
2. `scripts/mesh_check.py`: what "a valid 3D solid" means.
3. `scripts/mesh_repair.py`: how broken parts are fixed.
4. `scripts/mass_properties.py`: mass, balance point (CG) and rotation inertia.
5. `scripts/build_stallion_v2_model.py`: turns the CAD into the Gazebo model (the biggest file).
6. `scripts/run_headless_test.sh` and `scripts/sitl_hover_check.py`: running and grading a flight.
7. `scripts/flight_metrics.py`: turning the flight logs into numbers and charts.
8. `scripts/gazebo_render_views.py` and `scripts/build_variant_deck.js`: pictures and slides.


Simulation of the Stallion V2 quad-tilt tricopter VTOL (with vial pod). The airframe
comes from the repaired CAD export in `inputs/`. Gazebo Harmonic runs the physics, and
ArduPlane SITL (QuadPlane, tilt-rotor settings) flies it through the JSON bridge.

- **How it works, file by file:** [`docs/CODE_GUIDE.md`](docs/CODE_GUIDE.md)
- **Results (flight logs, images, summary):** [`results/`](results/README.md)
- **Slides:** [`docs/Stallion_V2_Sim_Results.pptx`](docs/Stallion_V2_Sim_Results.pptx)

## Layout

```
inputs/                              raw GLB from CAD, and the repaired GLB the model is built from
scripts/
  mesh_check.py                      topology check per CAD part (watertight, manifold, sheets)
  mesh_repair.py                     repairs bad parts (basic fixes, then shrink-wrap fallback)
  mass_properties.py                 mass, centre of gravity and inertia from the GLB
  build_stallion_v2_model.py         writes the Gazebo model (meshes + model.sdf) from the GLB
  sim_model.scad                     OpenSCAD scene of the airframe for the sim images
  render_sim_images.sh               renders the five views into results/images/
  sitl_hover_check.py                automated flight test (hover, optional transition, landing)
  run_headless_test.sh               starts Gazebo + SITL + MAVProxy and runs the flight test
  launch_gazebo_only.sh              manual: Gazebo with GUI (terminal 1)
  launch_sitl_only.sh                manual: ArduPlane SITL with MAVProxy (terminal 2)
gazebo/
  worlds/stallion_runway.sdf         runway world; spawns both airframes
  models/stallion_vtol/              airframe 1 — flown by SITL on UDP 9002
  models/stallion_vtol_2/            airframe 2 — spawned, no autopilot attached
  models/stallion_vtol_nopod/        airframe without the vial pod (variant)
  worlds/stallion_runway_nopod.sdf   world with the no-pod airframe
params/stallion_vtol_sitl.parm       ArduPlane QuadPlane / tilt / PID parameters for the sim
docs/                                slides
results/                             flight logs, summary, mesh checks, sim images
```

## Setup

You need: Python 3 with `numpy trimesh manifold3d scipy scikit-image pymavlink`,
Gazebo Harmonic (`gz`), OpenSCAD (for the images), and MAVProxy.
You also need two builds, at the paths below (or set the env vars):

| Component | Default path | Env var |
|---|---|---|
| ArduPilot source, built for SITL (`build/sitl/bin/arduplane`) | `~/ardupilot` | `ARDUPILOT_DIR` |
| ardupilot_gazebo, built (`build/libArduPilotPlugin.so`) | `~/ardupilot_gazebo` | `ARDUPILOT_GZ_DIR` |

```bash
pip install numpy trimesh manifold3d scipy scikit-image pymavlink
```

## Run it

```bash
# 1. Check the GLB and repair it if needed (writes a new GLB)
python3 scripts/mesh_check.py inputs/stallion_v2_pod_repaired.glb
python3 scripts/mesh_repair.py inputs/stallion_v2_equipped_with_pod.glb /tmp/repaired.glb

# 2. Mass / CG / inertia
python3 scripts/mass_properties.py inputs/stallion_v2_pod_repaired.glb --battery-shift 0.057

# 3. Build the Gazebo model from the repaired GLB (writes gazebo/models/*)
python3 scripts/build_stallion_v2_model.py inputs/stallion_v2_pod_repaired.glb

# 4. Flight test, no GUI (hover only, or add --transition for forward flight + landing)
scripts/run_headless_test.sh --csv results/clean_repo_rerun/hover_log.csv
scripts/run_headless_test.sh --transition --climb-time 30 --climb-throttle 1800 --csv results/clean_repo_rerun/transition_log.csv

# 5. Without-pod variant: model, world, flight tests
scripts/build_stallion_v2_model.py inputs/stallion_v2_pod_repaired.glb --variant nopod
WORLD=gazebo/worlds/stallion_runway_nopod.sdf scripts/run_headless_test.sh --csv results/variants/nopod/hover_log.csv

# 6. Flight-dynamics metrics and charts for both variants (results/variants/{pod,nopod})
python3 scripts/flight_metrics.py results/variants --out results/metrics

# 7. Slides (needs pptxgenjs: npm install pptxgenjs, then node scripts/build_variant_deck.js)
node scripts/build_variant_deck.js

# 8. Gazebo pictures of both airframes (grey background, five views each)
xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol results/images/gazebo/pod
xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol_nopod results/images/gazebo/nopod

# 9. OpenSCAD pictures (simpler, not from Gazebo)
xvfb-run -a scripts/render_sim_images.sh      # or plain: scripts/render_sim_images.sh
```

For a GUI session instead, run `scripts/launch_gazebo_only.sh` in one terminal and
`scripts/launch_sitl_only.sh` in a second one, then fly from MAVProxy.

Step 3 regenerates the model. The committed model is reproduced byte for byte from
`inputs/stallion_v2_pod_repaired.glb`, so a clean diff after step 3 means the build is stable.

## History

This cleanup removed material that was not used by the V2 simulation: the original CAD
folders, firmware and HIL/CAN/swarm code, the v1 meshes, and a duplicate of the model.
Everything removed is still in git history, before the cleanup commit (`8d0a300`).
