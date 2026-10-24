// CPU ray render of actual section/vehicle geometry and the production mask.
// Synthetic occluders test geometry only; this is not city visual acceptance.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source=(await readFile(process.env.METRO_SOURCE || new URL('../public/transit-view.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
const {createTransitView}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const sourceFixture=process.env.METRO_SOURCE_FIXTURE?JSON.parse(await readFile(process.env.METRO_SOURCE_FIXTURE,'utf8')):null;
const groundQueryMeshes=(sourceFixture?.features||[]).filter(feature=>feature.kind==='ground').map(feature=>{
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(feature.positions,3));geometry.computeBoundingSphere();
 return new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));
});
const groundRay=new THREE.Raycaster();
const view=createTransitView({project:(lat,lon,y=0)=>{
 const x=lon*111320,z=-lat*111320;let ground=0;
 if(groundQueryMeshes.length){groundRay.set(new THREE.Vector3(x,60,z),new THREE.Vector3(0,-1,0));ground=groundRay.intersectObjects(groundQueryMeshes,false)[0]?.point.y??0;}
 return new THREE.Vector3(x,ground+y,z);
}});
view.setMetroData({segments:[{id:'selected',form:'tunnel',coordinates:[[-.002,0],[.002,0]]},{id:'crossing',form:'tunnel',coordinates:[[0,-.002],[0,.002]]}]});
const camera=new THREE.OrthographicCamera(-60,60,45,-45,.1,1000);
const bearing=Number(process.env.METRO_BEARING||35)*Math.PI/180;
camera.position.set(Math.sin(bearing)*120,120/Math.sqrt(2),Math.cos(bearing)*120);camera.lookAt(0,-4,0);camera.updateMatrixWorld();
view.setView({camera,span:120,viewportHeight:300});
view.update({vehicles:[{id:'test',mode:'metro',latitude:14/111320,longitude:0,routeShape:[[[-.002,0],[.002,0]]],freshness:'fresh',sourceConnected:true}]});
view.setCutaway(true);
assert.equal(view.statistics().section.report.renderedAs,'illustrated train');
assert.equal(view.statistics().section.report.latitude,14/111320,'raw observation retained');
assert.equal(view.statistics().section.report.representedPosition.latitude,0,'route-compatible track selected instead of crossing tunnel');
assert.ok(Math.abs(view.statistics().section.report.representedPosition.offsetMetres-14)<.001);
assert.ok(view.statistics().section.geometryBounds.max[2]-view.statistics().section.geometryBounds.min[2]<=32.01,'crossing branch is not excavated');
assert.ok(view.statistics().section.segmentCount>1);
const mouthCorners=new Map();
for(const polygon of view.getSectionGeometry().mouthPolygons)for(const point of polygon.slice(0,2)){
 const key=point.toArray().map(value=>value.toFixed(4)).join(':');mouthCorners.set(key,(mouthCorners.get(key)||0)+1);
}
assert.ok([...mouthCorners.values()].every(count=>count===2),'four banks must meet in a continuous surface perimeter');
const city=new THREE.Group();
for(const [x,y,z,w,h,d] of [[0,-.5,0,200,1,200],[-26,14,5,15,28,16],[26,18,-5,15,36,16], ...(process.env.METRO_ROOF_OCCLUDER ? [[0,10,0,60,20,22]] : [])]){
 const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshBasicMaterial({color:y<0?'#79947a':'#b49d84'}));mesh.position.set(x,y,z);city.add(mesh);
}
if(process.env.METRO_SOURCE_FIXTURE){
 for(const mesh of [...city.children])city.remove(mesh);
 const fixture=sourceFixture;
 for(const feature of fixture.features){
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(feature.positions,3));geometry.computeVertexNormals();geometry.computeBoundingBox();geometry.computeBoundingSphere();
  const classification=feature.attributes?.KLASSE_IMG||'',purpose=feature.attributes?.FUNCTIE||'';
  const groundColour=classification.startsWith('Begroeid')?'#79947a':/voet/i.test(purpose)?'#c9c4b2':classification==='Pand'?'#aea99a':'#939a94';
  const mesh=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({color:feature.kind==='ground'?groundColour:'#b49d84',side:THREE.DoubleSide}));if(feature.kind!=='ground')mesh.userData.bagId=feature.id;city.add(mesh);
 }
}
city.updateMatrixWorld(true);view.group.updateMatrixWorld(true);
let cityCut=null;
if(process.env.METRO_GHOST){
 const cutSource=(await readFile(new URL('../public/metro-city-cut.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
 const {createMetroCityCut}=await import(`data:text/javascript;base64,${Buffer.from(cutSource).toString('base64')}`);
 cityCut=createMetroCityCut();cityCut.update(city.children.filter(mesh=>mesh.position.y>0||mesh.userData.bagId),view.getSectionGeometry());cityCut.group.updateMatrixWorld(true);
}
const mask=view.getCutaway();
function removed(point){const b=mask.bounds,p=mask.projection,t=mask.texture.image;const x=Math.floor((point.x-point.y*p.x-b.x)/b.z*t.width),z=Math.floor((point.z-point.y*p.y-b.y)/b.w*t.height);return x>=0&&z>=0&&x<t.width&&z<t.height&&t.data[z*t.width+x]>127;}
const ray=new THREE.Raycaster();ray.params.Line.threshold=.12;const width=Number(process.env.METRO_RENDER_WIDTH||320),height=Math.round(Number(process.env.METRO_RENDER_WIDTH||320)*.75),pixels=Buffer.alloc(width*height*3);let trainPixels=0,clearedBuildingPixels=0,unsupportedOpeningPixels=0;
for(let y=0;y<height;y++)for(let x=0;x<width;x++){
 ray.setFromCamera(new THREE.Vector2((x+.5)/width*2-1,1-(y+.5)/height*2),camera);
 const cityHits=ray.intersectObject(city,true), visibleCity=cityHits.filter(hit=>!removed(hit.point)&&!(hit.object.geometry.getAttribute('_metroExcised')?.getX(hit.face.a)>.5));
 const transitHits=ray.intersectObject(view.group,true).filter(hit=>!hit.object.isInstancedMesh||hit.instanceId<hit.object.count);
 if(cityHits.some(hit=>removed(hit.point))&&!transitHits.length)unsupportedOpeningPixels++;
 const ghostHits=cityCut?ray.intersectObject(cityCut.group,true):[];
 const hit=[...visibleCity,...transitHits].sort((a,b)=>a.distance-b.distance)[0];
 let colour=new THREE.Color('#c5c2ad');
 if(hit){colour=hit.object.material.color.clone();if(hit.object.name==='Observed metro'){colour.set('#e2e3ce');trainPixels++;}if(hit.object.name==='metro roofs'){colour.set('#e2e3ce');trainPixels++;}if(hit.face){
  const colours=hit.object.geometry.getAttribute('color'),positions=hit.object.geometry.getAttribute('position');
  if(colours&&hit.object.material.vertexColors){
   const bary=THREE.Triangle.getBarycoord(hit.object.worldToLocal(hit.point.clone()),new THREE.Vector3().fromBufferAttribute(positions,hit.face.a),new THREE.Vector3().fromBufferAttribute(positions,hit.face.b),new THREE.Vector3().fromBufferAttribute(positions,hit.face.c),new THREE.Vector3());
   const tint=new THREE.Color(0,0,0);for(const [index,weight]of [[hit.face.a,bary.x],[hit.face.b,bary.y],[hit.face.c,bary.z]])tint.add(new THREE.Color().fromBufferAttribute(colours,index).multiplyScalar(weight));colour.multiply(tint);
  }
  colour.multiplyScalar(.65+.35*Math.abs(hit.face.normal.y));
 }}
 if(cityHits.some(h=>(h.object.position.y>0||h.object.userData.bagId)&&removed(h.point)))clearedBuildingPixels++;
 if(ghostHits.length&&(!hit||ghostHits[0].distance<hit.distance))colour.lerp(new THREE.Color('#9baea1'),ghostHits[0].object.material.opacity);
 colour.convertLinearToSRGB();
 const i=(y*width+x)*3;pixels[i]=Math.round(colour.r*255);pixels[i+1]=Math.round(colour.g*255);pixels[i+2]=Math.round(colour.b*255);
}
assert.equal(unsupportedOpeningPixels,0,'aperture must not expose background beyond actual section faces');
assert.ok(trainPixels>150,`train must have legible projected area: ${trainPixels}`);
assert.ok(clearedBuildingPixels>150,`building pixels must be removed by projected mask: ${clearedBuildingPixels}`);
const path=process.argv[2]||'/tmp/metro-occlusion.ppm';await writeFile(path,Buffer.concat([Buffer.from(`P6\n${width} ${height}\n255\n`),pixels]));
console.log(JSON.stringify({path,trainPixels,clearedBuildingPixels,unsupportedOpeningPixels,cityCut:cityCut?.diagnostics()??null,representedPosition:view.statistics().section.report.representedPosition}));
cityCut?.dispose();view.dispose();
