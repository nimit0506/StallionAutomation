#!/usr/bin/env python3
"""
gazebo_render_views.py — render the Stallion model inside Gazebo, with Gazebo's own cameras.

    xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol results/images/gazebo/pod
    xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol_nopod results/images/gazebo/nopod

How it works:
  1. Writes a temporary world: the stallion_runway ground, sun and scene, with one
     airframe at the origin and five camera sensors around it (iso, top, side, front, rear).
  2. Starts Gazebo headless (gz sim -s) on that world.
  3. Reads one frame from each camera topic with `gz topic -e -n 1`.
  4. Decodes the raw RGB pixels and saves PNG files.

The renders are Gazebo's own rendering (the Ogre engine that the Gazebo GUI uses),
not a separate tool's imitation.
"""
import argparse
import codecs
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
BASE_WORLD = os.path.join(REPO, "gazebo", "worlds", "stallion_runway.sdf")
TARGET = np.array([0.0, 0.0, 0.10])   # the cameras look at the middle of the airframe
DIST = 2.4                            # m from the target
W, H = 1600, 1000

# Camera name -> direction from the target to the camera (normalised, then scaled by DIST)
VIEWS = {
    "iso": (1.2, -1.1, 0.7),
    "top": (0.001, 0.0, 2.0),
    "side": (0.0, -1.0, 0.05),
    "front": (1.0, 0.0, 0.05),
    "rear": (-1.5, 0.9, 0.5),
}


def pose_for(name):
    """SDF pose string (x y z roll pitch yaw) of a camera that looks at TARGET."""
    d = np.array(VIEWS[name], float)
    d /= np.linalg.norm(d)
    pos = TARGET + DIST * d
    fwd = TARGET - pos
    fwd /= np.linalg.norm(fwd)
    left = np.cross([0, 0, 1.0], fwd)
    if np.linalg.norm(left) < 1e-9:                 # looking straight down: pick any left axis
        left = np.array([0, 1.0, 0])
    left /= np.linalg.norm(left)
    up = np.cross(fwd, left)
    # Rotation matrix whose columns are the camera's x (forward), y (left), z (up) axes
    m = np.column_stack([fwd, left, up])
    roll = math.atan2(m[2, 1], m[2, 2])
    pitch = math.asin(-m[2, 0])
    yaw = math.atan2(m[1, 0], m[0, 0])
    return f"{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f} {roll:.6f} {pitch:.6f} {yaw:.6f}", pos


def camera_model(name):
    pose, _ = pose_for(name)
    return f"""    <model name="cam_{name}">
      <static>true</static>
      <pose>{pose}</pose>
      <link name="link">
        <sensor name="camera" type="camera">
          <always_on>1</always_on>
          <update_rate>1</update_rate>
          <visualize>false</visualize>
          <topic>cam_{name}/image</topic>
          <camera>
            <horizontal_fov>0.6</horizontal_fov>
            <image><width>{W}</width><height>{H}</height></image>
            <clip><near>0.05</near><far>100</far></clip>
          </camera>
        </sensor>
      </link>
    </model>
"""


def build_world(model_name):
    """Base world with the airframe at the origin and the five cameras added."""
    src = open(BASE_WORLD).read()
    # Drop the two runway airframes; this world shows one airframe at the origin
    src = re.sub(r"\s*<!-- Spawn Stallion.*?</include>\n", "\n", src, flags=re.S)
    # Render look only: grey ground and a light grey background instead of the flight world's green and blue
    src = src.replace("<ambient>0.3 0.5 0.3 1</ambient>", "<ambient>0.55 0.55 0.55 1</ambient>")
    src = src.replace("<diffuse>0.3 0.5 0.3 1</diffuse>", "<diffuse>0.55 0.55 0.55 1</diffuse>")
    src = src.replace("<background>0.6 0.7 0.9 1.0</background>", "<background>0.82 0.82 0.84 1.0</background>")
    airframe = f"""    <include>
      <uri>model://{model_name}</uri>
      <pose>0 0 0.08 0 0 0</pose>
    </include>
"""
    cams = "".join(camera_model(v) for v in VIEWS)
    return src.replace("</world>", airframe + cams + "  </world>")


def capture(topic, out_png):
    """Read one frame from a Gazebo camera topic and save it as PNG."""
    txt = subprocess.run(["gz", "topic", "-e", "-t", topic, "-n", "1"],
                         capture_output=True, timeout=120).stdout
    s = txt.decode("latin-1")
    w = int(re.search(r"width:\s*(\d+)", s).group(1))
    h = int(re.search(r"height:\s*(\d+)", s).group(1))
    data = re.search(r'data:\s*"(.*)"', s, re.S).group(1)
    raw = codecs.escape_decode(data.encode("latin-1"))[0]
    assert len(raw) == w * h * 3, (len(raw), w, h)
    Image.fromarray(np.frombuffer(raw, np.uint8).reshape(h, w, 3)).save(out_png)
    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="stallion_vtol (with pod) or stallion_vtol_nopod")
    ap.add_argument("out", help="folder for the PNG files")
    ap.add_argument("--wait", type=float, default=25, help="seconds for the renderer to start")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="stallion_render_")
    world = os.path.join(tmp, "render.sdf")
    open(world, "w").write(build_world(args.model))

    env = dict(os.environ)
    env["GZ_SIM_RESOURCE_PATH"] = f"{REPO}/gazebo/models:{REPO}/gazebo/worlds:" + env.get("GZ_SIM_RESOURCE_PATH", "")
    log = open(os.path.join(tmp, "gz.log"), "w")
    gz = subprocess.Popen(["gz", "sim", "-s", "-r", world], env=env, stdout=log, stderr=log)
    try:
        time.sleep(args.wait)
        for view in VIEWS:
            topic = f"cam_{view}/image"
            out_png = os.path.join(args.out, f"{view}.png")
            w, h = capture(topic, out_png)
            print(f"wrote {out_png} ({w}x{h})")
    finally:
        gz.kill()
        subprocess.run(["pkill", "-9", "-f", "[g]z sim"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
