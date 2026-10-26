"""Written by AI on 2026-10-26 by model GPT-6 Astra.

One oblique, offline inspection of the assembled GLB with its actual materials.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.server
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
from urllib.parse import unquote, urlparse

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
REPOSITORY = Path(__file__).resolve().parents[2]
HTML = '''<!doctype html><meta charset="utf-8"><style>html,body{margin:0;overflow:hidden;background:#deded7}canvas{display:block}</style>
<script type="importmap">{"imports":{"three":"/repo/web/vendor/three/build/three.module.js","three/addons/":"/repo/web/vendor/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
try {
 const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
 renderer.setSize(2500,2500);renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.setClearColor(0xdedfd9);
 document.body.appendChild(renderer.domElement);
 const scene=new THREE.Scene();scene.add(new THREE.HemisphereLight(0xffffff,0xd1c9b6,2));
 const sun=new THREE.DirectionalLight(0xffffff,1.8);sun.position.set(-100,400,200);scene.add(sun);
 const gltf=await new GLTFLoader().loadAsync('/asset/buildings.glb');scene.add(gltf.scene);
 const box=new THREE.Box3().setFromObject(gltf.scene);const center=box.getCenter(new THREE.Vector3());
 const extent=box.getSize(new THREE.Vector3());const span=Math.max(extent.x,extent.z)*1.25;
 const camera=new THREE.OrthographicCamera(-span/2,span/2,span/2,-span/2,.1,5000);
 camera.position.set(center.x+span*.85,span*.8,center.z+span*.65);camera.lookAt(center.x,8,center.z);
 renderer.render(scene,camera);window.renderComplete=true;document.title='READY';
} catch(e){document.body.innerText=e.stack;document.title='FAILED';}
</script>'''


def render(glb, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    page = output.with_suffix('.html')
    page.write_text(HTML)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def translate_path(self, request_path):
            path = unquote(urlparse(request_path).path)
            if path == '/asset/buildings.glb':
                return str(glb)
            if path.startswith('/repo/'):
                return str(REPOSITORY / path[len('/repo/'):])
            return str(page)

        def log_message(self, *args):
            pass

        def copyfile(self, source, destination):
            try:
                super().copyfile(source, destination)
            except (BrokenPipeError, ConnectionResetError):
                pass

    browser_root = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    roots = [Path(browser_root)] if browser_root else list(Path('/nix/store').glob('*playwright-browsers*'))
    executables = []
    for root in roots:
        executables += list(root.glob('chromium_headless_shell-*/chrome-*/chrome-headless-shell'))
        executables += list(root.glob('chromium-*/chrome-*/*.app/Contents/MacOS/Google Chrome for Testing'))
        executables += list(root.glob('chromium-*/chrome-*/chrome'))
    if not executables:
        raise FileNotFoundError('Run in devenv shell: Chromium is required for the offline GLB inspection.')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='010-asset-check-') as profile, tempfile.TemporaryFile() as log:
            command = [str(executables[0]), '--headless', '--no-sandbox', '--disable-dev-shm-usage',
                       '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
                       '--hide-scrollbars', '--window-size=2500,2500', '--force-device-scale-factor=1',
                       f'--user-data-dir={profile}', f'--remote-debugging-port={port}',
                       f'http://127.0.0.1:{server.server_port}/debug/{page.name}']
            process = subprocess.Popen(command, stdout=log, stderr=log)
            try:
                subprocess.run(['node', str(REPOSITORY / 'pipeline/buildings/debug_capture.mjs'),
                                str(port), str(output)], check=True, timeout=180)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    finally:
        server.shutdown()
    output.with_suffix('.json').write_text(json.dumps({
        'written_by': 'AI, GPT-6 Astra, 2026-10-26',
        'date': datetime.now(timezone.utc).isoformat(), 'glb': str(glb),
        'glb_sha256': hashlib.sha256(glb.read_bytes()).hexdigest(),
        'image': str(output), 'view': 'one oblique inspection with the GLB original axes and actual embedded materials',
        'viewport_px': [2500, 2500]}, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--glb', type=Path, default=ROOT / 'assets/v1/tiles/x90250_y436000/buildings.glb')
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/v1/tiles/x90250_y436000/check-oblique.png')
    args = parser.parse_args()
    render(args.glb, args.output)
