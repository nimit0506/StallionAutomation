// ============================================================================
// build_box_deck.js — short, simple deck: Stallion V2 with vs without the box
// ============================================================================
//
// WHAT THIS FILE DOES (plain language)
//   Writes a 6-slide PowerPoint from the results of the updated flight sim:
//     results/box_vs_nobox/summary.json   numbers (from scripts/box_compare.py)
//     results/box_vs_nobox/chart.png      height and airspeed chart
//     results/images/gazebo/...           Gazebo renders of the two aircraft
//
// HOW TO RUN IT
//   npm install pptxgenjs          (once, in any folder)
//   NODE_PATH=/path/to/node_modules node scripts/build_box_deck.js
//   Output: docs/Stallion_V2_Box_vs_NoBox_Flight_Sim.pptx
//
// Layout units are inches. A 16:9 slide is 10 x 5.625 in; x from the left, y from the top.
// ============================================================================
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.join(__dirname, "..");
const R = (p) => path.join(ROOT, p);
const S = JSON.parse(fs.readFileSync(R("results/box_vs_nobox/summary.json")));
const B = S.box, N = S.nobox;             // B = with box, N = without box

// Colours (hex, no #): navy titles, blue = with box, amber = without box
const C = { navy: "1B2A41", box: "1F5F99", nobox: "D9822B", ink: "1E1E1E", muted: "5F6B7A",
            line: "D5DBE3", panel: "F3F5F8", white: "FFFFFF" };
const FONT = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.title = "Stallion V2: with vs without the box (flight sim)";
let page = 0;

// Title at the top of a slide, optional grey subtitle
function title(s, text, sub) {
  s.addText(text, { x: 0.5, y: 0.3, w: 9, h: 0.6, fontFace: FONT, fontSize: 26, bold: true, color: C.navy, margin: 0, isTextBox: true });
  if (sub) s.addText(sub, { x: 0.5, y: 0.9, w: 9, h: 0.35, fontFace: FONT, fontSize: 14, color: C.muted, margin: 0, isTextBox: true });
}
// Grey footer with the slide number
function footer(s) {
  page += 1;
  s.addText(`Gazebo + ArduPlane SITL · assumptions from the CFD study (0.8 mm walls)   |   ${page}`,
    { x: 0.5, y: 5.25, w: 9, h: 0.25, fontFace: FONT, fontSize: 10, color: C.muted, margin: 0, isTextBox: true });
}
// Bulleted list in a box
function bullets(s, items, box, size = 15) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })),
    { ...box, fontFace: FONT, fontSize: size, color: C.ink, paraSpaceAfter: 8, valign: "top", margin: 0, isTextBox: true });
}
// Table: header row in navy, alternating light rows; first column left-aligned
function table(s, header, rows, opts) {
  const hdr = header.map((t) => ({ text: t, options: { bold: true, color: C.white, fill: { color: C.navy }, align: "center" } }));
  const body = rows.map((r, i) => r.map((t, j) => ({ text: String(t),
    options: { color: C.ink, fill: { color: i % 2 ? C.white : C.panel }, align: j === 0 ? "left" : "center" } })));
  s.addTable([hdr, ...body], { x: 0.5, y: opts.y, w: 9, colW: opts.colW, fontFace: FONT,
    fontSize: opts.fontSize || 14, rowH: opts.rowH || 0.38, border: { type: "solid", pt: 0.5, color: C.line } });
}
const yn = (ok, yes, no) => (ok ? yes : no);

// Plain-language conclusions for the last slide (numbers come from summary.json)
const TAKEAWAYS = [
  "With the CFD weights, the box hardly changes how the aircraft flies. Hover, climb and handling are the same within the accuracy of one flight.",
  `The box's drag shows in cruise: ${B.cruise_airspeed_ms.toFixed(1)} m/s with the box against ${N.cruise_airspeed_ms.toFixed(1)} m/s without, at the same motor power. This matches the CFD finding that the box's effect is drag, not weight.`,
  `Its 40 g needs only slightly more hover power (${B.hover_motor_pwm} against ${N.hover_motor_pwm} PWM).`,
  "The large differences in the earlier sim came from wrong weights (box 150 g instead of 40 g) and from a world that ran at half speed. Both are fixed.",
];
const LIMITS = [
  "One flight per version, so small differences (for example the time to reach 12 m/s) are within run-to-run noise.",
  "Only the box's drag is in the flight sim. The CFD's change in pitch stability (static margin 7.0% with the box, 3.7% without) is not modelled.",
  "Both versions swing about 18–20° while landing. That is a controller issue and has nothing to do with the box.",
];

// 1. Title -----------------------------------------------------------------------
{
  const s = pres.addSlide();
  s.background = { color: C.navy };
  s.addText("Stallion V2: with vs without the box", { x: 0.6, y: 1.6, w: 8.8, h: 0.9, fontFace: FONT, fontSize: 36, bold: true, color: C.white, margin: 0, isTextBox: true });
  s.addText("Flight simulation, updated with the CFD study's assumptions", { x: 0.6, y: 2.5, w: 8.8, h: 0.5, fontFace: FONT, fontSize: 20, color: C.white, margin: 0, isTextBox: true });
  s.addText("Gazebo Harmonic + ArduPlane SITL · same flight for both: take off, hover, fly forward at about 20 m/s, land", { x: 0.6, y: 3.2, w: 8.8, h: 0.4, fontFace: FONT, fontSize: 13, color: "C9D3E0", margin: 0, isTextBox: true });
}

