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
  for (const lightness of [0.12, 0.25, 0.38, 0.5, 0.62, 0.74, 0.86, 0.96]) colours.push(oklchToSrgb(lightness, 0.008, 80));
  return colours;
}

// Base colours for the ground surface classes in pipeline/README.md.
// These are drawing choices; which class each pixel has comes from BGT.
export const surfaceClassColours = {
  0: [0.55, 0.55, 0.52], // unknown
  1: [0.50, 0.51, 0.53], // carriageway
  2: [0.66, 0.30, 0.27], // cycle path, red asphalt
  3: [0.70, 0.68, 0.63], // pavement
  4: [0.50, 0.50, 0.50], // parking
  5: [0.47, 0.44, 0.40], // tram track bed
  6: [0.42, 0.62, 0.30], // grass
  7: [0.30, 0.48, 0.24], // shrubs
  8: [0.33, 0.53, 0.64], // water
  9: [0.72, 0.64, 0.48], // unpaved
  10: [0.63, 0.61, 0.57], // paved yard or square
  11: [0.52, 0.50, 0.48], // building footprint
  12: [0.56, 0.54, 0.50], // bridge deck
  13: [0.48, 0.46, 0.44], // quay wall
  14: [0.45, 0.41, 0.37], // train or metro track bed
  15: [0.62, 0.60, 0.56], // traffic island
  16: [0.50, 0.46, 0.40], // rail yard
};
