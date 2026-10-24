import * as THREE from 'three';

// Preserve whole source features around an illustrative section as faint edges.
// Source triangles stay intact; a reversible attribute controls their draw/shadow.
export function createMetroCityCut() {
  const group = new THREE.Group(); group.name = 'Metro section · source building outlines';
  const material = new THREE.LineBasicMaterial({color:'#9baea1',transparent:true,opacity:.12,depthWrite:false});
  const records = new Map(), sourceKeys=new WeakMap();let nextSourceKey=0;
  function sourceKey(mesh,model,id,hasIds){
    for(let ancestor=mesh;ancestor;ancestor=ancestor.parent)if(ancestor.userData?.bagId)return `bag:${ancestor.userData.bagId}`;
    if(!hasIds)return `mesh:${mesh.uuid}`;
    let owner=mesh;while(owner&&!owner.batchTable)owner=owner.parent;owner=owner||model;
    if(!sourceKeys.has(owner))sourceKeys.set(owner,++nextSourceKey);return `${sourceKeys.get(owner)}:${id}`;
  }
  let lastKey='',selectedCount=0,builds=0;
  const point = new THREE.Vector3();
  function makeRecord(mesh,model) {
    const geometry=mesh.geometry,position=geometry.getAttribute('position'),ids=geometry.getAttribute('_batchid');
    const flags=new THREE.Float32BufferAttribute(new Float32Array(position.count),1);
    flags.setUsage(THREE.DynamicDrawUsage); geometry.setAttribute('_metroExcised',flags);
    const features=new Map();
    for(let index=0;index<position.count;index++) {
      const id=ids?.getX(index)??0;
      if(!features.has(id))features.set(id,{id,key:sourceKey(mesh,model,id,!!ids),vertices:[],bounds:new THREE.Box3(),selected:false,outline:null});
      const feature=features.get(id);feature.vertices.push(index);
      point.fromBufferAttribute(position,index).applyMatrix4(mesh.matrixWorld);feature.bounds.expandByPoint(point);
    }
    builds++;
    return {mesh,geometry,position,ids,flags,features,matrix:mesh.matrixWorld.clone()};
  }
  function removeRecord(record) {
    record.flags.array.fill(0);record.flags.needsUpdate=true;
    for(const feature of record.features.values())if(feature.outline){group.remove(feature.outline);feature.outline.geometry.dispose();}
  }
  function outline(record,feature) {
    const vertices=[],indices=[],mapping=new Map();
    for(const index of feature.vertices){mapping.set(index,vertices.length/3);point.fromBufferAttribute(record.position,index).applyMatrix4(record.matrix);vertices.push(point.x,point.y,point.z);}
    const sourceIndex=record.geometry.index,count=sourceIndex?.count??record.position.count;
    for(let offset=0;offset<count;offset+=3){const a=sourceIndex?sourceIndex.getX(offset):offset;if((record.ids?.getX(a)??0)!==feature.id)continue;for(let corner=0;corner<3;corner++)indices.push(mapping.get(sourceIndex?sourceIndex.getX(offset+corner):offset+corner));}
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));geometry.setIndex(indices);
    const allEdges=new THREE.EdgesGeometry(geometry,28);geometry.dispose();
    const original=allEdges.getAttribute('position'),baseEdges=[];
    // Retain only original low foundation edges, never a roof/facade wire cage.
    for(let i=0;i<original.count;i+=2)if(original.getY(i)<=feature.bounds.min.y+.6&&original.getY(i+1)<=feature.bounds.min.y+.6){
      for(const index of [i,i+1])baseEdges.push(original.getX(index),original.getY(index),original.getZ(index));
    }
    allEdges.dispose();const edges=new THREE.BufferGeometry();edges.setAttribute('position',new THREE.Float32BufferAttribute(baseEdges,3));
    const lines=new THREE.LineSegments(edges,material);lines.name='Original foundation edges · section context';group.add(lines);return lines;
  }
  const cross=(a,b,c)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  function hull(points){
    points.sort((a,b)=>a.x-b.x||a.y-b.y);const low=[],high=[];
    for(const p of points){while(low.length>1&&cross(low.at(-2),low.at(-1),p)<=0)low.pop();low.push(p);}
    for(const p of [...points].reverse()){while(high.length>1&&cross(high.at(-2),high.at(-1),p)<=0)high.pop();high.push(p);}
    return low.slice(0,-1).concat(high.slice(0,-1));
  }
  function overlaps(a,b){
    for(const polygon of [a,b])for(let i=0;i<polygon.length;i++){
      const p=polygon[i],q=polygon[(i+1)%polygon.length],axis={x:p.y-q.y,y:q.x-p.x};
      const aa=a.map(v=>v.x*axis.x+v.y*axis.y),bb=b.map(v=>v.x*axis.x+v.y*axis.y);
      if(Math.max(...aa)<Math.min(...bb)||Math.max(...bb)<Math.min(...aa))return false;
    }
    return true;
  }
  function update(models,section) {
    if(!section?.enabled){
      if(!records.size)return false;
      for(const record of records.values())removeRecord(record);records.clear();selectedCount=0;lastKey='off';return true;
    }
    const present=new Set();let changed=false;
    for(const model of models){model.updateWorldMatrix(true,true);model.traverseVisible(mesh=>{
      if(!mesh.isMesh)return;present.add(mesh);
      const previous=records.get(mesh);
      if(!previous||previous.geometry!==mesh.geometry||!previous.matrix.equals(mesh.matrixWorld)){
        if(previous)removeRecord(previous);records.set(mesh,makeRecord(mesh,model));changed=true;
      }
    });}
    for(const [mesh,record]of records)if(!present.has(mesh)){removeRecord(record);records.delete(mesh);changed=true;}
    const key=section?.enabled?JSON.stringify([section.projection.toArray(),section.segments.map(s=>[s.start.toArray(),s.end.toArray()])]):'off';
    if(!changed&&key===lastKey)return false;
    lastKey=key;selectedCount=0;
    const projection=section?.projection||new THREE.Vector2();
    const project=p=>({x:p.x-p.y*projection.x,y:p.z-p.y*projection.y});
    const footprints=[],physicalFootprints=[];
    if(section?.enabled)for(const segment of section.segments){
      const side=new THREE.Vector3(-(segment.end.z-segment.start.z),0,segment.end.x-segment.start.x).normalize().multiplyScalar(section.selectionHalfWidth??section.halfWidth);
      const points=[];
      for(const end of [segment.start,segment.end])for(const sign of [-1,1])for(const depth of [0,-section.depth])points.push(project(end.clone().addScaledVector(side,sign).add(new THREE.Vector3(0,depth,0))));
      footprints.push(hull(points));
      physicalFootprints.push(hull([segment.start.clone().add(side),segment.start.clone().sub(side),segment.end.clone().add(side),segment.end.clone().sub(side)].map(p=>({x:p.x,y:p.z}))));
    }
    const featureBounds=new Map();
    for(const record of records.values())for(const feature of record.features.values()){
      if(!featureBounds.has(feature.key))featureBounds.set(feature.key,feature.bounds.clone());else featureBounds.get(feature.key).union(feature.bounds);
    }
    const selectedKeys=new Set();
    for(const [key,bounds]of featureBounds){
      const {min,max}=bounds,points=[];
      for(const x of [min.x,max.x])for(const y of [min.y,max.y])for(const z of [min.z,max.z])points.push(project({x,y,z}));
      const polygon=hull(points);
      const physical=[{x:min.x,y:min.z},{x:max.x,y:min.z},{x:max.x,y:max.z},{x:min.x,y:max.z}];
      if(footprints.length>0&&polygon.length>2&&(footprints.some(footprint=>overlaps(polygon,footprint))||physicalFootprints.some(footprint=>overlaps(physical,footprint))))selectedKeys.add(key);
    }
    selectedCount=selectedKeys.size;
    for(const record of records.values()){
      let dirty=false;
      for(const feature of record.features.values()){
        const selected=selectedKeys.has(feature.key);
        if(selected===feature.selected)continue;
        feature.selected=selected;dirty=true;changed=true;
        for(const index of feature.vertices)record.flags.setX(index,selected?1:0);
        if(selected)feature.outline=outline(record,feature);
        else if(feature.outline){group.remove(feature.outline);feature.outline.geometry.dispose();feature.outline=null;}
      }
      if(dirty)record.flags.needsUpdate=true;
    }
    return changed;
  }
  return {group,update,diagnostics:()=>({cachedMeshes:records.size,featureBuilds:builds,selectedFeatures:selectedCount}),dispose(){for(const record of records.values())removeRecord(record);records.clear();material.dispose();group.removeFromParent();}};
}
