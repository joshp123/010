import * as THREE from 'three';

// Interpret the municipality's generic crown envelopes; never change source
// instance placement, diameter, height or orientation. This is illustrated
// foliage architecture, not measured branches or a species identification.
const foliage = ['#526c49', '#648154', '#71895a', '#5b774d'].map(value => new THREE.Color(value));
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
  const positions = [], colors = [], primitive = new THREE.IcosahedronGeometry(1, 0);
  const shape = primitive.getAttribute('position');
  // Three staggered whorls and a cap give gaps, shelf shadows and an irregular
  // outline at building scale. The source's overall dimensions remain exact.
  const lobes = [{ y: .48, ring: 0, radius: .32, tall: .32, seed: 1 }];
  for (const [level, y, count, radius] of [[0, .28, 5, .225], [1, .53, 5, .235], [2, .77, 4, .18]]) {
    for (let i = 0; i < count; i++) {
      const angle = i / count * Math.PI * 2 + level * 1.1;
      lobes.push({ y: y + (number(level + 1, i) - .5) * .07, ring: profile.radius(y) * .48, angle, radius, tall: radius * .94, seed: level * 7 + i + 2 });
    }
  }
  lobes.push({ y: .9, ring: 0, radius: .14, tall: .16, seed: 26 });
  for (const lobe of lobes) {
    const angle = lobe.angle || 0, cx = Math.cos(angle) * lobe.ring, cz = Math.sin(angle) * lobe.ring;
    const shade = foliage[lobe.seed % foliage.length];
    for (let i = 0; i < shape.count; i++) {
      const a = angle + .33, sx = shape.getX(i), sz = shape.getZ(i);
      let x = cx + (sx * Math.cos(a) - sz * Math.sin(a)) * lobe.radius;
      let z = cz + (sx * Math.sin(a) + sz * Math.cos(a)) * lobe.radius;
      const y = THREE.MathUtils.clamp(lobe.y + shape.getY(i) * lobe.tall, 0, 1);
      const r = Math.hypot(x, z), limit = Math.min(.5, profile.radius(y));
      if (r > limit && r) { x *= limit / r; z *= limit / r; }
      positions.push(x, y, z); colors.push(shade.r, shade.g, shade.b);
    }
  }
  primitive.dispose();
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
  geometry.userData = { ...source.userData, vegetationInterpretation: 'Faceted crown clusters within original inventory envelope; illustrative, not surveyed leaves or branches' };
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
