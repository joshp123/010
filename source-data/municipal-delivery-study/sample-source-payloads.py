# Written by AI on 2026-10-25 by model GPT-6 Astra.
import urllib.request,json,gzip,concurrent.futures,pathlib,struct,io,time,hashlib
from PIL import Image
out=pathlib.Path(__file__).resolve().parent;d=json.loads((out/'hierarchy-census.json').read_text());base=d['source'];samples=[]
for i in range(len(d['subtrees'])):
 r=d['subtrees'][i]
 for lev in (['15','18'] if i in [0,3,9,16,21,28,32,35] else ['18']):
  a=[u for u in r['contents'] if u.startswith(lev+'/')];samples.append((r['uri'],a[len(a)//2]))
def inspect(item):
 subtree,uri=item;t=time.monotonic();wire=urllib.request.urlopen(base+uri,timeout=90).read();download_seconds=time.monotonic()-t;b=gzip.decompress(wire) if wire[:2]==b'\x1f\x8b' else wire
 off=28+sum(struct.unpack_from('<4I',b,12));g=b[off:];n=struct.unpack_from('<I',g,12)[0];doc=json.loads(g[20:20+n]);binary=g[28+n:];sizes={str(s):0 for s in [128,256,512]};native=0;pixels=0
 for im in doc.get('images',[]):
  v=doc['bufferViews'][im['bufferView']];raw=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];native+=len(raw);img=Image.open(io.BytesIO(raw)).convert('RGBA');pixels+=img.width*img.height
  for size in [128,256,512]:
   copy=img.copy();copy.thumbnail((size,size),Image.Resampling.BOX);buf=io.BytesIO();copy.save(buf,format='WEBP',lossless=True,method=4);sizes[str(size)]+=min(len(raw),len(buf.getvalue()))
 row={'subtree':subtree,'uri':uri,'wireBytes':len(wire),'expandedBytes':len(b),'imageBytes':native,'geometryAndMetadataBytes':len(b)-native,'imageCount':len(doc.get('images',[])),'pixels':pixels,'mipImageBytes':sizes,'wireSha256':hashlib.sha256(wire).hexdigest(),'downloadSeconds':round(download_seconds,3),'decodeAndEncodeSeconds':round(time.monotonic()-t-download_seconds,3),'seconds':round(time.monotonic()-t,2)};print(json.dumps(row),flush=True);return row
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(inspect,samples))
(out/'payload-samples.json').write_text(json.dumps({'method':'One median-order finest tile from each of40 source subtrees, plus8 level15 tiles; not probability sample. Mip image totals use BOX resize+losslessWebP, keeping smaller original. Geometry/metadata unchanged.','samples':rows},indent=2))
