#!/usr/bin/env python3
"""Retain exact dated orthophoto + native BGT for Schiedamseweg. Explicit acquisition."""
import urllib.request,urllib.parse,json,gzip,hashlib,datetime,argparse
from pathlib import Path
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/public-space-pilot';OUT.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--acquire',action='store_true');parser.add_argument('--year',default='2026',choices=['2025','2026']);args=parser.parse_args();year=args.year
x,y=Transformer.from_crs(4326,28992,always_xy=True).transform(4.44711,51.90963);x,y=round(x),round(y);span=128;bounds=[x-64,y-64,x+64,y+64];size=1600
q={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap','LAYERS':year+'_orthoHR','STYLES':'','CRS':'EPSG:28992','BBOX':','.join(map(str,bounds)),'WIDTH':size,'HEIGHT':size,'FORMAT':'image/jpeg'}
records=[('schiedamseweg-'+year+'.jpg','https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?'+urllib.parse.urlencode(q)),('33577-6934.b3dm.gz','https://www.3drotterdam.nl/datasource-data/0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/15/33577/6934.b3dm')]
for name,url in records:
 p=OUT/name;meta=p.with_suffix('.json')
 if p.exists():
  b=gzip.decompress(p.read_bytes()) if name.endswith('.gz') else p.read_bytes();assert hashlib.sha256(b).hexdigest()==json.loads(meta.read_text())['decodedSha256'];continue
 if not args.acquire:raise RuntimeError(f'Missing {p}; pass --acquire')
 with urllib.request.urlopen(url,timeout=90) as r:b=r.read()
 if b[:2]==b'\x1f\x8b':b=gzip.decompress(b)
 p.write_bytes(gzip.compress(b,mtime=0) if name.endswith('.gz') else b)
 record={'url':url,'acquiredAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'decodedSha256':hashlib.sha256(b).hexdigest(),'license':'CC BY 4.0','attribution':'Gemeente Rotterdam — 3D Rotterdam' if name.endswith('.gz') else 'Samenwerkingsverband Beeldmateriaal / PDOK — Luchtfoto '+year+' OrthoHR'}
 if name.endswith('.jpg'):record.update(boundsRD=bounds,imageSize=[size,size],pixelMetres=.08,layer=year+'_orthoHR',pixelCoordinates='top-left image edge=(minX,maxY); pixel centres at minX+(x+.5)*.08,maxY-(y+.5)*.08',licenseEvidence='../roof-ortho/license-publication.json')
 else:record['licenseEvidence']='../current-building-evidence/catalog-evidence.json'
 meta.write_text(json.dumps(record,indent=2)+'\n');print(name,len(b),flush=True)
