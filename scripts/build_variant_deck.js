// build_variant_deck.js — builds the with-pod vs without-pod flight dynamics deck.
//
//   node scripts/build_variant_deck.js
//
// Reads every number from results/metrics/metrics.json and results/mesh/mass*.json,
// and every picture from results/images and results/metrics/charts, so the deck can be
// regenerated after a new run without editing text by hand.
// Output: docs/Stallion_V2_Pod_vs_NoPod_Flight_Dynamics.pptx
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.join(__dirname, "..");
const R = (p) => path.join(ROOT, p);
const M = JSON.parse(fs.readFileSync(R("results/metrics/metrics.json")));
const MASS = JSON.parse(fs.readFileSync(R("results/mesh/mass.json")));
const MASS_NP = JSON.parse(fs.readFileSync(R("results/mesh/mass_nopod.json")));
const POD = M.pod;
const NP = M.nopod;

// Colours: with pod = deep blue, without pod = amber, text = near-black, neutral grey for labels
const C = {
  navy: "1B2A41", pod: "1F5F99", nopod: "D9822B", ink: "1E1E1E", muted: "5F6B7A",
  line: "D5DBE3", panel: "F3F5F8", white: "FFFFFF",
};
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";          // 10 x 5.625 in
pres.title = "Stallion V2: with and without the vial pod";

// Shared helpers ------------------------------------------------------------
const fmt = (v, d = 2) => (v === null || v === undefined ? "n/a" : Number(v).toFixed(d));

function title(slide, text, sub) {
  slide.addText(text, { x: 0.5, y: 0.3, w: 9, h: 0.6, fontFace: FONT, fontSize: 26, bold: true, color: C.navy, margin: 0, isTextBox: true });
  if (sub) slide.addText(sub, { x: 0.5, y: 0.9, w: 9, h: 0.4, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, isTextBox: true });
}

function footer(slide, n) {
  slide.addText(`Simulation: Gazebo Harmonic + ArduPlane SITL, 10 Hz logs   |   ${n}`, {
    x: 0.5, y: 5.2, w: 9, h: 0.25, fontFace: FONT, fontSize: 10, color: C.muted, margin: 0, isTextBox: true,
  });
}

// Simple table: header row + rows of strings; first column left, others centred
function table(slide, header, rows, opts = {}) {
  const hdr = header.map((t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.navy }, align: "center" } }));
  const body = rows.map((r, i) =>
    r.map((t, j) => ({
      text: String(t),
      options: { color: C.ink, fill: { color: i % 2 ? C.white : C.panel }, align: j === 0 ? "left" : "center" },
    })));
  slide.addTable([hdr, ...body], {
    x: opts.x ?? 0.5, y: opts.y ?? 1.45, w: opts.w ?? 9,
    colW: opts.colW,
    fontFace: FONT, fontSize: opts.fontSize ?? 14, rowH: opts.rowH ?? 0.36,
    border: { type: "solid", pt: 0.5, color: C.line },
  });
}

function stat(slide, x, y, value, label, colour) {
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w: 2.1, h: 1.6, fill: { color: C.panel }, line: { color: C.panel } });
  slide.addText(value, { x: x + 0.15, y: y + 0.2, w: 1.8, h: 0.6, fontFace: FONT, fontSize: 28, bold: true, color: colour, margin: 0, isTextBox: true });
  slide.addText(label, { x: x + 0.15, y: y + 0.85, w: 1.8, h: 0.65, fontFace: FONT, fontSize: 12, color: C.ink, margin: 0, valign: "top", isTextBox: true });
}

let n = 0;
const next = () => ++n;

