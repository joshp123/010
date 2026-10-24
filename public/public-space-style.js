// Written by AI, GPT-6, 2026-10-24.
// Source footprints and material classes are measured; paint texture and the
// narrow boundary ink are illustration, not invented curbs, joints or markings.
import * as THREE from 'three';

export function publicSpaceClass(attributes = {}, preparedKind = '') {
  const type = String(attributes.KLASSE_IMG || '').toLowerCase();
  const physical = String(attributes.FYSIEKVK || '').toLowerCase();
  const purpose = String(attributes.FUNCTIE || attributes.KLASSE || '').toLowerCase();
  if (type.includes('water') || preparedKind === 'water') return 5;
  if (type.startsWith('begroeid') || /gras|groen|struik|bos|tuin/.test(physical) || preparedKind === 'green') return 4;
  if (/zand/.test(physical) || preparedKind === 'sand') return 6;
  if (type.includes('pand') || /muur|kade|damwand/.test(purpose)) return 0;
  if (/gesloten/.test(physical) || preparedKind === 'closed-paving') return 1;
  if (/open verharding/.test(physical) || preparedKind === 'open-paving') return 3;
  // Prepared road/path classification does not establish its surfacing material.
  return 0;
}

function attributesFor(mesh, id) {
  let parent = mesh;
  while (parent && !parent.batchTable) parent = parent.parent;
  try { return parent?.batchTable.getDataFromId(id)?.attributes || {}; } catch { return {}; }
}

export function preparePublicSpaceGeometry(mesh) {
  const geometry = mesh.geometry, position = geometry?.getAttribute('position');
  if (!position || geometry.userData.publicSpacePrepared) return null;
  const batch = geometry.getAttribute('_batchid');
  const classes = new Float32Array(position.count), records = new Map();
  const record = id => {
    if (!records.has(id)) {
      const attributes = attributesFor(mesh, id);
      records.set(id, { surface: publicSpaceClass(attributes, mesh.userData.surfaceKind),
        key: [attributes.KLASSE_IMG, attributes.FUNCTIE, attributes.FYSIEKVK].join('|') });
    }
    return records.get(id);
  };
  for (let i = 0; i < position.count; i++) classes[i] = record(batch?.getX(i) || 0).surface;
  geometry.setAttribute('_surfaceClass', new THREE.BufferAttribute(classes, 1));
  geometry.userData.publicSpacePrepared = true;
  // Boundary extraction uses the retained triangle topology. Shared geometric
  // edges are compared across source features; internal triangulation and tile
  // perimeters do not become decorative lines. No new geographic objects.
  if (!batch) return null;
  const index = geometry.index, edges = new Map();
  const vertexKey = i => [position.getX(i), position.getY(i), position.getZ(i)].map(n => Math.round(n * 1000)).join(',');
  const keys = Array.from({length:position.count}, (_,i) => vertexKey(i));
  const count = index?.count ?? position.count;
  for (let i = 0; i < count; i += 3) {
    const triangle = [0,1,2].map(j => index ? index.getX(i+j) : i+j);
    const r = record(batch.getX(triangle[0]));
    for (let j = 0; j < 3; j++) {
      const a=triangle[j], b=triangle[(j+1)%3], c=triangle[(j+2)%3];
      const key = keys[a]<keys[b] ? `${keys[a]}/${keys[b]}` : `${keys[b]}/${keys[a]}`;
      const entry = edges.get(key);
      if (!entry) edges.set(key, {a,b,c,record:r,count:1,different:false});
      else { entry.count++; entry.different ||= entry.record.key !== r.key; entry.other = r; }
    }
  }
  const vertices=[], colors=[], batchValues=[], surfaceValues=[], sourceColor=geometry.getAttribute('color');
  const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3(),inward=new THREE.Vector3(),edge=new THREE.Vector3();
  let boundaries=0;
  for (const item of edges.values()) {
    // Different source pavement/vegetation/shore footprints only. Unknown walls
    // and buildings are omitted, and identical material splits remain invisible.
    if (item.count!==2 || !item.different || !item.record.surface || !item.other?.surface) continue;
    if (item.record.surface===item.other.surface && item.record.key===item.other.key) continue;
    a.fromBufferAttribute(position,item.a); b.fromBufferAttribute(position,item.b); c.fromBufferAttribute(position,item.c);
    edge.subVectors(b,a); const length=edge.length(); if(length<.02) continue; edge.divideScalar(length);
    inward.subVectors(c,a).addScaledVector(edge,-inward.dot(edge));
    const altitude=inward.length(); if(altitude<.015) continue;
    inward.multiplyScalar(Math.min(.16,altitude*.35)/altitude);
    const aa=a.clone().add(inward),bb=b.clone().add(inward);
    for (const v of [a,b,aa,b,bb,aa]) {
      vertices.push(v.x,v.y,v.z); batchValues.push(batch.getX(item.a)); surfaceValues.push(item.record.surface);
      const factor=.49; colors.push((sourceColor?.getX(item.a)??.3)*factor,(sourceColor?.getY(item.a)??.3)*factor,(sourceColor?.getZ(item.a)??.3)*factor);
    }
    boundaries++;
  }
  if (!vertices.length) return null;
  const border=new THREE.BufferGeometry();
  border.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  border.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
  border.setAttribute('_batchid',new THREE.Float32BufferAttribute(batchValues,1));
  border.setAttribute('_surfaceClass',new THREE.Float32BufferAttribute(surfaceValues,1));
  border.computeVertexNormals(); border.computeBoundingSphere();
  border.userData={sourceBoundarySegments:boundaries,illustration:'16 cm maximum painted seam inside exact surveyed adjacent surface boundaries; no curb geometry'};
  return border;
}

