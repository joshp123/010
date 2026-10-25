#!/usr/bin/env python3
"""Written by AI, GPT-6 Astra, 2026-10-25. Retain official bridge evidence."""
import concurrent.futures,datetime,hashlib,json,urllib.parse,urllib.request
from pathlib import Path
from pyproj import Transformer
OUTPUT=Path(__file__).resolve().parents[1]/'source-data/erasmus-public-space'
OUTPUT.mkdir(parents=True,exist_ok=True)
def fetch_collection(collection):
    target=OUTPUT/(collection+'.json')
    if target.exists():return
    url='https://api.pdok.nl/kadaster/bgt/ogc/v1/collections/'+collection+'/items?'+urllib.parse.urlencode(dict(bbox='4.479,51.904,4.494,51.916',datetime='2026-10-24T00:00:00Z',limit=1000,f='json'))
    features=[];requests=[]
    while url:
        raw=urllib.request.urlopen(url,timeout=90).read();page=json.loads(raw)
        requests.append(dict(url=url,sha256=hashlib.sha256(raw).hexdigest()));features.extend(page['features'])
        url=next((link['href'] for link in page.get('links',[]) if link['rel']=='next'),None)
    target.write_text(json.dumps(dict(type='FeatureCollection',sourceRequests=requests,features=features),separators=(',',':'))+'\n')
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch_collection,['wegdeel','spoor','ondersteunendwegdeel']))
if not (OUTPUT/'ortho2026.jpg').exists():
    x,y=Transformer.from_crs(4326,28992,always_xy=True).transform(4.4855,51.9093);bounds=[x-390,y-490,x+390,y+490]
    url='https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?'+urllib.parse.urlencode(dict(SERVICE='WMS',VERSION='1.3.0',REQUEST='GetMap',LAYERS='2026_orthoHR',STYLES='',CRS='EPSG:28992',BBOX=','.join(map(str,bounds)),WIDTH=1560,HEIGHT=1960,FORMAT='image/jpeg'))
    raw=urllib.request.urlopen(url,timeout=90).read();(OUTPUT/'ortho2026.jpg').write_bytes(raw)
    (OUTPUT/'ortho2026.source.json').write_text(json.dumps(dict(url=url,sha256=hashlib.sha256(raw).hexdigest(),boundsRD=bounds,imageSize=[1560,1960],pixelMetres=.5,acquiredAt=datetime.datetime.now(datetime.timezone.utc).isoformat(),license='CC BY 4.0',attribution='Samenwerkingsverband Beeldmateriaal / PDOK — 2026 OrthoHR'),indent=2)+'\n')
