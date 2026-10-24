import * as THREE from 'three';

// Interpret the municipality's generic crown envelopes; never change source
// instance placement, diameter, height or orientation. This is illustrated
// foliage architecture, not measured branches or a species identification.
const foliage = ['#3c5438', '#526b43', '#637c4e', '#768b59'].map(value => new THREE.Color(value));
const bark = new THREE.Color('#6a5846');
const number = (seed, n) => { const x = Math.sin(seed * 17.31 + n * 91.77) * 43758.5453; return x - Math.floor(x); };

function treePart(mesh) {
  let parent = mesh;
  while (parent && !parent.batchTable) parent = parent.parent;
  try { return parent?.batchTable.getDataFromId(0)?.attributes?.tree_part; } catch { return null; }
}

// Source prototype cross-sections retain the distinction between narrow,
// conical, broad and spherical crowns. Interpolate maximum radial extents at
// 12 heights; this is a silhouette guide, not new botanical source data.
function crownProfile(source) {
  source.computeBoundingBox();
  const box = source.boundingBox, size = box.getSize(new THREE.Vector3()), centre = box.getCenter(new THREE.Vector3());
  const bins = Array.from({ length: 13 }, () => 0), positions = source.getAttribute('position');
  for (let i = 0; i < positions.count; i++) {
    const y = (positions.getY(i) - box.min.y) / size.y;
    const radius = Math.hypot((positions.getX(i) - centre.x) / size.x, (positions.getZ(i) - centre.z) / size.z);
    const bin = Math.min(12, Math.max(0, Math.round(y * 12)));
    bins[bin] = Math.max(bins[bin], radius);
  }
  for (let i = 0; i < bins.length; i++) if (!bins[i]) {
    let lo = i - 1, hi = i + 1;
    while (lo >= 0 && !bins[lo]) lo--;
    while (hi < bins.length && !bins[hi]) hi++;
    bins[i] = lo >= 0 && hi < bins.length ? THREE.MathUtils.lerp(bins[lo], bins[hi], (i - lo) / (hi - lo)) : bins[lo >= 0 ? lo : hi] || .5;
  }
  return { box, size, centre, radius(y) { const t = THREE.MathUtils.clamp(y, 0, 1) * 12, lo = Math.floor(t); return THREE.MathUtils.lerp(bins[lo], bins[Math.min(12, lo + 1)], t - lo); } };
}

