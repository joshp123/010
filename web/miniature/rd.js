// Written by AI on 2026-10-25 by model Claude Opus 5.5.
// WGS84 <-> RD New with the published polynomial approximation
// (Schreutelkamp and Strang van Hees). Accurate to about a metre, which is
// enough for links and search; the scene itself is built with exact grids.

const X0 = 155000, Y0 = 463000, PHI0 = 52.15517440, LAM0 = 5.38720621;

const toRdP = [[0, 1, 190094.945], [1, 1, -11832.228], [2, 1, -114.221], [0, 3, -32.391], [1, 0, -0.705], [3, 1, -2.340], [1, 3, -0.608], [0, 2, -0.008], [2, 3, 0.148]];
const toRdQ = [[1, 0, 309056.544], [0, 2, 3638.893], [2, 0, 73.077], [1, 2, -157.984], [3, 0, 59.788], [0, 1, 0.433], [2, 2, -6.439], [1, 1, -0.032], [0, 4, 0.092], [1, 4, -0.054]];
const toWgsK = [[0, 1, 3235.65389], [2, 0, -32.58297], [0, 2, -0.24750], [2, 1, -0.84978], [0, 3, -0.06550], [2, 2, -0.01709], [1, 0, -0.00738], [4, 0, 0.00530], [2, 3, -0.00039], [4, 1, 0.00033], [1, 1, -0.00012]];
const toWgsL = [[1, 0, 5260.52916], [1, 1, 105.94684], [1, 2, 2.45656], [3, 0, -0.81885], [1, 3, 0.05594], [3, 1, -0.05607], [0, 1, 0.01199], [3, 2, -0.00256], [1, 4, 0.00128], [0, 2, 0.00022], [2, 0, -0.00022], [5, 0, 0.00026]];

export function rdFromWgs84(lat, lon) {
  const dPhi = 0.36 * (lat - PHI0), dLam = 0.36 * (lon - LAM0);
  let x = X0, y = Y0;
  for (const [p, q, r] of toRdP) x += r * dPhi ** p * dLam ** q;
  for (const [p, q, s] of toRdQ) y += s * dPhi ** p * dLam ** q;
  return { x, y };
}

export function wgs84FromRd(x, y) {
  const dX = (x - X0) * 1e-5, dY = (y - Y0) * 1e-5;
  let lat = PHI0, lon = LAM0;
  for (const [p, q, k] of toWgsK) lat += (k * dX ** p * dY ** q) / 3600;
  for (const [p, q, l] of toWgsL) lon += (l * dX ** p * dY ** q) / 3600;
  return { lat, lon };
}
