#!/usr/bin/env python3
"""Fetch pinned, unmodified browser dependencies from the official npm registry."""
import io
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    'three': ('0.186.1', [
        'LICENSE', 'build/three.module.js', 'build/three.core.js',
        'examples/jsm/loaders/GLTFLoader.js', 'examples/jsm/utils/BufferGeometryUtils.js',
        'examples/jsm/utils/SkeletonUtils.js',
    ]),
    '3d-tiles-renderer': ('0.5.3', [
        'LICENSE', 'build/index.three.js', 'build/index.core.js', 'build/renderer-CUfHAmYW.js', 'build/renderer-_7gAivIK.js',
    ]),
}
for package, (version, files) in PACKAGES.items():
    url = f'https://registry.npmjs.org/{package}/-/{package}-{version}.tgz'
    with urllib.request.urlopen(url) as response:
        archive_bytes = response.read()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:gz') as archive:
        for filename in files:
            output = ROOT / 'dist' / 'vendor' / package / filename
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.extractfile(f'package/{filename}').read())
    print(f'{package} {version}: {len(files)} files')