// 2. What changed in the flight sim --------------------------------------------------
{
  const s = pres.addSlide();
  title(s, "What changed in the flight sim", "The flight sim now uses the same assumptions as the CFD study");
  table(s, ["", "Before", "Now"], [
    ["Mass with box", "2451 g", "2268 g (CFD)"],
    ["Mass without box", "2301 g", "2228 g (CFD)"],
    ["Box mass", "150 g (placeholder)", "40 g (CFD)"],
    ["Drag (CD at 0°)", "same for both", "0.0665 with box, 0.0583 without (CFD)"],
    ["Simulated world", "2 aircraft: ran at half speed", "1 aircraft: full speed for both"],
    ["Height measurement", "autopilot estimate", "GPS"],
  ], { y: 1.4, colW: [2.6, 2.8, 3.6], rowH: 0.45 });
  s.addText("The old weights came from a guessed plastic mass and a 150 g box. They are now matched to the CFD mass model.",
    { x: 0.5, y: 4.55, w: 9, h: 0.5, fontFace: FONT, fontSize: 13, color: C.ink, margin: 0, isTextBox: true });
  footer(s);
}

// 3. The two aircraft (Gazebo renders) -----------------------------------------------
{
  const s = pres.addSlide();
  title(s, "The two aircraft in Gazebo", "The only difference is the box under the fuselage");
  s.addText("With box", { x: 0.5, y: 1.35, w: 4.4, h: 0.35, fontFace: FONT, fontSize: 16, bold: true, color: C.box, margin: 0, isTextBox: true });
  s.addText("Without box", { x: 5.1, y: 1.35, w: 4.4, h: 0.35, fontFace: FONT, fontSize: 16, bold: true, color: C.nobox, margin: 0, isTextBox: true });
  s.addImage({ path: R("results/images/gazebo/pod/iso.png"), x: 0.5, y: 1.8, w: 4.4, h: 2.75 });
  s.addImage({ path: R("results/images/gazebo/nopod/iso.png"), x: 5.1, y: 1.8, w: 4.4, h: 2.75 });
  footer(s);
}

// 4. Results table -------------------------------------------------------------------
{
  const s = pres.addSlide();
  title(s, "Results", "One flight per version; cruise values are the second half of forward flight");
  table(s, ["", "With box", "Without box"], [
    ["Forward flight and landing", yn(B.forward_flight_pass && B.landed, "pass", "fail"), yn(N.forward_flight_pass && N.landed, "pass", "fail")],
    ["Cruise airspeed (m/s)", B.cruise_airspeed_ms.toFixed(1), N.cruise_airspeed_ms.toFixed(1)],
    ["Cruise motor power (PWM, front motors)", B.cruise_front_motor_pwm, N.cruise_front_motor_pwm],
    ["Hover motor power (PWM, average)", B.hover_motor_pwm, N.hover_motor_pwm],
    ["Hover steadiness (tilt RMS, °)", B.hover_tilt_rms_deg.toFixed(1), N.hover_tilt_rms_deg.toFixed(1)],
    ["Rear motor share of hover thrust (CFD: 32.1%)", `${B.hover_rear_thrust_share_pct}%`, `${N.hover_rear_thrust_share_pct}%`],
    ["Climb rate (m/s)", B.climb_rate_ms.toFixed(2), N.climb_rate_ms.toFixed(2)],
    ["Time to reach 12 m/s (s)", B.time_to_12ms_s.toFixed(1), N.time_to_12ms_s.toFixed(1)],
  ], { y: 1.35, colW: [5, 2, 2], rowH: 0.42 });
  footer(s);
}

// 5. Chart --------------------------------------------------------------------------
{
  const s = pres.addSlide();
  title(s, "Height and airspeed through the flight", "Climb, hover, forward flight (about 20 m/s), back to hover, landing");
  s.addImage({ path: R("results/box_vs_nobox/chart.png"), x: 0.9, y: 1.3, w: 8.2, h: 3.8 });
  footer(s);
}

// 6. What it means -------------------------------------------------------------------
{
  const s = pres.addSlide();
  title(s, "What it means");
  bullets(s, TAKEAWAYS, { x: 0.5, y: 1.15, w: 9, h: 2.6 }, 15);
  s.addText("Limits", { x: 0.5, y: 3.75, w: 9, h: 0.3, fontFace: FONT, fontSize: 15, bold: true, color: C.navy, margin: 0, isTextBox: true });
  bullets(s, LIMITS, { x: 0.5, y: 4.08, w: 9, h: 1.1 }, 12);
  footer(s);
}

const out = R("docs/Stallion_V2_Box_vs_NoBox_Flight_Sim.pptx");
pres.writeFile({ fileName: out }).then(() => console.log(`wrote ${out} (${page + 1} slides)`));
