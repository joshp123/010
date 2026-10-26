"""AHN heights and BRT physical form. Written by AI on 2026-10-26 by model GPT-6."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image
from shapely import STRtree
from shapely.geometry import shape,Point,box
from .build import BOUNDS,ROOT,SOURCE
from .sources import archive

AHN=ROOT/'sources/network-ahn/2026-10-26'
BRT=ROOT/'sources/overview-brt/2026-10-26'


class PhysicalForm:
    def __init__(self):
        self.groups={}
        self.used={}
        area=box(*BOUNDS).buffer(2500)
        for mode,types in {'tram':['tram'],'metro':['metro','sneltram'],'train':['trein']}.items():
            features=[]
            for file in sorted((BRT/'spoorbaandeel_lijn').glob('*.json')):
                for feature in json.loads(file.read_bytes())['features']:
                    props=feature['properties']
                    if props.get('typespoorbaan') in types and props.get('status')=='in gebruik' and shape(feature['geometry']).intersects(area):
                        features.append(feature)
            lines=[shape(f['geometry']) for f in features]
            self.groups[mode]=(STRtree(lines),lines,features)

    def classify(self,mode,a,b):
        if mode=='ferry':return 'water',None
        tree,lines,features=self.groups[mode]
        point=Point(a)
        dx,dy=b[0]-a[0],b[1]-a[1]
        norm=math.hypot(dx,dy)
        candidates=[]
        for index in tree.query(point.buffer(40)):
            line=lines[index]
            distance=point.distance(line)
            if distance>40:continue
            along=line.project(point)
            before,after=line.interpolate(max(0,along-5)),line.interpolate(min(line.length,along+5))
            ux,uy=after.x-before.x,after.y-before.y
            alignment=abs(dx*ux+dy*uy)/(max(.001,norm*math.hypot(ux,uy)))
            if alignment<.75:continue
            candidates.append((distance,int(index)))
        if not candidates:return 'unclassified',None
        _,index=min(candidates)
        feature=features[index]
        props=feature['properties']
        physical=props.get('fysiekvoorkomen') or ''
        self.used[feature['id']]={'physical':physical,'mode':mode,'relativeLevel':props.get('hoogteniveau'),'sourceId':props.get('lokaal_id')}
        if 'in tunnel' in physical:return 'tunnel',feature['id']
        if 'brug' in physical:return 'bridge',feature['id']
        return 'surface',feature['id']


class HeightSampler:
    def tile(self,x,y,coverage):
        # Reuse the network run's exact native-resolution source tiles where available.
        bx,by=math.floor(x/1000)*1000,math.floor(math.nextafter(y,-math.inf)/1000)*1000
        existing=AHN/f'{coverage}-{bx}-{by}.tif'
        if existing.exists():return existing
        bx,by=math.floor(x/500)*500,math.floor(math.nextafter(y,-math.inf)/500)*500
        params={'SERVICE':'WCS','VERSION':'1.0.0','REQUEST':'GetCoverage','COVERAGE':coverage,'CRS':'EPSG:28992','BBOX':f'{bx},{by},{bx+500},{by+500}','WIDTH':1000,'HEIGHT':1000,'FORMAT':'image/tiff'}
        from urllib.parse import urlencode
        url='https://service.pdok.nl/rws/ahn/wcs/v1_0?'+urlencode(params)
        return SOURCE/'ahn'/f'{coverage}-{bx}-{by}.tif',url

    def acquire(self,jobs):
        todo={}
        for x,y,coverage in jobs:
            tile=self.tile(x,y,coverage)
            if isinstance(tile,tuple):todo[tile[0]]=tile[1]
        def fetch(item):
            path,url=item
            result=archive(str(path.relative_to(SOURCE)),url,'CC0-1.0','AHN / Rijkswaterstaat / PDOK, 0.5 m DTM/DSM, NAP')
            with Image.open(result) as im:
                assert im.size==(1000,1000)
            return result
        with ThreadPoolExecutor(max_workers=4) as pool:
            for path in pool.map(fetch,sorted(todo.items())):print('AHN',path.name,flush=True)

    @staticmethod
    @lru_cache(maxsize=32)
    def read(path):
        with Image.open(path) as image:
            values=np.array(image,dtype=np.float32)
            scale=image.tag_v2[33550]
            tiepoint=image.tag_v2[33922]
        return values,scale,tiepoint

    def value(self,x,y,coverage,deck=False,nearest=False):
        tile=self.tile(x,y,coverage)
        path=tile[0] if isinstance(tile,tuple) else tile
        values,scale,tie=self.read(path)
        col=math.floor((x-tie[3])/scale[0]);row=math.floor((tie[4]-y)/scale[1])
        if nearest:
            r0,c0=max(0,row-4),max(0,col-4)
            window=values[r0:min(values.shape[0],row+5),c0:min(values.shape[1],col+5)]
            rr,cc=np.where(np.isfinite(window)&(np.abs(window)<10000))
            distances=(rr+r0-row)**2+(cc+c0-col)**2
            if not len(rr) or distances.min()>16:return None
            index=np.argmin(distances)
            return round(float(window[rr[index],cc[index]]),2)
        if deck:
            cells=values[max(0,row-6):min(values.shape[0],row+7),max(0,col-6):min(values.shape[1],col+7)].flatten()
        else:
            cells=values[row:row+1,col:col+1].flatten()
        cells=cells[np.isfinite(cells)&(np.abs(cells)<10000)]
        if not len(cells):return None
        return round(float(np.percentile(cells,2) if deck else cells[0]),2)
