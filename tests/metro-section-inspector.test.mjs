// Geometry/framing checks and a CPU composition aid; actual WebGL review decides quality.
import assert from 'node:assert/strict';
import {readFile,writeFile} from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source=(await readFile(new URL('../public/transit-view.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
const {createTransitView}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const view=createTransitView({project:(lat,lon,y=0)=>new THREE.Vector3(lon*111320,2.6+y,-lat*111320)});
view.setMetroData({source:'synthetic test only',segments:[{id:'track',form:'tunnel',coordinates:[[-.002,0],[.002,0]]}]});
const cityCamera=new THREE.OrthographicCamera(-110,110,110,-110,.1,1000);cityCamera.position.set(70,100,70);cityCamera.lookAt(0,0,0);cityCamera.updateMatrixWorld();
view.setView({camera:cityCamera,span:220,viewportHeight:844});
const report={id:'test',mode:'metro',latitude:0,longitude:0,freshness:'fresh',sourceConnected:true,observedAt:1234};
view.update({vehicles:[report]});view.setCutaway(true);
assert.equal(view.getSectionGeometry().enabled,false,'inspector must not remove city geometry');
const dimensions=[[390,844],[1280,720]];
for(const [width,height] of dimensions){
 const section=view.getSectionView({width,height});
 assert.ok(section.enabled);assert.ok(section.viewportHeight<=height*.28+1);
 assert.equal(section.report.observedAt,1234);assert.equal(section.streetAnchor.y,2.6);
 const train=section.scene.getObjectByName('Section reported train');assert.ok(train);
 const matrix=new THREE.Matrix4();train.getMatrixAt(0,matrix);
 const bounds=new THREE.Box3().setFromObject(train),corners=[];
 for(const x of [bounds.min.x,bounds.max.x])for(const y of [bounds.min.y,bounds.max.y])for(const z of [bounds.min.z,bounds.max.z])corners.push(new THREE.Vector3(x,y,z).project(section.camera));
 assert.ok(corners.every(p=>Math.abs(p.x)<.98&&Math.abs(p.y)<.98),'full train framed on desktop and phone');
}
const section=view.getSectionView({width:390,height:844});
const width=390,height=section.viewportHeight,pixels=Buffer.alloc(width*height*3),ray=new THREE.Raycaster();let trainPixels=0;
for(let y=0;y<height;y++)for(let x=0;x<width;x++){
 ray.setFromCamera(new THREE.Vector2((x+.5)/width*2-1,1-(y+.5)/height*2),section.camera);
 const hit=ray.intersectObject(section.scene,true)[0];let colour=section.scene.background.clone();
 if(hit){colour=hit.object.material.color.clone();if(hit.object.name.includes('Section reported train')||hit.object.name==='Section train roof'){colour.set('#d1d7cc');trainPixels++;}if(hit.face)colour.multiplyScalar(.55+.45*Math.abs(hit.face.normal.y));}
 colour.convertLinearToSRGB();const i=(y*width+x)*3;pixels[i]=colour.r*255;pixels[i+1]=colour.g*255;pixels[i+2]=colour.b*255;
}
assert.ok(trainPixels>700,'train must remain a readable focal element');
if(process.argv[2])await writeFile(process.argv[2],Buffer.concat([Buffer.from(`P6\n${width} ${height}\n255\n`),pixels]));
view.update({vehicles:[]});assert.equal(view.getSectionView().report,null);assert.ok(!view.getSectionView().scene.getObjectByName('Section reported train'),'empty observation must remove train');
view.setCutaway(false);assert.equal(view.getSectionView().enabled,false);
view.dispose();console.log(JSON.stringify({trainPixels,width,height,checks:'full train framing, finite panel, no city excavation, current report and empty state'}));
