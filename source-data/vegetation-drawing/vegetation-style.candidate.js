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

// Model-drawn orthographic fields are projected onto the original municipal
// prototype triangles. Neither envelope nor source instance transform changes.
const crownPaint = new THREE.TextureLoader().load('./data/vegetation-drawing/crown-fields.png');
crownPaint.colorSpace = THREE.SRGBColorSpace;
crownPaint.magFilter = THREE.NearestFilter;
crownPaint.minFilter = THREE.LinearMipmapLinearFilter;
export function createCrownGeometry(source) {
  source.computeBoundingBox();
  const geometry=source.clone(), positions=geometry.getAttribute('position');
  const size=source.boundingBox.getSize(new THREE.Vector3()), centre=source.boundingBox.getCenter(new THREE.Vector3());
  const coordinates=new Float32Array(positions.count*3), colours=new Float32Array(positions.count*3).fill(1);
  const point=new THREE.Vector3();
  for(let i=0;i<positions.count;i++) point.fromBufferAttribute(positions,i).sub(centre).divide(size).toArray(coordinates,i*3);
  geometry.setAttribute('canopyCoordinates',new THREE.BufferAttribute(coordinates,3));
  geometry.setAttribute('color',new THREE.BufferAttribute(colours,3));
  if(!geometry.getAttribute('normal')) geometry.computeVertexNormals();
  geometry.computeBoundingBox(); geometry.computeBoundingSphere();
  geometry.userData={...source.userData, vegetationInterpretation:'Model-drawn foliage fields on unchanged municipal prototype triangles; inventory dimensions and placement retained', preserveTextureProjection:true};
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
            shader.vertexShader = 'attribute vec3 canopyCoordinates; varying vec3 crownPosition; varying vec3 crownNormal;\n'+shader.vertexShader;
            shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\ncrownPosition=canopyCoordinates; crownNormal=objectNormal;');
            shader.fragmentShader = `uniform sampler2D crownFields; varying vec3 crownPosition; varying vec3 crownNormal;
              vec3 crownField(float index, vec2 coordinates) {
                vec2 cell=vec2(mod(index,3.0),floor(index/3.0));
                vec2 uv=(cell+coordinates*(420.0/512.0)+.5)/vec2(3.0,2.0);
                uv.y=1.0-uv.y;
                return texture2D(crownFields,uv).rgb;
              }
            `+shader.fragmentShader;
            shader.fragmentShader=shader.fragmentShader.replace('#include <map_fragment>', `
              vec3 crownDirection=normalize(crownNormal);
              vec3 crownWeights=pow(abs(crownDirection),vec3(4.0));
              crownWeights/=max(dot(crownWeights,vec3(1.0)),.0001);
              vec3 crownX=crownField(crownDirection.x>0.0?2.0:3.0,vec2(crownDirection.x>0.0?-crownPosition.z:crownPosition.z,-crownPosition.y));
              vec3 crownY=crownField(crownDirection.y>0.0?4.0:5.0,vec2(crownPosition.x,crownDirection.y>0.0?crownPosition.z:-crownPosition.z));
              vec3 crownZ=crownField(crownDirection.z>0.0?0.0:1.0,vec2(crownDirection.z>0.0?crownPosition.x:-crownPosition.x,-crownPosition.y));
              diffuseColor.rgb*=crownX*crownWeights.x+crownY*crownWeights.y+crownZ*crownWeights.z;
            `);
          };
          material.customProgramCacheKey = () => sourceMaterial.customProgramCacheKey() + '-source-bound-foliage-fields-v2';
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
