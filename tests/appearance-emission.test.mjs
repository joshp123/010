import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(s,c,next){return next(s==='three'?new URL('../public/vendor/three/build/three.module.js',import.meta.url).href:s,c);}});
const THREE=await import('../public/vendor/three/build/three.module.js');
const {prepareAppearanceModel}=await import('../public/building-appearance.js');
const night={value:0},map=new THREE.Texture(),mat=new THREE.MeshStandardMaterial({emissive:0xffffff,emissiveMap:map}),model=new THREE.Mesh(new THREE.BoxGeometry(),mat);
function fixtureHook(material){const before=material.onBeforeCompile;material.onBeforeCompile=function(shader,renderer){before.call(this,shader,renderer);shader.fragmentShader=shader.fragmentShader.replace('#include <emissivemap_fragment>','#include <emissivemap_fragment>\ntotalEmissiveRadiance += vec3(fixtureNight);');};}
prepareAppearanceModel(model,{night,applyLighting:fixtureHook,applyCutaway:()=>{}});
const shader={uniforms:{},vertexShader:'#include <begin_vertex>',fragmentShader:'vec3 totalEmissiveRadiance = emissive;\n#include <emissivemap_fragment>'};mat.onBeforeCompile(shader,{});
assert.equal(shader.uniforms.appearanceSourceNight,night);night.value=1;assert.equal(shader.uniforms.appearanceSourceNight.value,1);assert.equal(mat.emissiveMap,map);assert.equal(mat.emissive.getHex(),0xffffff);
const gate=shader.fragmentShader.indexOf('totalEmissiveRadiance *= clamp('),source=shader.fragmentShader.indexOf('#include <emissivemap_fragment>'),fixture=shader.fragmentShader.indexOf('totalEmissiveRadiance += vec3(fixtureNight)');assert.ok(gate>=0&&gate<source&&source<fixture);assert.equal(shader.fragmentShader.match(/totalEmissiveRadiance \*=/g).length,1);
const unchanged=new THREE.MeshStandardMaterial({emissive:0xffffff,emissiveMap:map});prepareAppearanceModel(new THREE.Mesh(new THREE.BoxGeometry(),unchanged),{applyLighting:fixtureHook,applyCutaway:()=>{}});const without={uniforms:{},vertexShader:'',fragmentShader:'#include <emissivemap_fragment>'};unchanged.onBeforeCompile(without,{});assert.ok(!without.fragmentShader.includes('appearanceSourceNight'));assert.notEqual(mat.customProgramCacheKey(),unchanged.customProgramCacheKey());
console.log('Optional shared night gate precedes source emissive map and fixture contribution; original emissive assets unchanged');
