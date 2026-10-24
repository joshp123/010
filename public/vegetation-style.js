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
  const dark = new THREE.Color('#344d3b'), body = new THREE.Color('#5c724b'), light = new THREE.Color('#81915e');
  const masses = [
    [-.18,.42,-.08,.32,.35,.33], [.19,.45,.08,.30,.30,.30],
    [-.13,.70,.11,.28,.29,.29], [.13,.74,-.12,.26,.26,.27],
    [.02,.28,.06,.28,.25,.25], [.28,.61,.12,.21,.25,.22],
  ];
  // Connected foliage masses interpret the inventory envelope, not branches or
  // species. Their overlapping cross-sections avoid repeated vertical fluting.
  for (let ring = 0; ring <= rings; ring++) for (let sector = 0; sector <= sectors; sector++) {
    const y = ring / rings, angle = sector / sectors * Math.PI * 2;
    const nx = Math.cos(angle), nz = Math.sin(angle);
    let massRadius = 0, outerMass = masses[0];
    for (const mass of masses) {
      const [cx,cy,cz,rx,ry,rz] = mass;
      const a = nx*nx/(rx*rx)+nz*nz/(rz*rz);
      const b = -2*(nx*cx/(rx*rx)+nz*cz/(rz*rz));
      const c = cx*cx/(rx*rx)+cz*cz/(rz*rz)+(y-cy)**2/(ry*ry)-1;
      const discriminant = b*b-4*a*c;
      if (discriminant < 0) continue;
      const radius = (-b+Math.sqrt(discriminant))/(2*a);
      if (radius > massRadius) outerMass = mass;
      const overlap = Math.max(0, .07 - Math.abs(radius-massRadius)) / .07;
      massRadius = Math.max(massRadius, radius) + overlap*overlap*.0175;
    }
    const leafEdge = 1 + .045*Math.sin(angle*19+y*27)*Math.sin(y*23-angle*9);
    const radius = massRadius * Math.min(1, profile.radius(y)*2) * leafEdge;
    const x = nx * radius, z = nz * radius;
    const [,cy,,,ry] = outerMass;
    const massTop = THREE.MathUtils.smoothstep((y-cy)/ry, -.35, .65);
    const underside = THREE.MathUtils.smoothstep(y, .05, .42);
    const shade = dark.clone().lerp(body, underside);
    shade.lerp(light, massTop * .42 * underside);
    positions.push(x, y, z); colors.push(shade.r, shade.g, shade.b);
  }
  for (let ring = 0; ring < rings; ring++) for (let sector = 0; sector < sectors; sector++) {
    const a = ring * (sectors + 1) + sector, b = a + 1, c = a + sectors + 1, d = c + 1;
    indices.push(a, c, b, b, c, d);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
  geometry.setAttribute('canopyCoordinates', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setIndex(indices);
  geometry.computeBoundingBox();
  const ownBox = geometry.boundingBox.clone(), ownSize = ownBox.getSize(new THREE.Vector3()), p = geometry.getAttribute('position');
  for (let i = 0; i < p.count; i++) for (let axis = 0; axis < 3; axis++) {
    p.setComponent(i, axis, profile.box.min.getComponent(axis) + (p.getComponent(i, axis) - ownBox.min.getComponent(axis)) / ownSize.getComponent(axis) * profile.size.getComponent(axis));
  }
  geometry.computeVertexNormals();
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData = { ...source.userData, vegetationInterpretation: 'Connected shaded foliage volumes within the original inventory envelope, using shared city light; no inferred branches, species or new tree positions' };
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
          material.onBeforeCompile = (shader, renderer) => {
            sourceMaterial.onBeforeCompile(shader, renderer);
            shader.vertexShader = 'attribute vec3 canopyCoordinates; varying vec3 canopyPosition;\n' + shader.vertexShader;
            shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\ncanopyPosition = canopyCoordinates;');
            shader.fragmentShader = `
              varying vec3 canopyPosition;
              float canopyHash(vec3 p) { return fract(sin(dot(p,vec3(127.1,311.7,74.7)))*43758.5453); }
              float canopyMass(vec3 p) {
                vec3 cell=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
                return mix(mix(mix(canopyHash(cell),canopyHash(cell+vec3(1,0,0)),f.x),mix(canopyHash(cell+vec3(0,1,0)),canopyHash(cell+vec3(1,1,0)),f.x),f.y),mix(mix(canopyHash(cell+vec3(0,0,1)),canopyHash(cell+vec3(1,0,1)),f.x),mix(canopyHash(cell+vec3(0,1,1)),canopyHash(cell+vec3(1,1,1)),f.x),f.y),f.z);
              }
            ` + shader.fragmentShader;
            shader.fragmentShader = shader.fragmentShader.replace('#include <opaque_fragment>', `
              float canopyPigment = max(dot(diffuseColor.rgb, vec3(.2126,.7152,.0722)), .001);
              float canopyIllumination = dot(outgoingLight, vec3(.2126,.7152,.0722)) / canopyPigment;
              float canopyPaint = .50 + .23*smoothstep(.38,.48,canopyIllumination) + .27*smoothstep(.78,.88,canopyIllumination);
              float foliageMass = canopyMass(canopyPosition*vec3(13.0,17.0,13.0));
              float foliageShade = .82 + .15*smoothstep(.34,.43,foliageMass) + .15*smoothstep(.57,.66,foliageMass);
              canopyPaint *= foliageShade;
              outgoingLight = mix(outgoingLight, diffuseColor.rgb*canopyPaint, .95*(1.0-cityNight));
              #include <opaque_fragment>
            `);
          };
          material.customProgramCacheKey = () => sourceMaterial.customProgramCacheKey() + '-joined-painted-canopy-v4';
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