export function createCrownGeometry(source) {
  const profile = crownProfile(source);
  const positions = [], colors = [];
  // Thin, directional sprays have real gaps and a broken edge. The former
  // overlapping solid balls produced rounded plastic highlights at every scale.
  // This is a leaf-on illustration within the municipal crown envelope, not a
  // reconstruction of individual leaves (the retained 2026 aerial is leaf-off).
  function leaf(origin, along, across, length, width, shade) {
    const base = origin.clone().addScaledVector(along, -length * .45);
    const tip = origin.clone().addScaledVector(along, length * .55);
    const left = origin.clone().addScaledVector(across, width * .5);
    const right = origin.clone().addScaledVector(across, -width * .5);
    const ridge = origin.clone().add(new THREE.Vector3(0, width * .12, 0));
    const outline = [base, left, tip, right];
    for (let edge = 0; edge < 4; edge++) {
      const triangle = [outline[edge], outline[(edge + 1) % 4], ridge];
      // Closed two-sided leaf geometry also works with the existing shared
      // shadow/depth material; no transparency or scene shader special cases.
      for (const face of [triangle, [...triangle].reverse()]) for (const point of face) {
        const y = THREE.MathUtils.clamp(point.y, 0, 1);
        const limit = Math.min(.5, profile.radius(y)), radius = Math.hypot(point.x, point.z);
        const factor = radius > limit ? limit / radius : 1;
        positions.push(point.x * factor, y, point.z * factor);
        colors.push(shade.r, shade.g, shade.b);
      }
    }
  }
  const sprays = 1150;
  for (let i = 0; i < sprays; i++) {
    const y = .035 + .93 * number(i + 1, 1);
    const angle = i * 2.39996323;
    const envelope = Math.min(.5, profile.radius(y));
    const radial = envelope * (.15 + .80 * Math.sqrt(number(i + 1, 4)));
    const centre = new THREE.Vector3(Math.cos(angle) * radial, y, Math.sin(angle) * radial);
    const direction = new THREE.Vector3(Math.cos(angle), -.25 + number(i + 1, 6) * 1.1, Math.sin(angle)).normalize();
    const across = new THREE.Vector3(-Math.sin(angle), .65 * Math.sin(i), Math.cos(angle)).normalize();
    // Each spray shares a coherent olive family, with lighter outward tips.
    const shade = foliage[Math.min(foliage.length - 1, Math.floor((y * .35 + (radial / Math.max(envelope, .01)) * .65) * foliage.length))];
    for (let j = 0; j < 5; j++) {
      const side = j % 2 ? 1 : -1, step = Math.floor(j / 2);
      const anchor = centre.clone().addScaledVector(direction, (step - 1) * .027).addScaledVector(across, side * .018);
      const axis = direction.clone().multiplyScalar(.6).addScaledVector(across, side * (.4 + number(i + j, 8))).normalize();
      const cross = new THREE.Vector3(-axis.z, -.5 + number(i + j, 9), axis.x).normalize();
      const length = (.035 + .020 * number(i + 1, 5)) * (1 - step * .08);
      leaf(anchor, axis, cross, length, length * .8, shade);
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeBoundingBox();
  // Fit the illustrated crown to the exact inventory prototype envelope, so a
  // 12 m inventory crown stays 12 m, including after instance transforms.
  const ownBox = geometry.boundingBox.clone(), ownSize = ownBox.getSize(new THREE.Vector3()), p = geometry.getAttribute('position');
  for (let i = 0; i < p.count; i++) for (let axis = 0; axis < 3; axis++) {
    p.setComponent(i, axis, profile.box.min.getComponent(axis) + (p.getComponent(i, axis) - ownBox.min.getComponent(axis)) / ownSize.getComponent(axis) * profile.size.getComponent(axis));
  }
  geometry.computeVertexNormals(); geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData = { ...source.userData, vegetationInterpretation: 'Directional leaf sprays and open gaps inside the original inventory envelope; leaf-on illustration, not surveyed leaves or branches' };
  return geometry;
}

export function createVegetationStyle() {
  const models = new Map(), geometries = new Map();
  let crowns = 0, trunks = 0;
  function addModel(model) {
    if (models.has(model)) return;
    const records = [];
    model.traverse(mesh => {
      if (!mesh.isInstancedMesh || !mesh.geometry?.getAttribute('position')) return;
      const part = treePart(mesh);
      if (part !== 'kruin' && part !== 'stam') return;
      const source = mesh.geometry;
      let record = geometries.get(source);
      if (!record) {
        let geometry;
        if (part === 'kruin') geometry = createCrownGeometry(source);
        else {
          geometry = source.clone();
          const colors = new Float32Array(source.getAttribute('position').count * 3);
          for (let i = 0; i < colors.length; i += 3) bark.toArray(colors, i);
          geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        }
        record = { source, geometry, references: 0, part }; geometries.set(source, record);
      }
      record.references++; records.push({ mesh, record }); mesh.geometry = record.geometry;
      if (part === 'kruin') crowns += mesh.count; else trunks += mesh.count;
    });
    models.set(model, records);
  }
  function removeModel(model) {
    for (const { mesh, record } of models.get(model) || []) {
      mesh.geometry = record.source;
      if (--record.references === 0) { record.geometry.dispose(); geometries.delete(record.source); }
    }
    models.delete(model);
  }
  function dispose() { for (const model of [...models.keys()]) removeModel(model); }
  return { addModel, removeModel, dispose, diagnostics: () => ({ models: models.size, interpretedPrototypes: geometries.size, sourceCrownInstancesProcessed: crowns, sourceTrunkInstancesProcessed: trunks }) };
}
