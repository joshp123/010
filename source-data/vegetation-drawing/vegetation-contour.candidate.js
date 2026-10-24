import * as THREE from 'three';
import { crownPositions, crownCoordinates, crownIndices } from './crown-contour-hull.js';

// Interpret the municipality's generic crown envelopes; never change source
// instance placement, diameter, height or orientation. This is illustrated
// foliage architecture, not measured branches or a species identification.
const referenceCrownProfile=[[0.08061080068481766, 0.08060158535277355], [0.21339996543116962, 0.2133936845673925], [0.2619824744584035, 0.2619772864774077], [0.31034264710315085, 0.3103384866908065], [0.3451364936042871, 0.3451330719888884], [0.3788075823329915, 0.37880488048910393], [0.40426006513868445, 0.4042579437998057], [0.4295851560351112, 0.4295838082520998], [0.446716211737, 0.44672416136219145], [0.46384726743888866, 0.46386451447228305], [0.47656080075884366, 0.476578375876209], [0.4857111873820418, 0.4857218559809818], [0.4948615740052399, 0.49486533608575456], [0.4998615612061855, 0.4998615612061855], [0.49989591154647817, 0.49989591154647817], [0.49993026188677087, 0.49993026188677087], [0.4999646122270635, 0.4999646122270635], [0.4999989625673562, 0.4999989625673562], [0.4850496613500094, 0.4850493245021713], [0.4696337383230916, 0.4696330541372791], [0.44777484674845275, 0.44777367889560227], [0.40361257990413957, 0.4036104564591993], [0.3542107903463155, 0.3542075934280419], [0.2593743973289528, 0.25936910472829233], [0.05074552237123048, 0.050735634345943054]];
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
function sourceCrownProfile(source) {
  const position=source.getAttribute('position'), indices=source.index;
  const size=source.boundingBox.getSize(new THREE.Vector3()), centre=source.boundingBox.getCenter(new THREE.Vector3());
  const points=Array.from({length:position.count},(_,i)=>new THREE.Vector3().fromBufferAttribute(position,i).sub(centre).divide(size));
  const profile=[];
  for(let row=0;row<=24;row++) {
    const y=(row+.05)/24.1-.5;
    let x=0,z=0;
    for(let offset=0;offset<(indices?.count??position.count);offset+=3) {
      const triangle=[0,1,2].map(corner=>points[indices?indices.getX(offset+corner):offset+corner]);
      for(let edge=0;edge<3;edge++) {
        const a=triangle[edge],b=triangle[(edge+1)%3];
        if((a.y<=y&&b.y>=y)||(b.y<=y&&a.y>=y)) {
          const fraction=(y-a.y)/(b.y-a.y||1),px=a.x+(b.x-a.x)*fraction,pz=a.z+(b.z-a.z)*fraction;
          x=Math.max(x,Math.abs(px));z=Math.max(z,Math.abs(pz));
        }
      }
    }
    profile.push([Math.max(.02,x),Math.max(.02,z)]);
  }
  return profile;
}
export function createCrownGeometry(source) {
  source.computeBoundingBox();
  const size=source.boundingBox.getSize(new THREE.Vector3()),centre=source.boundingBox.getCenter(new THREE.Vector3());
  const geometry=new THREE.BufferGeometry();
  const coordinates=Float32Array.from(crownPositions),positions=new Float32Array(coordinates.length);
  const profile=sourceCrownProfile(source);
  // Preserve each municipal prototype's height profile, with the model-drawn
  // connected crown structure interpreted inside that inventory envelope.
  for(let i=0;i<coordinates.length;i+=3) {
    const y=coordinates[i+1],row=Math.min(24,Math.max(0,Math.round((y+.5)*24)));
    const reference=referenceCrownProfile[row];
    positions[i]=coordinates[i]*Math.min(2,profile[row][0]/reference[0]);
    positions[i+1]=y;
    positions[i+2]=coordinates[i+2]*Math.min(2,profile[row][1]/reference[1]);
  }
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
  geometry.userData={...source.userData,vegetationInterpretation:'Six-view model-drawn connected crown hull, fitted to source prototype profile and exact inventory envelope',preserveTextureProjection:true};
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
          material.customProgramCacheKey = () => sourceMaterial.customProgramCacheKey() + '-source-bound-foliage-contour-v1';
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
