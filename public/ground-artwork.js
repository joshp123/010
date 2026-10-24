// Written by AI, GPT-6, 2026-10-24.
// Bounded, georeferenced model interpretation on exact surveyed ground features.
// Never project an aerial-derived image onto buildings, trees or unknown ground.
import * as THREE from 'three';

export function createGroundArtwork({baseUrl='./data/ground-artwork/',requestRender=()=>{},enabled=false,anisotropy=1}={}) {
  const uniforms={groundArtwork:{value:new THREE.Texture()},groundArtworkU:{value:new THREE.Vector4()},groundArtworkV:{value:new THREE.Vector4()},groundArtworkReady:{value:0},groundArtworkMaterialEncoding:{value:0}};
  const models=new Set(),stats={enabled,loaded:false,error:null,sourceFeatures:0,eligibleVertices:0};
  let manifest=null,allowed=new Set(),disposed=false;
  function addModel(model) {
    models.add(model);
    if(!manifest)return;
    model.traverse(mesh=>{
      if(!mesh.isMesh||!mesh.geometry?.getAttribute('position')||mesh.geometry.userData.sourceBoundarySegments)return;
      const geometry=mesh.geometry,batch=geometry.getAttribute('_batchid');
      if(!batch||geometry.getAttribute('_groundArtworkAllowed'))return;
      let parent=mesh;while(parent&&!parent.batchTable)parent=parent.parent;
      if(!parent)return;
      const flags=new Float32Array(batch.count),cached=new Map();let eligible=0;
      for(let i=0;i<batch.count;i++){
        const id=batch.getX(i);let flag=cached.get(id);
        if(flag===undefined){
          let record;try{record=parent.batchTable.getDataFromId(id);}catch{}
          const sourceId=String(record?.attributes?.DGDT_ID??record?.id??'');
          flag=allowed.has(sourceId)?1:0;cached.set(id,flag);
        }
        flags[i]=flag;eligible+=flag;
      }
      geometry.setAttribute('_groundArtworkAllowed',new THREE.BufferAttribute(flags,1));
      geometry.userData.groundArtworkEligibleVertices=eligible;
    });
  }
  const ready=enabled?(async()=>{
    try{
      const base=new URL(baseUrl,document.baseURI),response=await fetch(new URL('manifest.json',base));
      if(!response.ok)throw Error(`Ground artwork manifest HTTP ${response.status}`);
      const data=await response.json();
      if(data.status!=='review-candidate')throw Error('Unrecognised ground artwork status');
      const texture=await new THREE.TextureLoader().loadAsync(new URL(data.texture,base).href);
      if(disposed){texture.dispose();return;}
      texture.anisotropy=anisotropy;texture.colorSpace=THREE.SRGBColorSpace;texture.magFilter=THREE.LinearFilter;texture.minFilter=THREE.LinearMipmapLinearFilter;texture.wrapS=texture.wrapT=THREE.ClampToEdgeWrapping;
      // Compiler rows map world position to top-left image-normalized pixels.
      // Three TextureLoader flips image upload, so invert V here exactly once.
      uniforms.groundArtwork.value.dispose();uniforms.groundArtwork.value=texture;
      uniforms.groundArtworkU.value.fromArray(data.worldToImageUV[0]);uniforms.groundArtworkV.value.fromArray(data.worldToImageUV[1]);
      uniforms.groundArtworkMaterialEncoding.value=data.alphaEncoding==='material128-marking255'?1:0;
      manifest=data;allowed=new Set(data.sourceFeatureIds.map(String));stats.sourceFeatures=allowed.size;
      for(const model of models)addModel(model);
      uniforms.groundArtworkReady.value=1;stats.loaded=true;requestRender();
    }catch(error){stats.error=String(error);console.warn('010 ground artwork:',error);}
  })():Promise.resolve();
  return {ready,addModel,refresh(){for(const model of models)addModel(model);},removeModel(model){models.delete(model);},apply(material){
    if(!enabled||material.userData.groundArtwork)return;
    material.userData.groundArtwork=true;
    material.defaultAttributeValues={...material.defaultAttributeValues,_groundArtworkAllowed:[0]};
    const compile=material.onBeforeCompile,key=material.customProgramCacheKey();
    material.onBeforeCompile=function(shader,renderer){
      compile.call(this,shader,renderer);Object.assign(shader.uniforms,uniforms);
      shader.vertexShader='attribute float _groundArtworkAllowed; varying float groundArtworkAllowed;\n'+shader.vertexShader;
      shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\n groundArtworkAllowed=_groundArtworkAllowed;');
      shader.fragmentShader='uniform sampler2D groundArtwork; uniform vec4 groundArtworkU; uniform vec4 groundArtworkV; uniform float groundArtworkReady; uniform float groundArtworkMaterialEncoding; varying float groundArtworkAllowed;\n'+shader.fragmentShader;
      shader.fragmentShader=shader.fragmentShader.replace('#include <color_fragment>',`#include <color_fragment>
        if(groundArtworkReady>.5 && groundArtworkAllowed>.999 && abs(normalize(cityWorldNormal).y)>.75) {
          vec4 groundPoint=vec4(cityWorldPosition,1.0);
          vec2 groundUV=vec2(dot(groundArtworkU,groundPoint),dot(groundArtworkV,groundPoint));
          if(all(greaterThanEqual(groundUV,vec2(0.0)))&&all(lessThanEqual(groundUV,vec2(1.0)))) {
            vec4 groundPaint=texture2D(groundArtwork,vec2(groundUV.x,1.0-groundUV.y));
            // Keep the retained paving strokes and observed paint shapes, while
            // their material field follows the same source-class palette as
            // adjoining native ground. The original atlas remains unchanged.
            vec3 groundMaterialField=texture2D(groundArtwork,vec2(groundUV.x,1.0-groundUV.y),5.0).rgb;
            float groundDetail=dot(groundPaint.rgb-groundMaterialField,vec3(.2126,.7152,.0722));
            vec3 groundDrawnMaterial=clamp(diffuseColor.rgb+vec3(groundDetail*.8),0.0,1.0);
            if(groundArtworkMaterialEncoding>.5) {
              float groundMark=clamp((groundPaint.a-128.0/255.0)*(255.0/127.0),0.0,1.0);
              groundDrawnMaterial=mix(groundDrawnMaterial,groundPaint.rgb,groundMark);
              diffuseColor.rgb=mix(diffuseColor.rgb,groundDrawnMaterial,min(1.0,groundPaint.a*2.0));
            } else diffuseColor.rgb=mix(diffuseColor.rgb,groundPaint.rgb,groundPaint.a);
          }
        }
      `);
    };
    material.customProgramCacheKey=()=>key+'-source-ground-artwork-v2';material.needsUpdate=true;
  },diagnostics(){let vertices=0;for(const model of models)model.traverse(mesh=>{vertices+=mesh.geometry?.userData.groundArtworkEligibleVertices||0;});return {...stats,models:models.size,eligibleVertices:vertices};},dispose(){disposed=true;models.clear();uniforms.groundArtwork.value.dispose();}};
}
