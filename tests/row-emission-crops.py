#!/usr/bin/env python3
"""Source texel identity and out-of-crop zero equivalence, no GPU claim."""
import json,struct,hashlib
from pathlib import Path
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1];out=R/'public/data/illustrated-row';m=json.loads((out/'emission-manifest.json').read_text());b=(out/'row.glb').read_bytes();n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);assert hashlib.sha256(b[28+n:]).hexdigest()==m['geometryBinarySha256']
for entry in m['sourceBindings']:
 i=entry['baseColorImage'];original=np.array(Image.open(R/f'source-data/illustrated-row-emission/masks/emission-{i:02}.png').convert('RGB'));mat=d['materials'][entry['material']]
 if entry.get('empty'):assert not np.any(original);assert 'emissiveTexture' not in mat;continue
 crop=np.array(Image.open(out/d['images'][entry['emissionImage']]['uri']).convert('RGB'));x0,y0,x1,y1=entry['crop'];restored=np.zeros_like(original);restored[y0:y1,x0:x1]=crop;np.testing.assert_array_equal(original,restored)
 ys,xs=np.nonzero(np.any(original>0,axis=2));uv=np.c_[(xs+.5)/2048,(ys+.5)/2048];t=entry['textureTransform'];mapped=uv*t['scale']+t['offset'];coords=np.floor(mapped*[crop.shape[1],crop.shape[0]]).astype(int);np.testing.assert_array_equal(crop[coords[:,1],coords[:,0]],original[ys,xs]);assert mat['extras']['emissionCropGuard'];assert np.all((mapped>=0)&(mapped<=1));assert entry['material']!=(9)
assert d['textures'][d['materials'][10]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']==9
print('All nonzero original texels sample identically through UV transform; reconstructed full images exact, empty07 omitted, geometry binary unchanged')