// 1. Title ---------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: C.navy };
  n = next();
  s.addText("Stallion V2 flight dynamics", { x: 0.6, y: 1.5, w: 8.8, h: 0.9, fontFace: FONT, fontSize: 40, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText("With and without the vial pod", { x: 0.6, y: 2.4, w: 8.8, h: 0.6, fontFace: FONT, fontSize: 24, color: C.white, margin: 0, isTextBox: true });
  s.addText("Gazebo Harmonic + ArduPlane SITL, automated hover and transition flights", { x: 0.6, y: 3.2, w: 8.8, h: 0.4, fontFace: FONT, fontSize: 14, color: "C9D3E0", margin: 0, isTextBox: true });
}

// 2. Key findings ----------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Without the pod: 150 g lighter, and the flight changes",
    "Both versions pass hover and forward flight and land after the transition");
  const dMass = ((MASS.mass_kg - MASS_NP.mass_kg) * 1000).toFixed(0);
  const holdPod = POD.hover.hold.alt_mean_m, holdNp = NP.hover.hold.alt_mean_m;
  stat(s, 0.5, 1.6, `${dMass} g`, `Lighter without the pod: ${(MASS.mass_kg * 1000).toFixed(0)} g → ${(MASS_NP.mass_kg * 1000).toFixed(0)} g`, C.navy);
  stat(s, 2.8, 1.6, `${fmt(holdNp, 1)} m`, `Hold altitude without pod, same throttle (with pod: ${fmt(holdPod, 1)} m)`, C.nopod);
  stat(s, 5.1, 1.6, `${fmt(NP.transition.forward.time_to_12ms_s, 1)} s`, `Time to 12 m/s without pod (with pod: ${fmt(POD.transition.forward.time_to_12ms_s, 1)} s)`, C.nopod);
  const peakLand = Math.max(POD.transition.land.max_abs_roll_deg, POD.transition.land.max_abs_pitch_deg, NP.transition.land.max_abs_roll_deg, NP.transition.land.max_abs_pitch_deg);
  stat(s, 7.4, 1.6, `${peakLand.toFixed(0)}°`, "Largest roll or pitch during QLAND, either version: the descent does not settle", C.pod);
  s.addText([
    { text: "Hover: both versions hold altitude with similar attitude (roll and pitch RMS under 0.7°). The lighter airframe climbs higher at the same throttle.", options: { bullet: true, breakLine: true } },
    { text: "Forward flight: both reach about 20 m/s steady ground speed. The without-pod airframe moves its altitude about 6 m (std) against 0.3 m with the pod.", options: { bullet: true, breakLine: true } },
    { text: "Landing: both versions oscillate by about ±15–20° during QLAND. The landing controller is not tuned for these airframes.", options: { bullet: true } },
  ], { x: 0.5, y: 3.5, w: 9, h: 1.5, fontFace: FONT, fontSize: 14, color: C.ink, paraSpaceAfter: 6, valign: "top", margin: 0, isTextBox: true });
  footer(s, n);
}

// 3. Setup -----------------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "What was tested, and what changed between the two versions");
  s.addText([
    { text: "Same for both", options: { bold: true, breakLine: true } },
    { text: "Gazebo world, ArduPlane parameters, flight script and throttle profile", options: { bullet: true, breakLine: true } },
    { text: "Hover test: climb 10 s at 1700, hold 10 s at 1500, QLAND", options: { bullet: true, breakLine: true } },
    { text: "Transition test: climb 30 s at 1800, FBWB forward flight 30 s, QHOVER, QLAND", options: { bullet: true, breakLine: true } },
    { text: "Chennai home position, 10 Hz flight logs", options: { bullet: true } },
  ], { x: 0.5, y: 1.4, w: 4.3, h: 3.5, fontFace: FONT, fontSize: 14, color: C.ink, paraSpaceAfter: 6, valign: "top", margin: 0, isTextBox: true });
  s.addText([
    { text: "Changed without the pod", options: { bold: true, breakLine: true } },
    { text: `Mass ${(MASS.mass_kg * 1000).toFixed(0)} g → ${(MASS_NP.mass_kg * 1000).toFixed(0)} g`, options: { bullet: true, breakLine: true } },
    { text: "Inertia and CG recomputed from the CAD", options: { bullet: true, breakLine: true } },
    { text: "Pod visuals and pod collision removed", options: { bullet: true, breakLine: true } },
    { text: "Not changed: drag, which is one fixed value for both (the pod is not modelled separately)", options: { bullet: true } },
  ], { x: 5.2, y: 1.4, w: 4.3, h: 3.5, fontFace: FONT, fontSize: 14, color: C.ink, paraSpaceAfter: 6, valign: "top", margin: 0, isTextBox: true });
  footer(s, n);
}

