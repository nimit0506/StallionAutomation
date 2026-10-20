#!/usr/bin/env python3
# ============================================================================
# gazebo_render_views.py  —  "Take photos of the aircraft inside Gazebo"
# ============================================================================
#
# WHAT THIS FILE DOES (plain language)
#   Gazebo is a 3D physics simulator. It has built-in "cameras" (sensors) that
#   can look at the scene and produce images. This script:
#     1. Builds a small temporary world: the same ground and sun as the flight
#        world, one aircraft in the middle, and five cameras around it.
#     2. Starts Gazebo in the background (no window needed).
#     3. Asks each camera for one picture.
#     4. Saves the pictures as PNG files.
#   So the images are real Gazebo renders, not drawings made by another program.
#
# KEY WORDS
#   World       : a Gazebo file (.sdf) describing the ground, lights and models.
#   Model       : one object in the world, such as the aircraft.
#   Sensor      : a device attached to a model (here a camera).
#   Topic       : a named channel Gazebo publishes data on. Each camera publishes
#                 its pictures on a topic called cam_<view>/image.
#   Headless    : running without a window (the "-s" flag = server only).
#   xvfb-run    : runs a program on a virtual screen, so OpenGL rendering works
#                 on a machine with no monitor.
#   Pose        : position (x, y, z in metres) and orientation (roll, pitch, yaw
#                 in radians) of an object.
#
# HOW TO RUN IT
#   xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol results/images/gazebo/pod
#   xvfb-run -a python3 scripts/gazebo_render_views.py stallion_vtol_nopod results/images/gazebo/nopod
#
# NEEDS: Gazebo (gz), Python packages numpy and Pillow.
# ============================================================================

import argparse         # reads the command-line arguments
import codecs           # decodes the escaped binary text that gz topic prints
import math             # trigonometry (atan2, asin) for camera orientation
import os               # file paths
import re               # regular expressions: searches the world file and the topic text
import shutil           # deletes the temporary folder
import subprocess       # runs the "gz" command and starts Gazebo
import sys              # exit code
import tempfile         # creates a temporary folder for the world file and log
import time             # waits for Gazebo to start

import numpy as np      # vector maths for the camera positions
from PIL import Image   # turns pixel data into a PNG file

# Locate the repository from this script's position (scripts/ is one level below the repo)
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
# The world used by the flight tests. We copy its ground, lights and scene settings.
BASE_WORLD = os.path.join(REPO, "gazebo", "worlds", "stallion_runway.sdf")

# The point every camera looks at: the middle of the aircraft, 10 cm above the origin
TARGET = np.array([0.0, 0.0, 0.10])
DIST = 2.4                            # distance from the cameras to the target, in metres
W, H = 1600, 1000                     # picture size in pixels (width x height)

# Each view: the direction FROM the target TO the camera. Longer x/y/z changes
# the angle; the vector is normalised (made length 1) and then multiplied by DIST.
VIEWS = {
    "iso": (1.2, -1.1, 0.7),          # three-quarter view, from the front-left and above
    "top": (0.001, 0.0, 2.0),         # straight down (a tiny x offset avoids a zero-length axis)
    "side": (0.0, -1.0, 0.05),        # from the left side, level
    "front": (1.0, 0.0, 0.05),        # from the nose, level
    "rear": (-1.5, 0.9, 0.5),         # from behind and to the right, a little above
}


def pose_for(name):
    """Work out the position and orientation a camera needs to look at TARGET.

    Returns:
      - a text string "x y z roll pitch yaw" in the format Gazebo expects
      - the camera position as a numpy array
    """
    d = np.array(VIEWS[name], float)            # direction from target to camera
    d /= np.linalg.norm(d)                      # make it length 1
    pos = TARGET + DIST * d                     # camera position = target + distance x direction
    fwd = TARGET - pos                          # the direction the camera should look
    fwd /= np.linalg.norm(fwd)                  # length 1
    # 'left' = a direction at right angles to 'fwd' and to the vertical.
    # np.cross gives the vector at right angles to two others.
    left = np.cross([0, 0, 1.0], fwd)
    if np.linalg.norm(left) < 1e-9:             # looking straight down: 'left' is undefined,
        left = np.array([0, 1.0, 0])            # so pick any sideways direction
    left /= np.linalg.norm(left)
    up = np.cross(fwd, left)                    # the camera's own "up" direction
    # Rotation matrix: its three columns are the camera's forward, left and up axes
    m = np.column_stack([fwd, left, up])
    # Convert the rotation matrix to roll, pitch and yaw (the Gazebo format)
    roll = math.atan2(m[2, 1], m[2, 2])
    pitch = math.asin(-m[2, 0])
    yaw = math.atan2(m[1, 0], m[0, 0])
    return f"{pos[0]:.4f} {pos[1]:.4f} {pos[2]:.4f} {roll:.6f} {pitch:.6f} {yaw:.6f}", pos


