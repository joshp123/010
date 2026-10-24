import assert from 'node:assert/strict';import {registerHooks} from 'node:module';
registerHooks({resolve(s,c,next){return next(s==='three'?new URL('../public/vendor/three/build/three.module.js',import.meta.url).href:s,c);}});
const THREE=await import('../public/vendor/three/build/three.module.js');const{createAppearancePriorityReconciliation}=await import('../public/building-appearance.js');
const native=new THREE.Group(),art=new THREE.Group();const make=(id,visible=true)=>{const mesh=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshBasicMaterial());mesh.userData.featureId=id;mesh.visible=visible;return mesh;};
const target=make('OST_14427971'),neighbour=make('OST_14427972'),originalHidden=make('OST_14427971',false),unknown=make('BAG_14427971'),replacement=make('OST_14427971');native.add(target,neighbour,originalHidden,unknown);art.add(replacement);const reconcile=createAppearancePriorityReconciliation();
assert.equal(reconcile.update([native],[art]),true);assert.equal(target.visible,false);assert.equal(neighbour.visible,true);assert.equal(unknown.visible,true);assert.equal(originalHidden.visible,false);assert.equal(reconcile.update([native],[art]),false);
assert.equal(reconcile.update([native],[]),true);assert.equal(target.visible,true);assert.equal(originalHidden.visible,false,'Unloading art must not expose originally hidden native geometry');
art.visible=false;assert.equal(reconcile.update([native],[art]),false);assert.equal(target.visible,true);art.visible=true;reconcile.update([native],[art]);replacement.visible=false;assert.equal(reconcile.update([native],[art]),true);assert.equal(target.visible,true);
console.log('Exact OST override only; neighbouring/unknown identities preserved; hidden/unloaded illustration restores original visibility.');
