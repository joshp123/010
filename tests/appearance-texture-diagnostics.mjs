import assert from 'node:assert/strict';import {registerHooks} from 'node:module';
registerHooks({resolve(s,c,next){return next(s==='three'?new URL('../public/vendor/three/build/three.module.js',import.meta.url).href:s,c);}});
const THREE=await import('../public/vendor/three/build/three.module.js');const{appearanceTextureDiagnostics}=await import('../public/building-appearance.js');
const texture=new THREE.Texture({width:8,height:4});const clone=texture.clone();clone.offset.set(.3,.4);clone.repeat.set(.5,2);const model=new THREE.Group();
for(const map of [texture,clone])model.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map})));
let result=appearanceTextureDiagnostics([model]);assert.equal(result.textureObjects,2);assert.equal(result.uniqueImageSources,1);assert.equal(result.sourceSamplerVariants,1);assert.equal(result.decodedRgbaBytes,128);assert.equal(result.decodedRgbaBytesIncludingMips,172);assert.deepEqual(result.dimensions,{'8x4':1});
clone.magFilter=THREE.NearestFilter;result=appearanceTextureDiagnostics([model]);assert.equal(result.sourceSamplerVariants,2);assert.equal(result.uniqueImageSources,1);assert.equal(result.decodedRgbaBytesIncludingMips,172);
const separate=new THREE.Texture(texture.image);model.add(new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial({map:separate})));result=appearanceTextureDiagnostics([model]);assert.equal(result.uniqueImageSources,2,'Separate Texture.Source objects are distinct renderer upload caches even with same image object');assert.equal(result.decodedRgbaBytesIncludingMips,344);
console.log('Texture.Source sharing, transform-only clones, sampler variants and RGBA mip estimates pass; no measured GPU allocation claim.');
