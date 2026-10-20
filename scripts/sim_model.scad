// ============================================================================
// sim_model.scad  —  the aircraft as a 3D scene, WITH the vial pod
// ============================================================================
//
// WHAT THIS FILE IS (plain language)
//   OpenSCAD scene file. Each line says: "load this 3D mesh file and paint it
//   this colour". OpenSCAD then draws the whole aircraft.
//
// The meshes are the same visual meshes that Gazebo loads, from
// gazebo/models/stallion_vtol/meshes/v2, so the picture matches the simulated aircraft.
//
// SYNTAX
//   color([r, g, b]) import("file.stl");
//     color : sets the colour; r, g, b are 0..1 (red, green, blue).
//     import: loads a mesh file (STL = a list of triangles).
//   Paths are relative to THIS file, which is why render_sim_images.sh runs from scripts/.
//
// GROUPS AND COLOURS
//   airframe (orange)      main body, booms and mounts
//   wings (white)          main wings and V-tail
//   carbon (black)         carbon tubes
//   pod (green)            the vial pod (this file only; sim_model_nopod.scad leaves it out)
//   electronics (red)      flight controller, receiver, battery, servos
//   tilt and motor links   dark grey / black: motors and their tilt mounts
//   control surfaces (blue) ailerons and V-tail
// ============================================================================

// main body
color([1,0.45,0.1])  import("../gazebo/models/stallion_vtol/meshes/v2/airframe.stl");
// wings and V-tail
color([0.95,0.95,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/wings.stl");
// carbon tubes
color([0.12,0.12,0.12]) import("../gazebo/models/stallion_vtol/meshes/v2/carbon.stl");
// vial pod
color([0.3,0.75,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/pod.stl");
// electronics
color([0.85,0.15,0.15]) import("../gazebo/models/stallion_vtol/meshes/v2/electronics.stl");
// front-left tilt mount
color([0.35,0.35,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/fl_tilt_link.stl");
// front-left motor
color([0.1,0.1,0.1]) import("../gazebo/models/stallion_vtol/meshes/v2/fl_motor_link.stl");
// front-right tilt mount
color([0.35,0.35,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/fr_tilt_link.stl");
// front-right motor
color([0.1,0.1,0.1]) import("../gazebo/models/stallion_vtol/meshes/v2/fr_motor_link.stl");
// rear yaw mount
color([0.35,0.35,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/rear_yaw_link.stl");
// rear motor
color([0.1,0.1,0.1]) import("../gazebo/models/stallion_vtol/meshes/v2/rear_motor_link.stl");
// left aileron
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/aileron_left.stl");
// right aileron
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/aileron_right.stl");
// left V-tail surface
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/ruddervator_left.stl");
// right V-tail surface
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/ruddervator_right.stl");
