// CPU ray render of actual section/vehicle geometry and the production mask.
// Synthetic occluders test geometry only; this is not city visual acceptance.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source=(await readFile(process.env.METRO_SOURCE || new URL('../public/transit-view.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
const {createTransitView}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const view=createTransitView({project:(lat,lon,y=0)=>new THREE.Vector3(lon*111320,y,-lat*111320)});
view.setMetroData({segments:[{id:'selected',form:'tunnel',coordinates:[[-.002,0],[.002,0]]},{id:'crossing',form:'tunnel',coordinates:[[0,-.002],[0,.002]]}]});
const camera=new THREE.OrthographicCamera(-60,60,45,-45,.1,1000);
camera.position.set(70,100,100);camera.lookAt(0,-4,0);camera.updateMatrixWorld();
view.setView({camera,span:120,viewportHeight:300});
view.update({vehicles:[{id:'test',mode:'metro',latitude:14/111320,longitude:0,routeShape:[[[-.002,0],[.002,0]]],freshness:'fresh',sourceConnected:true}]});
view.setCutaway(true);
assert.equal(view.statistics().section.report.renderedAs,'illustrated train');
assert.equal(view.statistics().section.report.latitude,14/111320,'raw observation retained');
assert.equal(view.statistics().section.report.representedPosition.latitude,0,'route-compatible track selected instead of crossing tunnel');
assert.ok(Math.abs(view.statistics().section.report.representedPosition.offsetMetres-14)<.001);
assert.ok(view.statistics().section.geometryBounds.max[2]-view.statistics().section.geometryBounds.min[2]<=6.01,'crossing branch is not excavated');
assert.ok(view.statistics().section.segmentCount>1);
const city=new THREE.Group();
for(const [x,y,z,w,h,d] of [[0,-.5,0,200,1,200],[-26,14,5,15,28,16],[26,18,-5,15,36,16]]){
 const mesh=new THREE.Mesh(new THREE.BoxGeometry(w,h,d),new THREE.MeshBasicMaterial({color:y<0?'#79947a':'#b49d84'}));mesh.position.set(x,y,z);city.add(mesh);
}
city.updateMatrixWorld(true);view.group.updateMatrixWorld(true);
const mask=view.getCutaway();
function removed(point){const b=mask.bounds,p=mask.projection,t=mask.texture.image;const x=Math.floor((point.x-point.y*p.x-b.x)/b.z*t.width),z=Math.floor((point.z-point.y*p.y-b.y)/b.w*t.height);return x>=0&&z>=0&&x<t.width&&z<t.height&&t.data[z*t.width+x]>127;}
const ray=new THREE.Raycaster(),width=320,height=240,pixels=Buffer.alloc(width*height*3);let trainPixels=0,clearedBuildingPixels=0,unsupportedOpeningPixels=0;
for(let y=0;y<height;y++)for(let x=0;x<width;x++){
 ray.setFromCamera(new THREE.Vector2((x+.5)/width*2-1,1-(y+.5)/height*2),camera);
 const cityHits=ray.intersectObject(city,true), visibleCity=cityHits.filter(hit=>!removed(hit.point));
 const transitHits=ray.intersectObject(view.group,true).filter(hit=>!hit.object.isInstancedMesh||hit.instanceId<hit.object.count);
 if(cityHits.some(hit=>removed(hit.point))&&!transitHits.length)unsupportedOpeningPixels++;
 const hit=[...visibleCity,...transitHits].sort((a,b)=>a.distance-b.distance)[0];
 let colour=new THREE.Color('#c5c2ad');
 if(hit){colour=hit.object.material.color.clone();if(hit.object.name==='Observed metro'){colour.set('#e2e3ce');trainPixels++;}if(hit.object.name==='metro roofs'){colour.set('#e2e3ce');trainPixels++;}if(hit.face)colour.multiplyScalar(.65+.35*Math.abs(hit.face.normal.y));}
 if(cityHits.some(h=>h.object.position.y>0&&removed(h.point)))clearedBuildingPixels++;
 const i=(y*width+x)*3;pixels[i]=Math.round(colour.r*255);pixels[i+1]=Math.round(colour.g*255);pixels[i+2]=Math.round(colour.b*255);
}
assert.equal(unsupportedOpeningPixels,0,'aperture must not expose background beyond actual section faces');
assert.ok(trainPixels>150,`train must have legible projected area: ${trainPixels}`);
assert.ok(clearedBuildingPixels>150,`building pixels must be removed by projected mask: ${clearedBuildingPixels}`);
const path=process.argv[2]||'/tmp/metro-occlusion.ppm';await writeFile(path,Buffer.concat([Buffer.from(`P6\n${width} ${height}\n255\n`),pixels]));
console.log(JSON.stringify({path,trainPixels,clearedBuildingPixels,unsupportedOpeningPixels,representedPosition:view.statistics().section.report.representedPosition}));
view.dispose();
