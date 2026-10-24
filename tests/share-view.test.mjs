import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
// Exercise the actual URL encoder without initializing WebGL or live network IO.
const app=await readFile(new URL('../public/app.js',import.meta.url),'utf8');
const encoder=app.slice(app.indexOf('function encodeView('),app.indexOf('\nfunction updateView('));
for(const appearance of ['illustrated-row','current','off']) {
 const state={URL,location:{href:'https://candidate.example/'},url:new URL(`https://candidate.example/?appearance=${appearance}&vegetation=native&tanks=current&private=omit`),scene:{getView:()=>({lat:51.91,lon:4.48,span:40,bearing:35})},lightingMode:'night'};
 vm.createContext(state);vm.runInContext(encoder+';globalThis.encode=encodeView;',state);
 for(const base of [undefined,'https://010.jjpcodes.com/']) {
  const result=new URL(state.encode(base));
  assert.equal(result.searchParams.get('appearance'),appearance);
  assert.equal(result.searchParams.get('vegetation'),'native');assert.equal(result.searchParams.get('tanks'),'current');
  assert.equal(result.searchParams.get('span'),'40');assert.equal(result.searchParams.get('light'),'night');
  assert.equal(result.searchParams.has('private'),false);
 }
 state.url=new URL('https://candidate.example/?appearance=unknown&vegetation=unknown&tanks=unknown');
 const result=new URL(state.encode());for(const key of ['appearance','vegetation','tanks'])assert.equal(result.searchParams.has(key),false);
}
console.log('Actual share/history URL encoder preserves initialized review modes, 40m view and lighting; excludes unrelated/invalid parameters.');