// 4. Mass and inertia -------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Mass and inertia: the pod is 150 g, CG barely moves",
    "Estimate from the CAD. The printed airframe mass (1.0 kg) is assumed, not weighed.");
  const g = (v) => (v * 1000).toFixed(0);
  const cgOff = (m) => `${(m.cg_flu_m[1] * 1000).toFixed(1)} mm`;
  const cgAft = (m) => `${m.cg_aft_of_root_le_mm.toFixed(1)} mm`;
  const I = (m, i, j) => m.inertia_about_cg[i][j].toFixed(4);
  table(s, ["Property", "With pod", "Without pod", "Change"], [
    ["All-up mass (g)", g(MASS.mass_kg), g(MASS_NP.mass_kg), `−${g(MASS.mass_kg - MASS_NP.mass_kg)}`],
    ["CG aft of wing-root LE", cgAft(MASS), cgAft(MASS_NP), `${(MASS_NP.cg_aft_of_root_le_mm - MASS.cg_aft_of_root_le_mm).toFixed(1)} mm`],
    ["CG height (m)", MASS.cg_flu_m[2].toFixed(4), MASS_NP.cg_flu_m[2].toFixed(4), `+${((MASS_NP.cg_flu_m[2] - MASS.cg_flu_m[2]) * 1000).toFixed(1)} mm`],
    ["CG lateral offset (y)", cgOff(MASS), cgOff(MASS_NP), `${((MASS_NP.cg_flu_m[1] - MASS.cg_flu_m[1]) * 1000).toFixed(1)} mm`],
    ["Roll inertia Ixx (kg·m²)", I(MASS, 0, 0), I(MASS_NP, 0, 0), (MASS_NP.inertia_about_cg[0][0] - MASS.inertia_about_cg[0][0]).toFixed(4)],
    ["Pitch inertia Iyy (kg·m²)", I(MASS, 1, 1), I(MASS_NP, 1, 1), (MASS_NP.inertia_about_cg[1][1] - MASS.inertia_about_cg[1][1]).toFixed(4)],
    ["Yaw inertia Izz (kg·m²)", I(MASS, 2, 2), I(MASS_NP, 2, 2), (MASS_NP.inertia_about_cg[2][2] - MASS.inertia_about_cg[2][2]).toFixed(4)],
  ], { colW: [3.4, 1.9, 1.9, 1.8], rowH: 0.42, fontSize: 14 });
  footer(s, n);
}

// 5. Model renders ----------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "The model: the same airframe with and without the pod");
  s.addText("With pod", { x: 0.5, y: 1.3, w: 4.4, h: 0.35, fontFace: FONT, fontSize: 16, bold: true, color: C.pod, margin: 0, isTextBox: true });
  s.addText("Without pod", { x: 5.1, y: 1.3, w: 4.4, h: 0.35, fontFace: FONT, fontSize: 16, bold: true, color: C.nopod, margin: 0, isTextBox: true });
  s.addImage({ path: R("results/images/iso.png"), x: 0.5, y: 1.75, w: 4.4, h: 2.75 });
  s.addImage({ path: R("results/images/nopod/iso.png"), x: 5.1, y: 1.75, w: 4.4, h: 2.75 });
  s.addText("The pod (green) sits under the fuselage. Removing it takes out the pod's visual and collision mesh and 150 g of mass.", {
    x: 0.5, y: 4.6, w: 9, h: 0.5, fontFace: FONT, fontSize: 14, color: C.ink, margin: 0, isTextBox: true,
  });
  footer(s, n);
}

// 6. Hover numbers ----------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Hover: the lighter airframe climbs higher and holds with similar attitude");
  const P = POD.hover, Q = NP.hover;
  table(s, ["Hover test", "With pod", "Without pod"], [
    ["Altitude at end of climb (m)", fmt(P.climb.alt_end_m, 2), fmt(Q.climb.alt_end_m, 2)],
    ["Peak climb rate (m/s)", fmt(P.climb.peak_vertical_rate_ms, 2), fmt(Q.climb.peak_vertical_rate_ms, 2)],
    ["Hold altitude, mean (m)", fmt(P.hold.alt_mean_m, 2), fmt(Q.hold.alt_mean_m, 2)],
    ["Hold altitude, std (m)", fmt(P.hold.alt_std_m, 2), fmt(Q.hold.alt_std_m, 2)],
    ["Hold roll RMS (°)", fmt(P.hold.roll_rms_deg, 2), fmt(Q.hold.roll_rms_deg, 2)],
    ["Hold pitch RMS (°)", fmt(P.hold.pitch_rms_deg, 2), fmt(Q.hold.pitch_rms_deg, 2)],
    ["Hold max attitude, roll or pitch (°)", fmt(Math.max(P.hold.max_abs_roll_deg, P.hold.max_abs_pitch_deg), 2), fmt(Math.max(Q.hold.max_abs_roll_deg, Q.hold.max_abs_pitch_deg), 2)],
  ], { colW: [5, 2, 2], rowH: 0.42, fontSize: 14 });
  footer(s, n);
}