export function applyPublicSpaceMaterial(material) {
  if (material.userData.publicSpaceStyle) return;
  material.userData.publicSpaceStyle=true;
  material.defaultAttributeValues={...material.defaultAttributeValues,_surfaceClass:[0]};
  const compile=material.onBeforeCompile, key=material.customProgramCacheKey();
  material.onBeforeCompile=function(shader,renderer) {
    compile.call(this,shader,renderer);
    shader.vertexShader='attribute float _surfaceClass; varying float spaceClass;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\n spaceClass=_surfaceClass;');
    shader.fragmentShader='varying float spaceClass;\n'+shader.fragmentShader;
    // Material texture has a real metre scale and is integrated out before it
    // becomes subpixel. It claims no brick pattern, road paint or tidal state.
    shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>',`#include <color_fragment>
      vec2 spaceXY=cityWorldPosition.xz;
      float spaceFootprint=max(length(dFdx(spaceXY)),length(dFdy(spaceXY)));
      float spaceBrush=sin(spaceXY.x*.31+sin(spaceXY.y*.17)*1.7)*sin(spaceXY.y*.23-spaceXY.x*.07);
      float spaceBrushVisible=1.0-smoothstep(.6,2.2,spaceFootprint);
      float spaceWater=max(step(4.5,spaceClass)*step(spaceClass,5.5),step(vColor.r*1.13,vColor.g)*step(vColor.r*1.10,vColor.b)*step(vColor.b,vColor.g*1.08));
      if(spaceClass>0.5 && spaceWater<.5) {
        float spaceTexture=spaceClass>3.5 ? .055 : .018;
        diffuseColor.rgb*=1.0+spaceBrush*spaceTexture*spaceBrushVisible;
      }
      if(spaceWater>.5) {
        // Restrained painted wavelets. No boats, wakes or geographically false
        // shore features; measured water footprints remain the sole mask.
        vec2 spaceWave=vec2(spaceXY.x*.21+spaceXY.y*.10,spaceXY.y*.70-spaceXY.x*.04);
        float spaceRow=floor(spaceWave.y);
        float spaceDash=step(.68,cityHash(vec2(floor(spaceWave.x),spaceRow)));
        float spaceStroke=1.0-smoothstep(.07,.16+spaceFootprint*.35,abs(fract(spaceWave.y)-.5));
        float spaceDashEnd=smoothstep(.08,.25,fract(spaceWave.x))*(1.0-smoothstep(.68,.92,fract(spaceWave.x)));
        float spaceWaves=spaceStroke*spaceDash*spaceDashEnd*(1.0-smoothstep(1.0,5.0,spaceFootprint));
        diffuseColor.rgb=mix(diffuseColor.rgb,diffuseColor.rgb*vec3(1.18,1.12,1.10),spaceWaves*.7);
        diffuseColor.rgb*=1.0+.018*sin(spaceXY.x*.027+spaceXY.y*.019);
      }
    `);
  };
  material.customProgramCacheKey=()=>key+'-source-public-space-v2';
}

export function createPublicSpaceStyle({material,applyCutaway=()=>{}}={}) {
  const borders=new Map();
  const borderMaterial=material?.clone() || new THREE.MeshStandardMaterial({vertexColors:true,roughness:1,side:THREE.DoubleSide});
  // Cloning a Three material does not copy its custom compile function.
  if(material){borderMaterial.defaultAttributeValues={...material.defaultAttributeValues};borderMaterial.onBeforeCompile=material.onBeforeCompile;borderMaterial.customProgramCacheKey=material.customProgramCacheKey;}
  borderMaterial.polygonOffset=true; borderMaterial.polygonOffsetFactor=-1; borderMaterial.polygonOffsetUnits=-1;
  if(!material) applyCutaway(borderMaterial);
  function addModel(model){
    if(borders.has(model))return;
    const pending=[];
    model.traverse(mesh=>{if(mesh.isMesh){const geometry=preparePublicSpaceGeometry(mesh);if(geometry)pending.push({mesh,geometry});}});
    const created=[];
    for(const {mesh,geometry} of pending){const border=new THREE.Mesh(geometry,borderMaterial);border.name='Surveyed surface boundary illustration';border.receiveShadow=true;border.renderOrder=mesh.renderOrder+1;mesh.add(border);created.push(border);}
    borders.set(model,created);
  }
  function removeModel(model){for(const border of borders.get(model)||[]){border.removeFromParent();border.geometry.dispose();}borders.delete(model);}
  return {addModel,removeModel,dispose(){for(const model of [...borders.keys()])removeModel(model);borderMaterial.dispose();},diagnostics(){return {models:borders.size,boundarySegments:[...borders.values()].flat().reduce((n,b)=>n+b.geometry.userData.sourceBoundarySegments,0)};}};
}