def camera_model(name):
    """Return the SDF text for one camera: a fixed (static) model with a camera sensor."""
    pose, _ = pose_for(name)
    return f"""    <model name="cam_{name}">
      <static>true</static>                       <!-- the camera does not move or fall -->
      <pose>{pose}</pose>
      <link name="link">
        <sensor name="camera" type="camera">
          <always_on>1</always_on>                <!-- always produce pictures -->
          <update_rate>1</update_rate>            <!-- one picture per second -->
          <visualize>false</visualize>            <!-- do not draw the camera itself in the scene -->
          <topic>cam_{name}/image</topic>         <!-- where the pictures are published -->
          <camera>
            <horizontal_fov>0.6</horizontal_fov>  <!-- field of view, radians (about 34 degrees wide) -->
            <image><width>{W}</width><height>{H}</height></image>
            <clip><near>0.05</near><far>100</far></clip>   <!-- nearest and farthest visible distance -->
          </camera>
        </sensor>
      </link>
    </model>
"""


def build_world(model_name):
    """Make the temporary world file: the flight world's ground and lights, one aircraft, five cameras."""
    src = open(BASE_WORLD).read()
    # Remove the two runway airframes that the flight world spawns.
    # The regular expression matches each "Spawn Stallion" comment and its <include> block.
    src = re.sub(r"\s*<!-- Spawn Stallion.*?</include>\n", "\n", src, flags=re.S)
    # Render look only: grey ground and a light grey background instead of the flight world's green and blue.
    # The flight world itself is NOT changed; these edits exist only in the temporary copy.
    src = src.replace("<ambient>0.3 0.5 0.3 1</ambient>", "<ambient>0.55 0.55 0.55 1</ambient>")
    src = src.replace("<diffuse>0.3 0.5 0.3 1</diffuse>", "<diffuse>0.55 0.55 0.55 1</diffuse>")
    src = src.replace("<background>0.6 0.7 0.9 1.0</background>", "<background>0.82 0.82 0.84 1.0</background>")
    # Place the aircraft at the origin, 8 cm above the ground (its wheels/belly sit on the ground)
    airframe = f"""    <include>
      <uri>model://{model_name}</uri>
      <pose>0 0 0.08 0 0 0</pose>
    </include>
"""
    # Add the five cameras, then close the world tag
    cams = "".join(camera_model(v) for v in VIEWS)
    return src.replace("</world>", airframe + cams + "  </world>")


def capture(topic, out_png):
    """Take one picture from a camera topic and save it as a PNG file.

    Gazebo prints the picture as text (the 'gz topic -e' command). The pixel bytes
    are written with escape codes (for example \\377), so we decode them back
    into raw bytes, check their size, and turn them into an image.
    """
    # Ask Gazebo for ONE message from this topic and capture everything it prints
    txt = subprocess.run(["gz", "topic", "-e", "-t", topic, "-n", "1"],
                         capture_output=True, timeout=120).stdout
    s = txt.decode("latin-1")                     # convert bytes to text (latin-1 keeps every byte)
    # Read the image width and height from the message text
    w = int(re.search(r"width:\s*(\d+)", s).group(1))
    h = int(re.search(r"height:\s*(\d+)", s).group(1))
    # Read the pixel data between the quotes after "data:"
    data = re.search(r'data:\s*"(.*)"', s, re.S).group(1)
    # Turn the escape codes back into the real bytes
    raw = codecs.escape_decode(data.encode("latin-1"))[0]
    # Each pixel is 3 bytes (red, green, blue), so the size must be width x height x 3
    assert len(raw) == w * h * 3, (len(raw), w, h)
    # Reshape the bytes into a height x width x 3 array and save it as PNG
    Image.fromarray(np.frombuffer(raw, np.uint8).reshape(h, w, 3)).save(out_png)
    return w, h


def main():
    """Start Gazebo, take the five pictures, shut Gazebo down, clean up."""
    ap = argparse.ArgumentParser(description="Render the Stallion model with Gazebo's own cameras.")
    ap.add_argument("model", help="stallion_vtol (with pod) or stallion_vtol_nopod")
    ap.add_argument("out", help="folder where the PNG files are saved")
    ap.add_argument("--wait", type=float, default=25, help="seconds to wait for Gazebo to start")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="stallion_render_")         # a private temporary folder
    world = os.path.join(tmp, "render.sdf")                    # the temporary world file
    open(world, "w").write(build_world(args.model))

    # Tell Gazebo where to find the aircraft model files (the repo's gazebo/models folder)
    env = dict(os.environ)
    env["GZ_SIM_RESOURCE_PATH"] = f"{REPO}/gazebo/models:{REPO}/gazebo/worlds:" + env.get("GZ_SIM_RESOURCE_PATH", "")
    log = open(os.path.join(tmp, "gz.log"), "w")               # Gazebo's messages go here
    # Start Gazebo: -s = server only (no window), -r = start running straight away
    gz = subprocess.Popen(["gz", "sim", "-s", "-r", world], env=env, stdout=log, stderr=log)
    try:
        time.sleep(args.wait)                                  # give the renderer time to start
        for view in VIEWS:
            topic = f"cam_{view}/image"
            out_png = os.path.join(args.out, f"{view}.png")
            w, h = capture(topic, out_png)
            print(f"wrote {out_png} ({w}x{h})")
    finally:
        # Always shut Gazebo down and remove the temporary folder, even if something failed
        gz.kill()
        subprocess.run(["pkill", "-9", "-f", "[g]z sim"], capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


# Run main() only when started directly
if __name__ == "__main__":
    sys.exit(main())