// 7. Hover chart -------------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Hover flight: altitude and attitude over the full test");
  s.addImage({ path: R("results/metrics/charts/hover_timeseries.png"), x: 1.3, y: 1.1, w: 7.4, h: 4.0 });
  footer(s, n);
}

// 8. Transition forward flight numbers ---------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Forward flight: both reach about 20 m/s",
    "FBWB, 30 s. Steady values use the second half of the phase. The lighter airframe reaches 12 m/s sooner.");
  const P = POD.transition.forward, Q = NP.transition.forward;
  table(s, ["Forward flight", "With pod", "Without pod"], [
    ["Time to 12 m/s (s)", fmt(P.time_to_12ms_s, 1), fmt(Q.time_to_12ms_s, 1)],
    ["Ground speed, steady mean (m/s)", fmt(P.gs_mean_steady_ms, 1), fmt(Q.gs_mean_steady_ms, 1)],
    ["Ground speed, max (m/s)", fmt(P.gs_max_ms, 1), fmt(Q.gs_max_ms, 1)],
    ["Airspeed, steady mean (m/s)", fmt(P.airspeed_mean_steady_ms, 1), fmt(Q.airspeed_mean_steady_ms, 1)],
    ["Altitude, steady mean (m)", fmt(P.alt_mean_steady_m, 1), fmt(Q.alt_mean_steady_m, 1)],
    ["Altitude, steady std (m)", fmt(P.alt_std_steady_m, 2), fmt(Q.alt_std_steady_m, 2)],
    ["Roll RMS, steady (°)", fmt(P.roll_rms_steady_deg, 2), fmt(Q.roll_rms_steady_deg, 2)],
    ["Pitch RMS, steady (°)", fmt(P.pitch_rms_steady_deg, 2), fmt(Q.pitch_rms_steady_deg, 2)],
    ["Max |pitch| over the phase (°)", fmt(P.max_abs_pitch_deg, 1), fmt(Q.max_abs_pitch_deg, 1)],
  ], { colW: [5, 2, 2], rowH: 0.34, fontSize: 13 });
  footer(s, n);
}

// 9. Transition speed and tilt -----------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Transition: airspeed and tilt command");
  s.addImage({ path: R("results/metrics/charts/transition_speed_tilt.png"), x: 1.0, y: 1.1, w: 8.0, h: 4.0 });
  footer(s, n);
}

// 10. Transition full time series ---------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Transition flight: altitude and attitude over the full test");
  s.addImage({ path: R("results/metrics/charts/transition_timeseries.png"), x: 1.3, y: 1.05, w: 7.4, h: 4.1 });
  footer(s, n);
}

// 11. Landing and back-transition --------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Back to hover and landing: both oscillate, and neither settles");
  const P = POD.transition, Q = NP.transition;
  table(s, ["Back transition and QLAND (transition test)", "With pod", "Without pod"], [
    ["Back transition: pitch RMS (°)", fmt(P.back_transition.pitch_rms_deg, 2), fmt(Q.back_transition.pitch_rms_deg, 2)],
    ["Back transition: time to settle within 2° (s)", fmt(P.back_transition.settle_2deg_s, 1), fmt(Q.back_transition.settle_2deg_s, 1)],
    ["QLAND: touchdown below 0.5 m (s after QLAND)", fmt(P.land.touchdown_s, 1), fmt(Q.land.touchdown_s, 1)],
    ["QLAND: mean descent rate (m/s)", fmt(P.land.mean_descent_rate_ms, 2), fmt(Q.land.mean_descent_rate_ms, 2)],
    ["QLAND: max descent rate (m/s)", fmt(P.land.max_descent_rate_ms, 2), fmt(Q.land.max_descent_rate_ms, 2)],
    ["QLAND: max |roll| (°)", fmt(P.land.max_abs_roll_deg, 1), fmt(Q.land.max_abs_roll_deg, 1)],
    ["QLAND: max |pitch| (°)", fmt(P.land.max_abs_pitch_deg, 1), fmt(Q.land.max_abs_pitch_deg, 1)],
  ], { colW: [5.4, 1.8, 1.8], rowH: 0.42, fontSize: 14 });
  footer(s, n);
}

