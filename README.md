# Stallion V2 — with vs without the box (flight simulation)

Flight simulation of the Stallion V2 tilt-rotor VTOL, flown with and without the payload
box (the vial pod under the fuselage). Gazebo Harmonic computes the physics and ArduPlane
SITL (the real autopilot software) flies it. Mass and drag come from the CFD study
(Stallion_box_vs_nobox_CFD, 0.8 mm walls).

**Slides:** [`docs/Stallion_V2_Box_vs_NoBox_Flight_Sim.pptx`](docs/Stallion_V2_Box_vs_NoBox_Flight_Sim.pptx)

## Results in short

| | With box | Without box |
|---|---|---|
| Mass (from CFD) | 2268 g | 2228 g |
| Forward flight and landing | pass | pass |
| Cruise airspeed | 20.2 m/s | 20.7 m/s |
| Hover motor power | 1666 PWM | 1661 PWM |

The box hardly changes how the aircraft flies. Its drag makes cruise about 0.5 m/s slower
at the same motor power. One flight per version. The numbers are in
`results/box_vs_nobox/summary.json`.

## What is in the repo

```
inputs/        raw CAD export (GLB) and the repaired version the model is built from
scripts/       all code; every file starts with a plain-language explanation
gazebo/        the two aircraft models (with box, without box) and their worlds
params/        ArduPlane autopilot parameters for the simulation
results/       flight logs, summary, chart, Gazebo renders, mesh checks
docs/          the slides
```

Read the scripts in this order: `mesh_check.py`, `mesh_repair.py`, `mass_properties.py`,
`build_stallion_v2_model.py`, `run_headless_test.sh`, `sitl_hover_check.py`,
`box_compare.py`, `gazebo_render_views.py`, `build_box_deck.js`.

## Setup

- Python 3 with `numpy trimesh manifold3d scipy scikit-image pymavlink matplotlib pillow`
- Gazebo Harmonic (`gz`), MAVProxy (`mavproxy.py`)
- ArduPilot built for SITL (`ARDUPILOT_DIR`, default `~/ardupilot`)
- ardupilot_gazebo plugin built (`ARDUPILOT_GZ_DIR`, default `~/ardupilot_gazebo`)
- For the slides: Node.js with `pptxgenjs` (`npm install pptxgenjs`)

## Run everything

```bash
# 1. Build both aircraft models from the repaired CAD (mass and drag from the CFD study)
python3 scripts/build_stallion_v2_model.py inputs/stallion_v2_pod_repaired.glb
python3 scripts/build_stallion_v2_model.py inputs/stallion_v2_pod_repaired.glb --variant nopod

# 2. Fly the same test with each (about 5 minutes each, no window)
ARGS="--transition --climb-time 30 --climb-throttle 1800"
scripts/run_headless_test.sh $ARGS --csv results/box_vs_nobox/box/transition_log.csv > results/box_vs_nobox/box/console.txt
WORLD=gazebo/worlds/stallion_runway_nopod.sdf scripts/run_headless_test.sh $ARGS \
    --csv results/box_vs_nobox/nobox/transition_log.csv > results/box_vs_nobox/nobox/console.txt

# 3. Summary numbers and chart
python3 scripts/box_compare.py results/box_vs_nobox

# 4. Gazebo renders, then the slides
xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol results/images/gazebo/pod
xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol_nopod results/images/gazebo/nopod
NODE_PATH=/path/to/node_modules node scripts/build_box_deck.js
```

To watch the aircraft in the Gazebo window instead, run `scripts/launch_gazebo_only.sh` in
one terminal and `scripts/launch_sitl_only.sh` in a second.
