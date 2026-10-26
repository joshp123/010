// Written by AI on 2026-10-25 by model Claude Opus 5.5.
// The colours the pixel art may use. Each family is a ramp from shadow to
// highlight that shifts hue the way painters do: shadows cool, highlights warm.

// Twelve hues every 30 degrees, each at two saturations, plus neutral greys.
// Even coverage keeps brick red and water blue from collapsing to grey.
const hues = [10, 35, 60, 85, 110, 140, 170, 200, 230, 260, 290, 330];
const chromas = [0.045, 0.11];
const steps = [0.22, 0.33, 0.44, 0.55, 0.66, 0.77, 0.88];

function oklchToSrgb(l, c, hDegrees) {
  const h = hDegrees * Math.PI / 180;
  const a = c * Math.cos(h), b = c * Math.sin(h);
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.2914855480 * b;
  const L = l_ ** 3, M = m_ ** 3, S = s_ ** 3;
  const linear = [
    4.0767416621 * L - 3.3077115913 * M + 0.2309699292 * S,
    -1.2684380046 * L + 2.6097574011 * M - 0.3413193965 * S,
    -0.0041960863 * L - 0.7034186147 * M + 1.7076147010 * S,
  ];
  return linear.map((v) => {
    const clamped = Math.min(1, Math.max(0, v));
    return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055;
  });
}

export function buildPalette() {
  const colours = [];
  for (const hue of hues) {
    for (const chroma of chromas) {
      steps.forEach((lightness, index) => {
        const t = index / (steps.length - 1);
        // Painters' ramp: less saturated at the extremes, cooler in shadow.
        const c = chroma * (0.6 + 0.4 * Math.sin(Math.PI * t));
        colours.push(oklchToSrgb(lightness, c, hue + (t - 0.5) * -16));
      });
    }
  }
  // Neutrals: warm greys (brick dust, paving) and cool greys (concrete,
  // asphalt, steel, glass), finer steps than the colour ramps.
  const neutralSteps = [0.12, 0.2, 0.28, 0.36, 0.44, 0.52, 0.6, 0.68, 0.76, 0.84, 0.91, 0.97];
  for (const lightness of neutralSteps) colours.push(oklchToSrgb(lightness, 0.01, 75));
  for (const lightness of neutralSteps) colours.push(oklchToSrgb(lightness, 0.012, 250));
  return colours;
}

// Base colours for the ground surface classes in pipeline/README.md.
// These are drawing choices; which class each pixel has comes from BGT.
// Values from tools/measure-palette.py on tiny.london's day tiles
// (renders/reference/tiny-london-palette.json): roads a neutral 0.28, paving
// a cool neutral 0.57, vegetation a deep green, water a muted slate blue.
export const surfaceClassColours = {
  0: [0.50, 0.50, 0.49], // unknown
  1: [0.30, 0.31, 0.32], // carriageway
  2: [0.55, 0.27, 0.24], // cycle path, red asphalt
  3: [0.58, 0.575, 0.565], // pavement
  4: [0.36, 0.365, 0.37], // parking
  5: [0.42, 0.40, 0.38], // tram track bed
  6: [0.27, 0.42, 0.20], // grass
  7: [0.19, 0.33, 0.15], // shrubs
  8: [0.35, 0.45, 0.51], // water
  9: [0.56, 0.50, 0.40], // unpaved
  10: [0.53, 0.525, 0.515], // paved yard or square
  11: [0.45, 0.44, 0.43], // building footprint
  12: [0.47, 0.465, 0.46], // bridge deck
  13: [0.40, 0.39, 0.38], // quay wall
  14: [0.40, 0.37, 0.34], // train or metro track bed
  15: [0.52, 0.515, 0.505], // traffic island
  16: [0.42, 0.39, 0.35], // rail yard
};
