// ============================================================================
// build_variant_deck.js — writes the PowerPoint slides comparing the aircraft
//                         with and without the vial pod.
// ============================================================================
//
// WHAT THIS FILE DOES (plain language)
//   It writes a .pptx file (a PowerPoint presentation). It does NOT draw the
//   charts or run the simulation: it only reads the results that the other
//   scripts already produced, and places them on slides as text, tables and
//   pictures. If you re-run the flights, run flight_metrics.py first, then this
//   file, and the slides update.
//
// WHERE THE NUMBERS COME FROM
//   results/metrics/metrics.json   per-phase flight numbers (from flight_metrics.py)
//   results/mesh/mass.json         mass and inertia, with the pod   (from mass_properties.py)
//   results/mesh/mass_nopod.json   mass and inertia, without the pod
//   results/images/gazebo/...      renders from Gazebo's cameras  (gazebo_render_views.py)
//   results/metrics/charts/...     time-series charts              (flight_metrics.py)
//
// HOW TO RUN IT
//   1. Install the library once:   npm install pptxgenjs   (in any folder)
//   2. Run, pointing NODE_PATH at that folder's node_modules:
//        NODE_PATH=/path/to/node_modules node scripts/build_variant_deck.js
//   Output: docs/Stallion_V2_Pod_vs_NoPod_Flight_Dynamics.pptx
//
// READING THE LAYOUT CODE
//   pptxgenjs positions everything in INCHES. A 16:9 slide is 10 x 5.625 inches.
//   x = distance from the left edge, y = distance from the top edge.
//   "w" and "h" are the width and height of the box.
// ============================================================================

const path = require("path");                // builds file paths that work on any operating system
const fs = require("fs");                    // reads the JSON result files from disk
const pptxgen = require("pptxgenjs");        // the library that writes the .pptx file

// ROOT = the repository folder (one level up from this scripts/ folder)
const ROOT = path.join(__dirname, "..");
// R("a/b.txt") returns the full path to a file inside the repository
const R = (p) => path.join(ROOT, p);
// JSON.parse turns the text of a .json file into a JavaScript object we can read
const M = JSON.parse(fs.readFileSync(R("results/metrics/metrics.json")));     // flight numbers
const MASS = JSON.parse(fs.readFileSync(R("results/mesh/mass.json")));        // mass, with pod
const MASS_NP = JSON.parse(fs.readFileSync(R("results/mesh/mass_nopod.json")));  // mass, no pod
// Shortcuts: P = the with-pod numbers, N = the without-pod numbers.
// Each has the structure P.hover.hold.alt_mean_m, P.transition.forward.gs_mean_steady_ms, etc.
const P = M.pod;     // with pod
const N = M.nopod;   // without pod

// Colours, written as hex codes (no # sign). Blue = with pod, amber = without pod.
const C = {
  navy: "1B2A41", pod: "1F5F99", nopod: "D9822B", ink: "1E1E1E", muted: "5F6B7A",
  line: "D5DBE3", panel: "F3F5F8", white: "FFFFFF",
};
const FONT = "Calibri";                             // a font that every PowerPoint has
// Path to the Gazebo render of one view (view = iso, top, side, front or rear)
const IMG = (v, view) => R(`results/images/gazebo/${v}/${view}.png`);
// Path to a time-series chart PNG
const CH = (name) => R(`results/metrics/charts/${name}.png`);

const pres = new pptxgen();                          // a new, empty presentation
pres.layout = "LAYOUT_16x9";          // 10 x 5.625 in (the standard widescreen slide)
pres.title = "Stallion V2: with and without the vial pod";   // stored in the file's properties

// Helpers ------------------------------------------------------------------------
// f(value, decimals) formats a number with fixed decimals; prints "n/a" if missing
const f = (v, d = 2) => (v === null || v === undefined ? "n/a" : Number(v).toFixed(d));
let pageNo = 0;                                      // counts slides for the footer numbers

