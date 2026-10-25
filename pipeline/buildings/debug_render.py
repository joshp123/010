"""Written by AI on 2026-10-25 by model GPT-6.1 Sol.

Offline inspection renders of a source-derived tile; this is not product UI.
"""
import argparse
import datetime
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import tempfile
import socket
from urllib.parse import urlparse, unquote
import requests
import numpy as np
from shapely import union_all
from shapely.geometry import Polygon, mapping
from build import unpack_glb, accessor

REPOSITORY = Path(__file__).resolve().parents[2]
DATA = REPOSITORY.parent
OUTPUT = DATA / 'renders/debug-buildings'

HTML = '''<!doctype html><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden;background:#deded7}canvas{display:block}</style>
<script type="importmap">{"imports":{"three":"/repo/web/vendor/three/build/three.module.js","three/addons/":"/repo/web/vendor/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
try {
const mode=new URL(location).searchParams.get('mode');
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
renderer.setSize(2500,2500);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.setClearColor(0xdedfd9);
document.body.appendChild(renderer.domElement);
const scene=new THREE.Scene();scene.add(new THREE.HemisphereLight(0xffffff,0xd1c9b6,2.0));
const sun=new THREE.DirectionalLight(0xffffff,1.8);sun.position.set(-100,400,200);scene.add(sun);
const gltf=await new GLTFLoader().loadAsync('/scene/tiles/TILE/buildings.glb');
scene.add(gltf.scene);
const camera=new THREE.OrthographicCamera(-125,125,125,-125,.1,2000);
if(mode==='oblique') {
  camera.left=-155;camera.right=155;camera.top=155;camera.bottom=-155;camera.updateProjectionMatrix();
  camera.position.set(400,265,300);camera.lookAt(125,8,-125);
} else {
  camera.position.set(125,500,-125);camera.up.set(0,0,-1);camera.lookAt(125,0,-125);
  const texture=await new THREE.TextureLoader().loadAsync('/debug/aerial-TILE.jpg');texture.colorSpace=THREE.SRGBColorSpace;
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(250,250),new THREE.MeshBasicMaterial({map:texture}));
  ground.rotation.x=-Math.PI/2;ground.position.set(125,-10,-125);scene.add(ground);
  gltf.scene.traverse(object=>{if(!object.isMesh)return;
    if(mode==='edges'||mode==='aerial')object.visible=false;
    else{object.material=object.material.clone();object.material.transparent=true;object.material.opacity=.55;}
  });
  if(mode!=='aerial') {
    const outlines=[];
    gltf.scene.updateMatrixWorld(true);
    gltf.scene.traverse(object=>{if(!object.isMesh)return;
      const lines=new THREE.LineSegments(new THREE.EdgesGeometry(object.geometry,30),new THREE.LineBasicMaterial({color:0x00ffff,transparent:true,opacity:.9,depthTest:false}));
      lines.applyMatrix4(object.matrixWorld);lines.renderOrder=10;outlines.push(lines);
    });outlines.forEach(lines=>scene.add(lines));
  }
}
renderer.render(scene,camera);document.title='READY';window.renderComplete=true;
} catch(e) {document.body.innerText=e.stack;document.title='FAILED';}
</script>'''


