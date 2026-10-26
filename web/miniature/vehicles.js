// Written by AI on 2026-10-26 by model Claude Opus 5.5.
// Vehicles as 3D models from their published dimensions and liveries, drawn
// by the same pixel-art renderer as the city. Local axes: x along the vehicle
// (front = +x), y up, z across; origin at the centre of the footprint on the
// rail or road surface. Metres.
//
// References: RET Citadis 302 (Alstom): 5 sections, 31.5 m x 2.4 m, four
// double doors per side, silver-grey body with dark skirt, black front mask
// and window band, red and green stripe at the doors (Wikimedia Commons,
// "RET 2108 Citadis Barendrecht", public domain).

import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const mat = (hex) => new THREE.MeshLambertMaterial({ color: hex });
const palette = {
  silver: mat(0xc3c9cf), skirt: mat(0x55595e), glass: mat(0x1d2733), black: mat(0x15171b),
  red: mat(0xd2232a), green: mat(0x1f8a5c), roof: mat(0x8d9196), bogie: mat(0x2a2c30),
  lamp: new THREE.MeshBasicMaterial({ color: 0xfff6d8 }), yellow: mat(0xf2c418), nsBlue: mat(0x1c3f94),
  white: mat(0xeceeed), tyre: mat(0x1a1a1a), rider: mat(0x3a4a6b), skin: mat(0xd8a27c),
};

function box(w, h, d, material, x, y, z, radius = 0) {
  const geometry = radius > 0 ? new RoundedBoxGeometry(w, h, d, 2, radius) : new THREE.BoxGeometry(w, h, d);
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.set(x, y, z);
  return mesh;
}

// One car body section with window band, skirt and doors on both sides.
function section(group, x0, length, { body, glassFrom, glassTo, height, width, doors = [], doorMaterial, stripe }) {
  const cx = x0 + length / 2;
  group.add(box(length - 0.08, height - 0.35, width, body, cx, 0.35 + (height - 0.35) / 2, 0, 0.18));
  group.add(box(length - 0.1, 0.42, width + 0.02, palette.skirt, cx, 0.38, 0));
  group.add(box(length - 0.5, glassTo - glassFrom, width + 0.03, palette.glass, cx, (glassFrom + glassTo) / 2, 0));
  // Window pillars every 1.6 m, so the side reads as a row of windows.
  for (let px = x0 + 1.0; px < x0 + length - 0.6; px += 1.6) {
    if (doors.some((d) => Math.abs(x0 + d - px) < 1.0)) continue;
    group.add(box(0.22, glassTo - glassFrom, width + 0.05, body, px, (glassFrom + glassTo) / 2, 0));
  }
  for (const d of doors) {
    group.add(box(1.3, glassTo - 0.45, width + 0.04, doorMaterial ?? palette.glass, x0 + d, 0.45 + (glassTo - 0.45) / 2, 0));
    if (stripe) {
      group.add(box(0.3, 1.1, width + 0.05, stripe[0], x0 + d - 0.95, 0.95, 0));
      group.add(box(0.3, 1.1, width + 0.05, stripe[1], x0 + d - 1.25, 0.95, 0));
    }
  }
  group.add(box(length - 0.6, 0.12, width - 0.5, palette.roof, cx, height + 0.06, 0));
}

function cab(group, x, sign, { width, height, body }) {
  // Sloping front with black mask, headlamps and the red RET logo.
  const nose = box(1.2, height - 0.5, width - 0.1, body, x + sign * 0.45, 0.35 + (height - 0.5) / 2, 0, 0.35);
  group.add(nose);
  group.add(box(0.06, 1.35, width - 0.5, palette.black, x + sign * 1.06, 1.85, 0));
  group.add(box(0.06, 0.16, 0.9, palette.red, x + sign * 1.07, 0.75, 0));
  for (const s of [-0.75, 0.75]) group.add(box(0.05, 0.14, 0.2, palette.lamp, x + sign * 1.07, 0.95, s));
}