// Adds a bold title at the top of a slide, and an optional grey subtitle under it
function title(slide, text, sub) {
  slide.addText(text, { x: 0.5, y: 0.3, w: 9, h: 0.6, fontFace: FONT, fontSize: 26, bold: true, color: C.navy, margin: 0, isTextBox: true });
  if (sub) slide.addText(sub, { x: 0.5, y: 0.9, w: 9, h: 0.35, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, isTextBox: true });
}

// Adds the small grey line at the bottom of a slide, with the slide number
function footer(slide) {
  pageNo += 1;                                       // each slide that calls footer() gets the next number
  slide.addText(`Gazebo Harmonic + ArduPlane SITL, 10 Hz flight logs   |   ${pageNo}`, {
    x: 0.5, y: 5.25, w: 9, h: 0.25, fontFace: FONT, fontSize: 10, color: C.muted, margin: 0, isTextBox: true,
  });
}

// Adds a bulleted list. items = array of strings; box = {x, y, w, h} in inches; size = font size.
// The last item must not have a line break after it (breakLine), which is why we check i < length-1.
function bullets(slide, items, box, size = 14) {
  slide.addText(items.map((t, i) => ({
    text: t,
    options: { bullet: true, breakLine: i < items.length - 1 },
  })), { ...box, fontFace: FONT, fontSize: size, color: C.ink, paraSpaceAfter: 6, valign: "top", margin: 0, isTextBox: true });
}

// Adds a table. header = array of column titles; rows = array of rows (each an array of strings).
// The first column is left-aligned, the others centred. Rows alternate white and light grey.
// opts: x, y, w (position and width in inches), colW (column widths), rowH (row height), fontSize.
function table(slide, header, rows, opts = {}) {
  const hdr = header.map((t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.navy }, align: "center" } }));
  const body = rows.map((r, i) => r.map((t, j) => ({
    text: String(t),
    options: { color: C.ink, fill: { color: i % 2 ? C.white : C.panel }, align: j === 0 ? "left" : "center" },
  })));
  slide.addTable([hdr, ...body], {
    x: opts.x ?? 0.5, y: opts.y ?? 1.35, w: opts.w ?? 9, colW: opts.colW,
    fontFace: FONT, fontSize: opts.fontSize ?? 13, rowH: opts.rowH ?? 0.33,
    border: { type: "solid", pt: 0.5, color: C.line },
  });
}

// Adds a "stat card": a grey box with one big number (value) and a short caption (label) below it.
function stat(slide, x, y, value, label, colour) {
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w: 2.1, h: 1.55, fill: { color: C.panel }, line: { color: C.panel } });
  slide.addText(value, { x: x + 0.15, y: y + 0.15, w: 1.8, h: 0.6, fontFace: FONT, fontSize: 28, bold: true, color: colour, margin: 0, isTextBox: true });
  slide.addText(label, { x: x + 0.15, y: y + 0.8, w: 1.8, h: 0.7, fontFace: FONT, fontSize: 12, color: C.ink, margin: 0, valign: "top", isTextBox: true });
}

// Numbers used in several slides. The mass files store kg, so multiply by 1000 for grams.
const massPod = MASS.mass_kg * 1000, massNp = MASS_NP.mass_kg * 1000;
// dMass = how many grams the pod weighs (about 150)
const dMass = massPod - massNp;
const landPeak = Math.max(P.transition.land.max_abs_roll_deg, P.transition.land.max_abs_pitch_deg,
  N.transition.land.max_abs_roll_deg, N.transition.land.max_abs_pitch_deg);

// ============================================================================
// SLIDES. Each block { ... } below builds one slide. Slide order = order below.
// ============================================================================

