#!/usr/bin/env python3
# Written by AI on 2026-10-25 by model GPT-6 Astra.
import argparse,pathlib,json,gzip,struct,hashlib,io
from PIL import Image,ImageChops
ap=argparse.ArgumentParser(description='Verify actual compiled municipal pack geometry and sampled decoded mip pixels');ap.add_argument('directory',type=pathlib.Path);args=ap.parse_args();root=args.directory;m=json.loads((root/'manifest.json').read_text());wire=0;expanded=0;images=0
for ordinal,(uri,r) in enumerate(m['tiles'].items()):
 raw=(root/'raw'/uri).read_bytes();wire+=len(raw);raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;expanded+=len(raw);assert hashlib.sha256(raw).hexdigest()==r['sourceSha256']
 with (root/r['pack']).open('rb') as f:f.seek(r['offset']);packed=f.read(r['length'])
 assert hashlib.sha256(packed).hexdigest()==r['gzipSha256'];derived=gzip.decompress(packed);assert hashlib.sha256(derived).hexdigest()==r['derivedSha256'];off=28+sum(struct.unpack_from('<4I',raw,12));assert raw[12:off]==derived[12:off]
 def parse(b):
  b=b[off:];n=struct.unpack_from('<I',b,12)[0];return json.loads(b[20:20+n]),b[28+n:]
 a,ab=parse(raw);b,bb=parse(derived)
 assert all(a.get(k)==b.get(k) for k in ['accessors','meshes','nodes','scenes','scene'])
 imageviews={im['bufferView'] for im in a['images']}
 for vi,av in enumerate(a['bufferViews']):
  if vi in imageviews:continue
  bv=b['bufferViews'][vi];assert ab[av.get('byteOffset',0):av.get('byteOffset',0)+av['byteLength']]==bb[bv.get('byteOffset',0):bv.get('byteOffset',0)+bv['byteLength']]
 # Inspect decoded image identity at beginning/middle/end of the whole area.
 if ordinal in [0,len(m['tiles'])//2,len(m['tiles'])-1]:
  for ai,bi in zip(a['images'],b['images']):
   av=a['bufferViews'][ai['bufferView']];bv=b['bufferViews'][bi['bufferView']];original=Image.open(io.BytesIO(ab[av.get('byteOffset',0):av.get('byteOffset',0)+av['byteLength']]));original.thumbnail((256,256),Image.Resampling.BOX);actual=Image.open(io.BytesIO(bb[bv.get('byteOffset',0):bv.get('byteOffset',0)+bv['byteLength']])).convert('RGBA');assert ImageChops.difference(original.convert('RGBA'),actual).getbbox() is None;images+=1
report={'tiles':len(m['tiles']),'packs':len(m['packs']),'sourceWireBytes':wire,'sourceExpandedBytes':expanded,'derivedGzipBytes':sum(v['bytes'] for v in m['packs'].values()),'allGeometryAccessorsNodesUVsFeatureBatchTablesExact':True,'decodedImagesComparedWithExactBOX256':images,'imageSampling':'First/middle/last tile, all images on each; finalnative source remains original URL','bbox':m['bbox']};(root/'preservation-check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