// RET Citadis 302, 2100 series in current livery, checked against 8 Commons
// photos (sources/vehicle-photos/2026-10-26/ret-tram-citadis-2100): 30.85 m x
// 2.40 m x 3.34 m, five sections, four double doors on the right side only.
// Silver body (#b9bec2 in sun), dark grey skirt (#858379), tall dark windows
// almost to the roof between silver pillars, a large black front mask with
// the destination display above it and the red RET logo below, and blue
// (#34649e) and red (#e8553c) stripes beside the doors.
export function citadisTram() {
  const group = new THREE.Group();
  const width = 2.4, height = 3.34, length = 30.85;
  const silver = mat(0xb0bac6), skirt = mat(0x6e717a), glass = mat(0x1b222c), blue = mat(0x34649e), red = mat(0xe8553c);
  const lengths = [7.4, 3.1, 8.6, 3.1, 7.4]; // cab, bogie module, centre, bogie module, cab
  const joint = 0.25;
  let x = -length / 2;
  const doorsAt = [[5.0], [], [1.9, 6.7], [], [2.4]]; // door centres from each section's start
  lengths.forEach((len, i) => {
    const cx = x + len / 2;
    group.add(box(len, height - 0.3, width, silver, cx, 0.3 + (height - 0.3) / 2, 0, 0.2));
    group.add(box(len - 0.06, 0.55, width + 0.02, skirt, cx, 0.42, 0));
    // Windows: one tall dark band from 0.95 m to 2.85 m, broken by pillars.
    group.add(box(len - 0.4, 1.9, width + 0.03, glass, cx, 1.9, 0));
    for (let px = x + 0.9; px < x + len - 0.5; px += 1.45) group.add(box(0.16, 1.9, width + 0.05, silver, px, 1.9, 0));
    for (const d of doorsAt[i]) {
      // Right side (+z) only: a silver-framed double door, with the stripes.
      group.add(box(1.32, 2.2, 0.06, glass, x + d, 1.35, width / 2 + 0.03));
      group.add(box(0.05, 2.2, 0.08, silver, x + d, 1.35, width / 2 + 0.035));
      group.add(box(0.26, 1.5, 0.06, blue, x + d - 0.95, 1.2, width / 2 + 0.03));
      group.add(box(0.26, 1.5, 0.06, red, x + d - 1.2, 1.2, width / 2 + 0.03));
    }
    group.add(box(len - 0.8, 0.14, width - 0.6, mat(0x9a9ea2), cx, height + 0.07, 0));
    if (i < lengths.length - 1) group.add(box(joint, height - 0.4, width - 0.15, skirt, x + len + joint / 2, 0.3 + (height - 0.4) / 2, 0));
    x += len + joint;
  });
  for (const sign of [-1, 1]) {
    const nx = sign * (length / 2);
    // Rounded nose, black mask with windscreen, destination display, lamps, logo.
    group.add(box(1.0, height - 0.4, width - 0.04, silver, nx - sign * 0.2, 0.3 + (height - 0.4) / 2, 0, 0.45));
    group.add(box(0.08, 2.15, width - 0.35, mat(0x111316), nx + sign * 0.31, 1.95, 0));
    group.add(box(0.09, 0.28, width - 0.8, mat(0x3a2a10), nx + sign * 0.32, 2.85, 0));
    group.add(box(0.09, 0.2, 0.8, red, nx + sign * 0.31, 0.62, 0));
    for (const s of [-0.85, 0.85]) group.add(box(0.06, 0.16, 0.22, palette.lamp, nx + sign * 0.31, 0.75, s));
  }
  // Pantograph on the centre section and roof equipment boxes.
  group.add(box(1.8, 0.1, 1.5, palette.bogie, 0, height + 0.55, 0));
  for (const dx of [-0.5, 0.5]) group.add(box(0.07, 0.5, 0.07, palette.bogie, dx, height + 0.3, 0));
  for (const dx of [-11, 11]) group.add(box(2.4, 0.3, 1.4, mat(0x8d9196), dx, height + 0.15, 0));
  group.userData = { length, width };
  return group;
}

