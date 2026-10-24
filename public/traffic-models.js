// Generic illustrative city vehicles in metres, facing +Z. No surveyed vehicle
// make/person identity is implied. Shared geometry keeps every fleet instanced.
import * as THREE from 'three';

function box(size,position,color='#ffffff') {
  const geometry=new THREE.BoxGeometry(...size);geometry.translate(...position);return tint(geometry,color);
}
function tint(geometry,color) {
  const c=new THREE.Color(color),values=[];
  for(let i=0;i<geometry.attributes.position.count;i++)values.push(c.r,c.g,c.b);
  geometry.setAttribute('color',new THREE.Float32BufferAttribute(values,3));return geometry;
}
function combine(parts) {
  const positions=[],normals=[],colors=[];
  for(const source of parts) {
    const geometry=source.index?source.toNonIndexed():source;
    positions.push(...geometry.attributes.position.array);normals.push(...geometry.attributes.normal.array);colors.push(...geometry.attributes.color.array);
    if(geometry!==source)geometry.dispose();source.dispose();
  }
  const result=new THREE.BufferGeometry();
  result.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));result.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));result.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
  result.computeBoundingBox();result.computeBoundingSphere();return result;
}
function bar(a,b,width,color='#ffffff') {
  const start=new THREE.Vector3(...a),end=new THREE.Vector3(...b),direction=end.clone().sub(start);
  const geometry=new THREE.BoxGeometry(width,direction.length(),width);
  geometry.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),direction.normalize()));geometry.translate(...start.add(end).multiplyScalar(.5).toArray());return tint(geometry,color);
}
function cabin(width,baseY,topY,baseBack,baseFront,topBack,topFront) {
  const points=[[-width/2,baseY,baseBack],[width/2,baseY,baseBack],[-width/2,baseY,baseFront],[width/2,baseY,baseFront],[-width/2,topY,topBack],[width/2,topY,topBack],[-width/2,topY,topFront],[width/2,topY,topFront]];
  const indices=[0,2,1,1,2,3,0,1,4,1,5,4,2,6,3,3,6,7,4,5,6,5,7,6,0,4,2,2,4,6,1,3,5,3,7,5];
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(indices.reverse().flatMap(i=>points[i]),3));geometry.computeVertexNormals();return tint(geometry,'#ffffff');
}
export function createCarGeometries() {
  const painted=[box([1.75,.48,4.2],[0,.59,0]),box([1.69,.10,1.10],[0,.87,1.5]),box([1.69,.10,.65],[0,.87,-1.74]),cabin(1.48,1.40,1.47,-.96,.43,-.94,.40)];
  for(const x of [-.766,.766]) {
    painted.push(bar([x,.87,1.02],[x,1.43,.43],.08),bar([x,.87,-1.39],[x,1.43,-.96],.09),bar([x,.87,-.35],[x,1.43,-.35],.075));
  }
  const trim=[];
  for(const x of [-.84,.84])for(const z of [-1.28,1.28]) {
    const tyre=new THREE.CylinderGeometry(.31,.31,.20,12).rotateZ(Math.PI/2).translate(x,.31,z);trim.push(tint(tyre,'#29302f'));
    const hub=new THREE.CylinderGeometry(.135,.135,.205,8).rotateZ(Math.PI/2).translate(x,.31,z);trim.push(tint(hub,'#92958d'));
  }
  trim.push(box([1.68,.13,.08],[0,.39,2.11],'#525853'),box([1.68,.13,.08],[0,.39,-2.11],'#525853'));
  for(const x of [-.62,.62])trim.push(box([.30,.15,.025],[x,.72,2.115],'#e8debc'),box([.25,.14,.025],[x,.72,-2.115],'#8b493d'));
  return {body:combine(painted),glass:cabin(1.52,.86,1.41,-1.4,1.04,-.96,.43),trim:combine(trim)};
}
export function createBicycleGeometries() {
  const rear=[0,.32,-.56],front=[0,.32,.56],crank=[0,.34,-.05],seat=[0,.88,-.24],steer=[0,.85,.39];
  const frame=[];
  for(const [a,b] of [[rear,seat],[rear,crank],[seat,crank],[seat,steer],[steer,crank],[steer,front]])frame.push(bar(a,b,.065,'#687c78'));
  frame.push(bar(steer,[0,1.05,.35],.065,'#3f4947'),bar([-.27,1.06,.35],[.27,1.06,.35],.055,'#303936'),box([.26,.075,.25],[0,.92,-.24],'#343b39'));
  const torso=box([.38,.48,.25],[0,1.22,-.03]);torso.translate(0,-1.02,.15);torso.rotateX(.28);torso.translate(0,1.02,-.15);
  const arms=[];
  for(const x of [-.19,.19])arms.push(bar([x,1.40,.03],[x,1.16,.28],.115),bar([x,1.16,.28],[x,1.07,.35],.10));
  return {body:combine([torso,...arms]),head:tint(new THREE.IcosahedronGeometry(.145,0).translate(0,1.61,.11),'#ffffff'),frame:combine(frame),wheel:tint(new THREE.TorusGeometry(.30,.045,4,12).rotateY(Math.PI/2),'#ffffff')};
}
