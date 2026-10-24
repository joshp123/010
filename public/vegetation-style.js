import * as THREE from 'three';

// Interpret the municipality's generic crown envelopes; never change source
// instance placement, diameter, height or orientation. This is illustrated
// foliage architecture, not measured branches or a species identification.
const bark = new THREE.Color('#6a5846');

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
  const profile = crownProfile(source), positions = [], colors = [], indices = [];
  const rings = 24, sectors = 64;
  const dark = new THREE.Color('#324b30'), body = new THREE.Color('#486338'), light = new THREE.Color('#607943');
  // A connected, scalloped canopy with painted masses. All silhouette changes
  // stay inside the retained inventory prototype, never its instance placement.
  for (let ring = 0; ring <= rings; ring++) for (let sector = 0; sector <= sectors; sector++) {
    const y = ring / rings, angle = sector / sectors * Math.PI * 2;
    const lobes = .88 + .08 * Math.cos(angle * 5 + y * 2) + .04 * Math.cos(angle * 9 - y * 3);
    const radius = Math.min(.5, profile.radius(y)) * lobes * Math.pow(Math.max(0, Math.sin(Math.PI * y)), .32);
    const x = Math.cos(angle) * radius, z = Math.sin(angle) * radius;
    const upperMass = 1 - ((x + .16) / .50) ** 2 - ((y - .73) / .31) ** 2 - ((z + .10) / .52) ** 2;
    const sideMass = .8 - ((x - .20) / .32) ** 2 - ((y - .57) / .27) ** 2 - ((z + .21) / .43) ** 2;
    const shade = dark.clone().lerp(body, THREE.MathUtils.smoothstep(y - z * .22, .22, .28));
    shade.lerp(light, THREE.MathUtils.smoothstep(Math.max(upperMass, sideMass), .30, .38));
    positions.push(x, y, z); colors.push(shade.r, shade.g, shade.b);
  }
  for (let ring = 0; ring < rings; ring++) for (let sector = 0; sector < sectors; sector++) {
    const a = ring * (sectors + 1) + sector, b = a + 1, c = a + sectors + 1, d = c + 1;
    indices.push(a, c, b, b, c, d);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeBoundingBox();
  const ownBox = geometry.boundingBox.clone(), ownSize = ownBox.getSize(new THREE.Vector3()), p = geometry.getAttribute('position');
  for (let i = 0; i < p.count; i++) for (let axis = 0; axis < 3; axis++) {
    p.setComponent(i, axis, profile.box.min.getComponent(axis) + (p.getComponent(i, axis) - ownBox.min.getComponent(axis)) / ownSize.getComponent(axis) * profile.size.getComponent(axis));
  }
  geometry.computeVertexNormals();
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData = { ...source.userData, vegetationInterpretation: 'Joined drawn canopy masses and broad olive shading within the original inventory envelope; no inferred branches, species or new tree positions' };
  return geometry;
}

export function createVegetationStyle() {
  const models = new Map(), geometries = new Map(), canopyMaterials = new Map();
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
      const sourceMaterial = mesh.material;
      let canopyMaterial;
      if (part === 'kruin') {
        canopyMaterial = canopyMaterials.get(sourceMaterial);
        if (!canopyMaterial) {
          const material = sourceMaterial.clone();
          material.flatShading = false;
          material.onBeforeCompile = shader => {
            sourceMaterial.onBeforeCompile(shader);
            shader.fragmentShader = shader.fragmentShader.replace('#include <color_fragment>', `#include <color_fragment>
              float canopyFacing = abs(dot(normalize(vNormal), normalize(vViewPosition)));
              diffuseColor.rgb = mix(vec3(0.025, 0.042, 0.025), diffuseColor.rgb, smoothstep(0.04, 0.30, canopyFacing));
            `);
            shader.fragmentShader = shader.fragmentShader.replace('#include <opaque_fragment>', `
              outgoingLight = mix(outgoingLight, diffuseColor.rgb, 0.90 * (1.0 - cityNight));
              #include <opaque_fragment>
            `);
          };
          material.customProgramCacheKey = () => '010-drawn-canopy-masses-v1';
          canopyMaterial = { material, references: 0 };
          canopyMaterials.set(sourceMaterial, canopyMaterial);
        }
        canopyMaterial.references++;
        mesh.material = canopyMaterial.material;
      }
      record.references++; records.push({ mesh, record, sourceMaterial, canopyMaterial }); mesh.geometry = record.geometry;
      if (part === 'kruin') crowns += mesh.count; else trunks += mesh.count;
    });
    models.set(model, records);
  }
  function removeModel(model) {
    for (const { mesh, record, sourceMaterial, canopyMaterial } of models.get(model) || []) {
      mesh.geometry = record.source;
      mesh.material = sourceMaterial;
      if (canopyMaterial && --canopyMaterial.references === 0) {
        canopyMaterial.material.dispose(); canopyMaterials.delete(sourceMaterial);
      }
      if (--record.references === 0) { record.geometry.dispose(); geometries.delete(record.source); }
    }
    models.delete(model);
  }
  function dispose() { for (const model of [...models.keys()]) removeModel(model); }
  return { addModel, removeModel, dispose, diagnostics: () => ({ models: models.size, interpretedPrototypes: geometries.size, sourceCrownInstancesProcessed: crowns, sourceTrunkInstancesProcessed: trunks }) };
}
