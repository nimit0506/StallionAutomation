// Stallion V2 (with vial pod) for the sim-image renders.
// Uses the same visual meshes Gazebo loads (gazebo/models/stallion_vtol/meshes/v2),
// coloured by group. Rendered by scripts/render_sim_images.sh.
color([1,0.45,0.1])  import("../gazebo/models/stallion_vtol/meshes/v2/airframe.stl");
color([0.95,0.95,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/wings.stl");
color([0.12,0.12,0.12]) import("../gazebo/models/stallion_vtol/meshes/v2/carbon.stl");
color([0.3,0.75,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/pod.stl");
color([0.85,0.15,0.15]) import("../gazebo/models/stallion_vtol/meshes/v2/electronics.stl");
color([0.35,0.35,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/fl_tilt_link.stl");
color([0.1,0.1,0.1]) import("../gazebo/models/stallion_vtol/meshes/v2/fl_motor_link.stl");
color([0.35,0.35,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/fr_tilt_link.stl");
color([0.1,0.1,0.1]) import("../gazebo/models/stallion_vtol/meshes/v2/fr_motor_link.stl");
color([0.35,0.35,0.35]) import("../gazebo/models/stallion_vtol/meshes/v2/rear_yaw_link.stl");
color([0.1,0.1,0.1]) import("../gazebo/models/stallion_vtol/meshes/v2/rear_motor_link.stl");
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/aileron_left.stl");
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/aileron_right.stl");
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/ruddervator_left.stl");
color([0.25,0.55,0.95]) import("../gazebo/models/stallion_vtol/meshes/v2/ruddervator_right.stl");