def aerial(tile):
    target=OUTPUT/f'aerial-{tile}.jpg'
    if target.exists():return
    existing=DATA/'scene/v1/tiles'/tile/'ortho.jpg'
    if existing.exists():
        shutil.copyfile(existing,target)
        return
    x,y=[int(v[1:]) for v in tile.split('_')]
    directory=DATA/'sources/debug-buildings-ortho/2026-10-25'
    directory.mkdir(parents=True,exist_ok=True)
    params={'SERVICE':'WMS','REQUEST':'GetMap','VERSION':'1.3.0','LAYERS':'2026_orthoHR','STYLES':'','CRS':'EPSG:28992','BBOX':f'{x},{y},{x+250},{y+250}','WIDTH':2500,'HEIGHT':2500,'FORMAT':'image/jpeg'}
    response=requests.get('https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0',params=params,timeout=90)
    response.raise_for_status()
    if not response.headers.get('Content-Type','').startswith('image/jpeg'):raise ValueError(response.text[:1000])
    source=directory/f'{tile}.jpg';source.write_bytes(response.content)
    manifest={'dataset':'PDOK 2026_orthoHR debug roof-alignment reference','licence':'CC BY 4.0','credit':'Samenwerkingsverband Beeldmateriaal / PDOK — Luchtfoto 2026','files':[{'path':source.name,'url':response.url,'sha256':hashlib.sha256(response.content).hexdigest(),'bytes':len(response.content),'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}]}
    manifest_path=directory/'manifest.json'
    if manifest_path.exists():
        previous=json.loads(manifest_path.read_text())
        manifest['files']=[record for record in previous['files'] if record['path']!=source.name]+manifest['files']
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    shutil.copyfile(source,target)


class Handler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self,path):
        parts=unquote(urlparse(path).path).split('/')
        roots={'repo':REPOSITORY,'scene':DATA/'scene/v1','debug':OUTPUT}
        return str(roots.get(parts[1],OUTPUT).joinpath(*parts[2:]))
    def log_message(self,*args):pass
    def copyfile(self,source,outputfile):
        try:super().copyfile(source,outputfile)
        except (BrokenPipeError,ConnectionResetError):pass  # CDP navigation cancels startup requests.


def export_roof_edges(tile):
    x,y=[int(v[1:]) for v in tile.split('_')]
    source=DATA/'scene/v1/tiles'/tile/'buildings.glb'
    j,binary=unpack_glb(source.read_bytes());polygons={}
    for mesh in j.get('meshes',[]):
        for primitive in mesh['primitives']:
            attrs=primitive['attributes'];positions=accessor(j,binary,attrs['POSITION']).astype(np.float64).reshape(-1,3,3)
            identifiers=accessor(j,binary,attrs['_FEATURE_ID_0']).reshape(-1,3)[:,0]
            normals=np.cross(positions[:,1]-positions[:,0],positions[:,2]-positions[:,0]);length=np.linalg.norm(normals,axis=1)
            for triangle,identifier in zip(positions[normals[:,1]>.2*length],identifiers[normals[:,1]>.2*length]):
                polygon=Polygon(np.column_stack((triangle[:,0]+x,y-triangle[:,2])))
                if polygon.area>1e-6:polygons.setdefault(int(identifier),[]).append(polygon)
    features=[]
    for identifier,parts in polygons.items():
        feature=j['extras']['features'][identifier]
        features.append({'type':'Feature','properties':feature,'geometry':mapping(union_all(parts).boundary)})
    output={'type':'FeatureCollection','coordinate_reference_system':'EPSG:28992','image_pixel_mapping':'u=(RD_x-x_min)*10; v=(y_min+250-RD_y)*10; pixel origin upper left','tile':tile,'features':features}
    (OUTPUT/f'projected-roof-edges-{tile}.json').write_text(json.dumps(output,separators=(',',':'))+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tile',default='x90250_y436000');args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True);aerial(args.tile)
    if not (DATA/'scene/v1/tiles'/args.tile/'buildings.glb').exists():raise FileNotFoundError('Building tile is not yet built')
    export_roof_edges(args.tile)
    page=OUTPUT/f'debug-{args.tile}.html';page.write_text(HTML.replace('TILE',args.tile))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    browsers=Path(os.environ['PLAYWRIGHT_BROWSERS_PATH'])
    executables=list(browsers.glob('chromium_headless_shell-*/chrome-*/chrome-headless-shell'))+list(browsers.glob('chromium-*/chrome-*/chrome'))+list(browsers.glob('chromium-*/chrome-*/*.app/Contents/MacOS/Google Chrome for Testing'))
    chromium=executables[0]
    for mode in ['aerial','edges','overlay','oblique']:
        target=OUTPUT/f'{mode}-{args.tile}.png'
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='010-debug-chromium-') as profile, tempfile.TemporaryFile() as log:
            command=[str(chromium),'--headless','--no-sandbox','--disable-dev-shm-usage','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--hide-scrollbars','--window-size=2500,2500','--force-device-scale-factor=1',f'--user-data-dir={profile}',f'--remote-debugging-port={port}',f'http://127.0.0.1:{server.server_port}/debug/{page.name}?mode={mode}']
            process=subprocess.Popen(command,stdout=log,stderr=log)
            try:
                subprocess.run(['node',str(Path(__file__).with_name('debug_capture.mjs')),str(port),str(target)],check=True,timeout=100)
            finally:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait()
        print(target,flush=True)
    server.shutdown()


if __name__=='__main__':main()
