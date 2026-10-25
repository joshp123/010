import * as THREE from 'three';
import { crownPositions, crownIndices } from './crown-structured-contours.js';

// Interpret the municipality's generic crown envelopes; never change source
// instance placement, diameter, height or orientation. This is illustrated
// foliage architecture, not measured branches or a species identification.
const bark = new THREE.Color('#6a5846');

function treePart(mesh) {
  let parent = mesh;
  while (parent && !parent.batchTable) parent = parent.parent;
  try { return parent?.batchTable.getDataFromId(0)?.attributes?.tree_part; } catch { return null; }
}

export function createCrownGeometry(source) {
  source.computeBoundingBox();
  const size=source.boundingBox.getSize(new THREE.Vector3()),centre=source.boundingBox.getCenter(new THREE.Vector3());
  const geometry=new THREE.BufferGeometry();
  const coordinates=Float32Array.from(crownPositions),positions=new Float32Array(coordinates.length);
  // The source proxy constrains the occupied envelope. The connected crown
  // hierarchy comes from the registered model drawing, not its balloon profile.
  positions.set(coordinates);
  geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
  geometry.computeBoundingBox();
  const illustratedSize=geometry.boundingBox.getSize(new THREE.Vector3()),illustratedCentre=geometry.boundingBox.getCenter(new THREE.Vector3());
  for(let i=0;i<positions.length;i+=3) {
    positions[i]=(positions[i]-illustratedCentre.x)/illustratedSize.x*size.x+centre.x;
    positions[i+1]=(positions[i+1]-illustratedCentre.y)/illustratedSize.y*size.y+centre.y;
    positions[i+2]=(positions[i+2]-illustratedCentre.z)/illustratedSize.z*size.z+centre.z;
  }
  geometry.setIndex(crownIndices);
  const colors=new Float32Array(positions.length);
  const upperPigment=new THREE.Color('#657b45'),lowerPigment=new THREE.Color('#354a2d');
  const pigment=new THREE.Color();
  for(let i=0;i<coordinates.length;i+=3) {
    const upperMass=THREE.MathUtils.smoothstep(coordinates[i+1],-.20,.20);
    pigment.copy(lowerPigment).lerp(upperPigment,upperMass).toArray(colors,i);
  }
  geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
  geometry.computeVertexNormals();geometry.computeBoundingBox();geometry.computeBoundingSphere();
  geometry.userData={...source.userData,vegetationInterpretation:'Source-constrained connected crown contours, broad upper mass, unequal shoulders and narrower irregular lower volume within exact inventory envelope; common city illumination',preserveTextureProjection:false};
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
          material.map = null;
          material.color.set('#ffffff');
          material.roughness = 1;
          material.metalness = 0;
          // The common directional/ambient city light draws the connected upper
          // canopy and lower shadow. No repeated paint islands or unlit overlay.
          material.onBeforeCompile = (shader, renderer) => {
            sourceMaterial.onBeforeCompile(shader, renderer);
            shader.fragmentShader=shader.fragmentShader.replace('#include <opaque_fragment>', `
              float crownPigment=max(dot(diffuseColor.rgb,vec3(.2126,.7152,.0722)),.001);
              float crownIllumination=dot(outgoingLight,vec3(.2126,.7152,.0722))/crownPigment;
              float crownValue=.42+.26*smoothstep(.38,.43,crownIllumination)+.32*smoothstep(.68,.73,crownIllumination);
              outgoingLight=mix(outgoingLight,diffuseColor.rgb*crownValue,.85*(1.0-cityNight));
              float crownFacing=abs(dot(normalize(normal),normalize(vViewPosition)));
              float crownContour=smoothstep(0.0,max(fwidth(crownFacing)*1.5,.035),crownFacing);
              outgoingLight*=mix(.48,1.0,crownContour);
              #include <opaque_fragment>
            `);
          };
          material.customProgramCacheKey = () => sourceMaterial.customProgramCacheKey() + '-drawn-crown-hierarchy-shared-light-v4';
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