// 1. Title slide: dark background, no footer
{
  const s = pres.addSlide();
  s.background = { color: C.navy };
  s.addText("Stallion V2 flight dynamics", { x: 0.6, y: 1.5, w: 8.8, h: 0.9, fontFace: FONT, fontSize: 40, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText("With and without the vial pod", { x: 0.6, y: 2.4, w: 8.8, h: 0.6, fontFace: FONT, fontSize: 24, color: C.white, margin: 0, isTextBox: true });
  s.addText("Gazebo Harmonic + ArduPlane SITL: automated hover and transition flights", { x: 0.6, y: 3.2, w: 8.8, h: 0.4, fontFace: FONT, fontSize: 14, color: "C9D3E0", margin: 0, isTextBox: true });
}

// 2. Summary: four headline numbers and three key findings
{
  const s = pres.addSlide();
  title(s, `Without the pod: ${dMass.toFixed(0)} g lighter, and the flight changes`,
    "Both versions pass the hover and forward-flight tests and land after the transition");
  stat(s, 0.5, 1.45, `${dMass.toFixed(0)} g`, `Lighter without the pod (${massPod.toFixed(0)} g → ${massNp.toFixed(0)} g)`, C.navy);
  stat(s, 2.8, 1.45, `${f(N.hover.hold.alt_mean_m, 1)} m`, `Hover altitude without pod, same throttle (with pod: ${f(P.hover.hold.alt_mean_m, 1)} m)`, C.nopod);
  stat(s, 5.1, 1.45, `${f(N.transition.forward.time_to_12ms_s, 1)} s`, `To reach 12 m/s without pod (with pod: ${f(P.transition.forward.time_to_12ms_s, 1)} s)`, C.nopod);
  stat(s, 7.4, 1.45, `${landPeak.toFixed(0)}°`, "Largest roll or pitch during landing, either version", C.pod);
  bullets(s, [
    `Hover: both versions hold altitude and stay within ${Math.max(P.hover.hold.roll_rms_deg, N.hover.hold.roll_rms_deg, P.hover.hold.pitch_rms_deg, N.hover.hold.pitch_rms_deg).toFixed(1)}° of level (RMS). The lighter airframe climbs higher on the same throttle.`,
    `Forward flight: both reach about 20 m/s. Without the pod the altitude was still changing (${f(N.transition.forward.alt_std_steady_m, 1)} m spread against ${f(P.transition.forward.alt_std_steady_m, 1)} m with the pod).`,
    `Landing: both versions swing by 15–20° during the descent. The landing controller needs re-tuning. This is not caused by the pod.`,
  ], { x: 0.5, y: 3.2, w: 9, h: 1.9 }, 14);
  footer(s);
}

// 3. How the tests were flown -------------------------------------------------------
{
  const s = pres.addSlide();
  title(s, "How the flights were flown");
  bullets(s, [
    "Hover test: arm in QHOVER, climb 10 s at throttle PWM 1700, hold 10 s at 1500, then QLAND (land).",
    "Transition test: climb 30 s at PWM 1800, switch to FBWB (fixed-wing mode with altitude hold) for 30 s, return to QHOVER, then QLAND.",
    "Pass rules: hover passes if it reaches 3 m with roll and pitch within 25°. Forward flight passes if it reaches 12 m/s, stays above 2 m, and keeps tilt within 45°. The transition test passes landing if it ends below 0.5 m.",
    "Same world, same parameters and same throttle profile for both airframes. The only difference is the pod.",
    "Units: angles in degrees, altitude in metres, speeds in m/s. Servo and motor values are PWM (1000–2000).",
  ], { x: 0.5, y: 1.2, w: 9, h: 3.9 }, 15);
  footer(s);
}

// 4 and 5. Gazebo renders: one slide per airframe, five views each.
// Layout: three pictures in the top row, two centred in the bottom row.
function renderSlide(variant, label, colour) {
  const s = pres.addSlide();                         // a new slide
  title(s, `The airframe in Gazebo: ${label}`, "Rendered by Gazebo's own camera sensors (the same renderer the GUI uses)");
  const views = ["iso", "top", "side", "front", "rear"];
  const names = { iso: "Isometric", top: "Top", side: "Side", front: "Front", rear: "Rear" };
  const w = 2.72, h = 1.7;
  views.forEach((v, i) => {                          // place each picture in turn
    // row 0 = top (views 0-2), row 1 = bottom (views 3-4)
    const row = i < 3 ? 0 : 1;
    const col = i < 3 ? i : i - 3;
    const x = row === 0 ? 0.5 + col * (w + 0.15) : 0.5 + 0.5 * (w + 0.15) + col * (w + 0.15);
    const y = 1.3 + row * (h + 0.25);
    s.addImage({ path: IMG(variant, v), x, y, w, h });
    s.addText(names[v], { x, y: y + h + 0.02, w, h: 0.22, fontFace: FONT, fontSize: 11, color: colour, bold: true, margin: 0, isTextBox: true });
  });
  footer(s);
  return s;
}
renderSlide("pod", "with the vial pod", C.pod);
renderSlide("nopod", "without the vial pod", C.nopod);

// 6. Mass and inertia: a comparison table plus three plain-language bullets
{
  const s = pres.addSlide();
  title(s, `Mass and inertia: the pod is ${dMass.toFixed(0)} g, the CG hardly moves`,
    "CAD estimate. The printed airframe mass (1.0 kg) is an assumption, not a weighed value.");
  const dI = (i) => (MASS_NP.inertia_about_cg[i][i] - MASS.inertia_about_cg[i][i]).toFixed(4);
  table(s, ["Property", "With pod", "Without pod", "Change"], [
    ["All-up mass (g)", massPod.toFixed(0), massNp.toFixed(0), `−${dMass.toFixed(0)}`],
    ["CG aft of wing-root leading edge (mm)", f(MASS.cg_aft_of_root_le_mm, 1), f(MASS_NP.cg_aft_of_root_le_mm, 1), f(MASS_NP.cg_aft_of_root_le_mm - MASS.cg_aft_of_root_le_mm, 1)],
    ["CG lateral offset, y (mm)", f(MASS.cg_flu_m[1] * 1000, 1), f(MASS_NP.cg_flu_m[1] * 1000, 1), f((MASS_NP.cg_flu_m[1] - MASS.cg_flu_m[1]) * 1000, 1)],
    ["Roll inertia Ixx (kg·m²)", f(MASS.inertia_about_cg[0][0], 4), f(MASS_NP.inertia_about_cg[0][0], 4), dI(0)],
    ["Pitch inertia Iyy (kg·m²)", f(MASS.inertia_about_cg[1][1], 4), f(MASS_NP.inertia_about_cg[1][1], 4), dI(1)],
    ["Yaw inertia Izz (kg·m²)", f(MASS.inertia_about_cg[2][2], 4), f(MASS_NP.inertia_about_cg[2][2], 4), dI(2)],
  ], { colW: [4.2, 1.6, 1.6, 1.6], rowH: 0.36, fontSize: 13 });
  bullets(s, [
    `Less mass means less weight to lift, so the lighter airframe has more thrust per kilogram.`,
    `The CG moves less than 1 mm, so the balance of the aircraft is the same. The pod sits close to the centre of mass.`,
    `Inertia is resistance to rotation. Roll and pitch inertia fall by about 2%, so the aircraft turns a little more easily.`,
  ], { x: 0.5, y: 4.15, w: 9, h: 1.0 }, 12);
  footer(s);
}

// 7. Hover numbers: table of climb and hold results
{
  const s = pres.addSlide();
  title(s, "Hover: the lighter airframe climbs higher and holds with similar attitude");
  table(s, ["Hover test", "With pod", "Without pod"], [
    ["Altitude at end of climb (m)", f(P.hover.climb.alt_end_m), f(N.hover.climb.alt_end_m)],
    ["Peak climb rate (m/s)", f(P.hover.climb.peak_vertical_rate_ms), f(N.hover.climb.peak_vertical_rate_ms)],
    ["Hold altitude, mean (m)", f(P.hover.hold.alt_mean_m), f(N.hover.hold.alt_mean_m)],
    ["Hold altitude, spread (std, m)", f(P.hover.hold.alt_std_m), f(N.hover.hold.alt_std_m)],
    ["Hold roll, RMS (°)", f(P.hover.hold.roll_rms_deg), f(N.hover.hold.roll_rms_deg)],
    ["Hold pitch, RMS (°)", f(P.hover.hold.pitch_rms_deg), f(N.hover.hold.pitch_rms_deg)],
    ["Hold largest roll or pitch (°)", f(Math.max(P.hover.hold.max_abs_roll_deg, P.hover.hold.max_abs_pitch_deg), 1), f(Math.max(N.hover.hold.max_abs_roll_deg, N.hover.hold.max_abs_pitch_deg), 1)],
  ], { colW: [5, 2, 2], rowH: 0.34, fontSize: 13 });
  bullets(s, [
    "RMS (root mean square) is the typical size of the tilt. Zero means perfectly level. Lower is steadier.",
    "Spread (std) is how much the altitude wanders during the 10 s hold. Both are steady: under 0.2 m.",
    `Climb: the same throttle gives the lighter airframe a faster climb, so it finishes the climb higher (${f(N.hover.climb.alt_end_m, 1)} m against ${f(P.hover.climb.alt_end_m, 1)} m).`,
  ], { x: 0.5, y: 4.3, w: 9, h: 0.9 }, 12);
  footer(s);
}

// 8. Hover chart: the altitude, roll and pitch traces picture (made by flight_metrics.py)
{
  const s = pres.addSlide();
  title(s, "Hover flight: altitude, roll and pitch over the whole test");
  s.addImage({ path: CH("hover_timeseries"), x: 0.9, y: 1.05, w: 8.2, h: 3.6 });
  s.addText("Climb is the straight ramp, the hold is the flat section, and the descent (QLAND) is on the right. Roll and pitch stay small during the hold; they grow during the descent.",
    { x: 0.5, y: 4.7, w: 9, h: 0.5, fontFace: FONT, fontSize: 13, color: C.ink, margin: 0, isTextBox: true });
  footer(s);
}

// 9. Forward flight: table of speed and altitude numbers
{
  const s = pres.addSlide();
  title(s, "Forward flight: both reach about 20 m/s", "FBWB for 30 s. Steady values use the second half of the phase.");
  table(s, ["Forward flight", "With pod", "Without pod"], [
    ["Time to reach 12 m/s (s)", f(P.transition.forward.time_to_12ms_s, 1), f(N.transition.forward.time_to_12ms_s, 1)],
    ["Ground speed, steady mean (m/s)", f(P.transition.forward.gs_mean_steady_ms, 1), f(N.transition.forward.gs_mean_steady_ms, 1)],
    ["Ground speed, maximum (m/s)", f(P.transition.forward.gs_max_ms, 1), f(N.transition.forward.gs_max_ms, 1)],
    ["Altitude, steady mean (m)", f(P.transition.forward.alt_mean_steady_m, 1), f(N.transition.forward.alt_mean_steady_m, 1)],
    ["Altitude, spread (std, m)", f(P.transition.forward.alt_std_steady_m, 2), f(N.transition.forward.alt_std_steady_m, 2)],
    ["Pitch, RMS (°)", f(P.transition.forward.pitch_rms_steady_deg, 2), f(N.transition.forward.pitch_rms_steady_deg, 2)],
    ["Roll, RMS (°)", f(P.transition.forward.roll_rms_steady_deg, 2), f(N.transition.forward.roll_rms_steady_deg, 2)],
  ], { colW: [5, 2, 2], rowH: 0.33, fontSize: 13 });
  bullets(s, [
    "Both reach the same cruise speed of about 20 m/s, so the wings carry the aircraft in both cases.",
    `The lighter airframe accelerates to 12 m/s in ${f(N.transition.forward.time_to_12ms_s, 1)} s instead of ${f(P.transition.forward.time_to_12ms_s, 1)} s.`,
    `Without the pod, altitude was still changing: it peaked at ${f(N.transition.forward.alt_max_m, 0)} m and fell to ${f(N.transition.forward.alt_min_m, 0)} m. That spread is the energy being traded between speed and height, not instability.`,
  ], { x: 0.5, y: 4.3, w: 9, h: 0.9 }, 12);
  footer(s);
}

// 10. Transition chart: airspeed and tilt command over the whole test
{
  const s = pres.addSlide();
  title(s, "Transition: airspeed and tilt command");
  s.addImage({ path: CH("transition_speed_tilt"), x: 0.9, y: 1.0, w: 8.2, h: 3.5 });
  s.addText("Tilt (bottom): 1000 = rotors pointing up (hover), 2000 = rotors pointing forward (cruise). The command goes forward before forward flight and back afterwards. Airspeed (top) rises once the wings carry the aircraft.",
    { x: 0.5, y: 4.55, w: 9, h: 0.6, fontFace: FONT, fontSize: 13, color: C.ink, margin: 0, isTextBox: true });
  footer(s);
}

// 11. Transition chart: altitude and attitude over the whole test
{
  const s = pres.addSlide();
  title(s, "Transition flight: altitude, roll and pitch over the whole test");
  s.addImage({ path: CH("transition_timeseries"), x: 1.3, y: 1.0, w: 7.4, h: 3.75 });
  s.addText("Left to right: climb, hold, forward flight, return to hover, and landing. The large swings on the right are the landing descent in both versions.",
    { x: 0.5, y: 4.8, w: 9, h: 0.4, fontFace: FONT, fontSize: 13, color: C.ink, margin: 0, isTextBox: true });
  footer(s);
}

// 12. Return to hover and landing: table of the final phases
{
  const s = pres.addSlide();
  title(s, "Return to hover and landing");
  table(s, ["Transition test: return and landing", "With pod", "Without pod"], [
    ["Return to hover: pitch, RMS (°)", f(P.transition.back_transition.pitch_rms_deg), f(N.transition.back_transition.pitch_rms_deg)],
    ["Return to hover: time to settle within 2° (s)", f(P.transition.back_transition.settle_2deg_s, 1), f(N.transition.back_transition.settle_2deg_s, 1)],
    ["Landing: time to get below 0.5 m (s)", f(P.transition.land.touchdown_s, 1), f(N.transition.land.touchdown_s, 1)],
    ["Landing: mean descent rate (m/s)", f(P.transition.land.mean_descent_rate_ms), f(N.transition.land.mean_descent_rate_ms)],
    ["Landing: fastest descent (m/s)", f(P.transition.land.max_descent_rate_ms), f(N.transition.land.max_descent_rate_ms)],
    ["Landing: largest roll (°)", f(P.transition.land.max_abs_roll_deg, 1), f(N.transition.land.max_abs_roll_deg, 1)],
    ["Landing: largest pitch (°)", f(P.transition.land.max_abs_pitch_deg, 1), f(N.transition.land.max_abs_pitch_deg, 1)],
  ], { colW: [5.4, 1.8, 1.8], rowH: 0.33, fontSize: 13 });
  bullets(s, [
    "The mean descent rate (0.2–0.5 m/s) is gentle. The fastest rates (1.4–2.3 m/s) happen during the swings, which is when a touchdown would be hard.",
    "Neither landing settles inside 2°. The landing controller is what needs tuning; the pod does not change that.",
  ], { x: 0.5, y: 4.1, w: 9, h: 1.0 }, 13);
  footer(s);
}

// 13. Control effort: how hard the autopilot works (motor, tilt, aileron and V-tail commands)
{
  const s = pres.addSlide();
  title(s, "Control effort in hover", "Hold phase. Spread (std) is how much each command moves: higher means the controller is working harder.");
  const hp = P.hover.hold, hn = N.hover.hold;
  const trio = (a) => a.map((v) => Math.round(v)).join(" / ");
  table(s, ["Hold phase (PWM)", "With pod", "Without pod"], [
    ["Motor mean: front-right / front-left / rear", trio(hp.motor_mean_pwm), trio(hn.motor_mean_pwm)],
    ["Motor spread (std): front-right / front-left / rear", trio(hp.motor_std_pwm), trio(hn.motor_std_pwm)],
    ["Tilt servo mean (1000 = hover)", f(hp.tilt_mean_pwm, 0), f(hn.tilt_mean_pwm, 0)],
    ["Aileron spread (std)", f(hp.aileron_std_pwm, 1), f(hn.aileron_std_pwm, 1)],
    ["V-tail spread (std)", f(hp.vtail_std_pwm, 1), f(hn.vtail_std_pwm, 1)],
  ], { colW: [5, 2, 2], rowH: 0.36, fontSize: 13 });
  bullets(s, [
    `Without the pod the ailerons work about ${(N.hover.hold.aileron_std_pwm / P.hover.hold.aileron_std_pwm).toFixed(0)} times as hard in hover (${f(N.hover.hold.aileron_std_pwm, 1)} against ${f(P.hover.hold.aileron_std_pwm, 1)} PWM). The roll is being corrected more often.`,
    "The motors run near 1,700 PWM in both (about hover thrust), and their spread is small, so the throttle is steady.",
  ], { x: 0.5, y: 3.7, w: 9, h: 1.4 }, 13);
  footer(s);
}

// 14. Interpretation: what the differences mean, in words
{
  const s = pres.addSlide();
  title(s, "What the differences mean");
  bullets(s, [
    "The 150 g is the main difference. Both get the same throttle, so the lighter airframe has more thrust for its weight. It climbs higher and reaches forward speed sooner.",
    "The CG barely moves, so the pod is not a balance problem. Without it, mass falls about 6% and roll and pitch inertia fall about 2%: the aircraft responds a little more quickly.",
    "In hover, both attitudes are similar. The without-pod airframe needs more aileron correction, and it moves more in pitch in both hover and forward flight.",
    "The landing swings affect both versions alike. That is a tuning problem for the landing controller, not a pod problem.",
  ], { x: 0.5, y: 1.2, w: 9, h: 3.9 }, 15);
  footer(s);
}

// 15. Caveats and next steps: what the results do not prove
{
  const s = pres.addSlide();
  title(s, "Caveats and next steps");
  bullets(s, [
    "Each airframe flew once per test. Two runs of the with-pod hover already differed by about 3° in largest tilt, so differences smaller than that are not meaningful.",
    "The printed airframe mass (1.0 kg) is assumed, not weighed. The pod's 150 g (2 × 75 g) is also an estimate.",
    "Drag is one fixed value for both versions. The model does not reduce drag when the pod is removed, so the real airframe without the pod is probably a little faster.",
    "Aerodynamic and propeller coefficients come from the manual and estimates, not from wind-tunnel or flight data.",
    "Next: re-tune the landing controller, repeat each test three times, and weigh the printed parts to firm up the mass.",
  ], { x: 0.5, y: 1.2, w: 9, h: 3.9 }, 15);
  footer(s);
}

// Write the file. writeFile returns a promise (an "I will finish later" object), so
// .then() runs after the file is saved, and prints where it went.
const out = R("docs/Stallion_V2_Pod_vs_NoPod_Flight_Dynamics.pptx");
pres.writeFile({ fileName: out }).then(() => console.log(`wrote ${out} (${pageNo + 1} slides)`));