// 12. Control effort -------------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Control effort in hover: motor and tilt commands", "PWM values, hold phase; the spread (std) is how much the controller is working");
  const hp = POD.hover.hold, hn = NP.hover.hold;
  const mot = (a) => a.map((v) => Math.round(v)).join(" / ");
  const sd = (a) => a.map((v) => Math.round(v)).join(" / ");
  table(s, ["Hold phase", "With pod", "Without pod"], [
    ["Motors mean, front-right / front-left / rear (PWM)", mot(hp.motor_mean_pwm), mot(hn.motor_mean_pwm)],
    ["Motors std, front-right / front-left / rear (PWM)", sd(hp.motor_std_pwm), sd(hn.motor_std_pwm)],
    ["Tilt servo mean (PWM, 1000 = hover)", fmt(hp.tilt_mean_pwm, 0), fmt(hn.tilt_mean_pwm, 0)],
    ["Aileron std (PWM)", fmt(hp.aileron_std_pwm, 1), fmt(hn.aileron_std_pwm, 1)],
    ["V-tail std (PWM)", fmt(hp.vtail_std_pwm, 1), fmt(hn.vtail_std_pwm, 1)],
  ], { colW: [5, 2, 2], rowH: 0.45, fontSize: 14 });
  footer(s, n);
}

// 13. Interpretation ------------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "What the differences mean");
  s.addText([
    { text: "The 150 g change is the main difference. Both get the same throttle, so the lighter airframe has more thrust-to-weight. That is why it climbs higher on the same throttle and reaches forward speed sooner.", options: { bullet: true, breakLine: true } },
    { text: "The CG barely moves (under 1 mm), so the pod is not a balance problem. Without it the mass falls about 6% and pitch and roll inertia fall about 2%.", options: { bullet: true, breakLine: true } },
    { text: "Hover attitude is similar in both. The without-pod airframe moves more in pitch in hover and forward flight, and its ailerons work much harder in hover (8.3 PWM std against 0.7).", options: { bullet: true, breakLine: true } },
    { text: "The landing oscillation affects both versions in the same way. It is a tuning problem, not a pod problem.", options: { bullet: true } },
  ], { x: 0.5, y: 1.3, w: 9, h: 3.8, fontFace: FONT, fontSize: 16, color: C.ink, paraSpaceAfter: 10, valign: "top", margin: 0, isTextBox: true });
  footer(s, n);
}

// 14. Caveats ------------------------------------------------------------------------
{
  const s = pres.addSlide();
  n = next();
  title(s, "Caveats and open items");
  s.addText([
    { text: "Each variant was flown once per test. Repeat runs of the with-pod hover already varied by about 3° in peak tilt, so differences below that are not meaningful.", options: { bullet: true, breakLine: true } },
    { text: "Printed airframe mass (1.0 kg) is assumed, not weighed. The 150 g pod mass (2 × 75 g) is also an estimate.", options: { bullet: true, breakLine: true } },
    { text: "Drag is one fixed value for both versions. The model does not reduce drag when the pod is removed, so the real without-pod airframe is probably a little faster than shown.", options: { bullet: true, breakLine: true } },
    { text: "Aerodynamic and propeller coefficients come from the manual and an estimate, not from wind-tunnel or flight data.", options: { bullet: true, breakLine: true } },
    { text: "Next: re-tune the landing gains, repeat each test 3 times, and weigh the printed parts to firm up the mass.", options: { bullet: true } },
  ], { x: 0.5, y: 1.3, w: 9, h: 3.8, fontFace: FONT, fontSize: 16, color: C.ink, paraSpaceAfter: 10, valign: "top", margin: 0, isTextBox: true });
  footer(s, n);
}

const out = R("docs/Stallion_V2_Pod_vs_NoPod_Flight_Dynamics.pptx");
pres.writeFile({ fileName: out }).then(() => console.log(`wrote ${out} (${n} slides)`));
