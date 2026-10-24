import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(s,c,next){if(s==='three')return {url:new URL('../public/vendor/three/build/three.module.js',import.meta.url).href,shortCircuit:true};return next(s,c);}});
const THREE=await import('three');
const {createGroundArtwork}=await import('../public/ground-artwork.js');
globalThis.document={baseURI:'https://example.test/010/'};
let release;globalThis.fetch=async()=>{await new Promise(r=>release=r);return {ok:true,json:async()=>({status:'review-candidate',texture:'ground.png',sourceFeatureIds:['123'],worldToImageUV:[[1,0,0,0],[0,0,1,0]]})};};
THREE.TextureLoader.prototype.loadAsync=async()=>new THREE.Texture();
const original=new THREE.BufferGeometry();original.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,1,0,0,0,0,1,1,0,1,2,0,1,1,0,2],3));original.setAttribute('_batchid',new THREE.Float32BufferAttribute([0,0,0,1,1,1],1));
const model=new THREE.Group();model.batchTable={getDataFromId:id=>({attributes:{DGDT_ID:id===0?123:456}})};const mesh=new THREE.Mesh(original.clone());model.add(mesh);
const art=createGroundArtwork({enabled:true});art.addModel(model);assert.equal(mesh.geometry.getAttribute('_groundArtworkAllowed'),undefined);release();await art.ready;
assert.deepEqual([...mesh.geometry.getAttribute('_groundArtworkAllowed').array],[1,1,1,0,0,0]);assert.equal(art.diagnostics().eligibleVertices,3);
// Source fusion may replace a geometry using a pre-manifest original snapshot.
// Refresh must attach semantic eligibility to that newly created geometry.
mesh.geometry=original.clone();art.refresh();assert.deepEqual([...mesh.geometry.getAttribute('_groundArtworkAllowed').array],[1,1,1,0,0,0]);
const material=new THREE.MeshStandardMaterial();art.apply(material);const compile=material.onBeforeCompile;art.apply(material);assert.equal(material.onBeforeCompile,compile);assert.equal(material.defaultAttributeValues._groundArtworkAllowed[0],0);
art.removeModel(model);assert.equal(art.diagnostics().models,0);art.dispose();console.log('Ground artwork async source eligibility, unknown exclusion, regenerated geometry refresh and material idempotence passed.');