export function retMetro() {
  // RET RSG3 metro car pair (Bombardier): 2 x 30 m, 2.65 m wide, silver
  // with red ends and a dark window band.
  const group = new THREE.Group();
  const width = 2.65, height = 3.5, spec = { body: palette.silver, glassFrom: 1.35, glassTo: 2.6, height, width };
  for (const [x0, flip] of [[-30.2, -1], [0.2, 1]]) {
    section(group, x0, 30, { ...spec, doors: [4.5, 11.5, 18.5, 25.5], doorMaterial: palette.red });
    cab(group, flip < 0 ? x0 : x0 + 30, flip, spec);
  }
  group.userData = { length: 60.4, width };
  return group;
}

export function nsSprinter() {
  // NS Sprinter (SNG, 3 cars, about 61 m): yellow body, blue band below the
  // windows, dark window band.
  const group = new THREE.Group();
  const width = 2.8, height = 3.9, spec = { body: palette.yellow, glassFrom: 1.6, glassTo: 2.7, height, width };
  for (let i = 0; i < 3; i++) {
    const x0 = -30.5 + i * 20.4;
    section(group, x0, 20.2, { ...spec, doors: [4, 16], doorMaterial: palette.yellow });
    group.add(box(19.8, 0.35, width + 0.02, palette.nsBlue, x0 + 10.1, 1.15, 0));
  }
  cab(group, -30.5, -1, spec);
  cab(group, 30.5, 1, spec);
  group.userData = { length: 61, width };
  return group;
}

export function retBus() {
  // RET electric city bus (12 m): white body, dark window band, green and
  // red accents at the rear.
  const group = new THREE.Group();
  const width = 2.55, height = 3.2;
  group.add(box(12, height - 0.3, width, palette.white, 0, 0.3 + (height - 0.3) / 2, 0, 0.25));
  group.add(box(11.2, 1.25, width + 0.03, palette.glass, -0.2, 2.05, 0));
  group.add(box(0.06, 1.7, width - 0.3, palette.glass, 6.02, 1.85, 0));
  for (const [z, m] of [[0, palette.green], [0.25, palette.red]]) group.add(box(0.2, 1.0, width + 0.04, m, -4.5 + z, 0.9, 0));
  for (const s of [-1, 1]) for (const x of [-3.7, 3.9]) group.add(box(1.0, 0.9, 0.3, palette.tyre, x, 0.45, s * (width / 2 - 0.1)));
  group.add(box(4, 0.25, 1.6, palette.roof, -2, height + 0.12, 0));
  group.userData = { length: 12, width };
  return group;
}

export function car(colour = 0xc9ccd0) {
  const group = new THREE.Group();
  const paint = mat(colour);
  group.add(box(4.4, 0.75, 1.8, paint, 0, 0.55, 0, 0.18));
  group.add(box(2.4, 0.6, 1.62, palette.glass, -0.25, 1.2, 0, 0.15));
  group.add(box(2.2, 0.08, 1.5, paint, -0.25, 1.52, 0));
  for (const x of [-1.4, 1.4]) for (const s of [-1, 1]) group.add(box(0.65, 0.65, 0.22, palette.tyre, x, 0.33, s * 0.8));
  group.userData = { length: 4.4, width: 1.8 };
  return group;
}

export function cyclist(colour = 0x3a4a6b) {
  const group = new THREE.Group();
  for (const x of [-0.55, 0.55]) group.add(box(0.7, 0.7, 0.06, palette.tyre, x, 0.35, 0));
  group.add(box(1.1, 0.06, 0.06, palette.black, 0, 0.62, 0));
  group.add(box(0.36, 0.7, 0.36, mat(colour), -0.12, 1.15, 0));
  group.add(box(0.24, 0.24, 0.24, palette.skin, -0.02, 1.62, 0));
  group.add(box(0.12, 0.5, 0.12, palette.rider, -0.05, 0.75, 0.12));
  group.userData = { length: 1.8, width: 0.6 };
  return group;
}

export const vehicleKinds = {
  tram: () => citadisTram(),
  metro: () => retMetro(),
  train: () => nsSprinter(),
  bus: () => retBus(),
  ferry: () => retBus(),
  car: (i) => car([0xd8d8d4, 0x2f3440, 0x8a1f22, 0x3b5c8c, 0xc9ccd0, 0x151719][i % 6]),
  bike: (i) => cyclist([0x3a4a6b, 0x8a2a2a, 0x2f6b3a, 0x6b5a2f][i % 4]),
};
