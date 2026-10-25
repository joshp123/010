import * as THREE from 'three';
import { crownPositions, crownCoordinates, crownIndices } from './crown-isometric-hull.js';

// Interpret the municipality's generic crown envelopes; never change source
// instance placement, diameter, height or orientation. This is illustrated
// foliage architecture, not measured branches or a species identification.
const bark = new THREE.Color('#6a5846');

function treePart(mesh) {
  let parent = mesh;
  while (parent && !parent.batchTable) parent = parent.parent;
  try { return parent?.batchTable.getDataFromId(0)?.attributes?.tree_part; } catch { return null; }
}

// Registered whole-crown fields colour one reconstructed volume.
// Original prototype envelopes and source instance transforms remain exact.
const crownPaint = new THREE.TextureLoader().load('./data/vegetation-drawing/crown-fields.png');
crownPaint.colorSpace = THREE.SRGBColorSpace;
crownPaint.magFilter = THREE.NearestFilter;
crownPaint.minFilter = THREE.LinearMipmapLinearFilter;
export function createCrownGeometry(source) {
  source.computeBoundingBox();
  const size=source.boundingBox.getSize(new THREE.Vector3()),centre=source.boundingBox.getCenter(new THREE.Vector3());
  const geometry=new THREE.BufferGeometry();
  const coordinates=Float32Array.from(crownPositions),positions=new Float32Array(coordinates.length);
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
  geometry.setAttribute('canopyCoordinates',new THREE.BufferAttribute(Float32Array.from(crownCoordinates),3));
  geometry.setAttribute('color',new THREE.BufferAttribute(new Float32Array(positions.length).fill(1),3));
  geometry.computeVertexNormals();geometry.computeBoundingBox();geometry.computeBoundingSphere();
  geometry.userData={...source.userData,vegetationInterpretation:'Nine-view model-drawn connected crown volume within exact inventory envelope, coherent whole-crown view projection',preserveTextureProjection:true};
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
          material.map = crownPaint;
          material.onBeforeCompile = (shader, renderer) => {
            sourceMaterial.onBeforeCompile(shader, renderer);
            shader.uniforms.crownFields = {value:crownPaint};
            shader.vertexShader = 'attribute vec3 canopyCoordinates; varying vec3 crownPosition; varying vec3 crownViewDirection;\n'+shader.vertexShader;
            shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>
              crownPosition=canopyCoordinates;
              mat4 crownViewTransform=modelViewMatrix;
              #ifdef USE_INSTANCING
                crownViewTransform*=instanceMatrix;
              #endif
              crownViewDirection=normalize(vec3(crownViewTransform[0][2],crownViewTransform[1][2],crownViewTransform[2][2]));
            `);
            shader.fragmentShader = `uniform sampler2D crownFields; varying vec3 crownPosition; varying vec3 crownViewDirection;
              vec3 crownField(float index, vec3 position) {
                float angle=index*.7853981634;
                float elevation=index>7.5?1.5707963268:.6154797087;
                vec3 right=vec3(cos(angle),0.0,-sin(angle));
                vec3 up=vec3(-sin(angle)*sin(elevation),cos(elevation),-cos(angle)*sin(elevation));
                vec2 projected=vec2(dot(position,right),-dot(position,up));
                vec2 cell=vec2(mod(index,3.0),floor(index/3.0));
                vec2 uv=(cell+projected*(320.0/512.0)+.5)/3.0;
                uv.y=1.0-uv.y;
                return texture2D(crownFields,uv).rgb;
              }
            `+shader.fragmentShader;
            shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>', `
              vec3 viewDirection=normalize(crownViewDirection);
              float angle=mod(atan(viewDirection.x,viewDirection.z)+6.2831853072,6.2831853072)/.7853981634;
              float first=floor(angle), fraction=fract(angle);
              vec3 paint=mix(crownField(first,crownPosition),crownField(mod(first+1.0,8.0),crownPosition),smoothstep(.2,.8,fraction));
              float topWeight=smoothstep(.82,.98,viewDirection.y);
              diffuseColor.rgb*=mix(paint,crownField(8.0,crownPosition),topWeight);
            `);
          };
          material.customProgramCacheKey = () => sourceMaterial.customProgramCacheKey() + '-source-bound-whole-crown-isometric-v1';
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
