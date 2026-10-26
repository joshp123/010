"""Draw output over the 2026 aerial. Written by AI on 2026-10-26 by model GPT-6."""
import argparse
import json
import math
from pathlib import Path
import requests
from PIL import Image,ImageDraw,ImageFont
from shapely import line_merge, set_precision
from shapely.ops import unary_union
from shapely.geometry import LineString, box
from .build import ROOT,SOURCE,BOUNDS,OUTPUT,parts
from .sources import archive

RENDERS=ROOT/'renders/debug-transit'
COLORS={'tram':'#ff4cbd','metro':'#00eaff','train':'#ffe252','ferry':'#8bff75'}


def aerial(bounds,resolution):
    width=round((bounds[2]-bounds[0])/resolution)
    height=round((bounds[3]-bounds[1])/resolution)
    image=Image.new('RGB',(width,height))
    for y in range(0,height,2000):
        for x in range(0,width,2000):
            w,h=min(2000,width-x),min(2000,height-y)
            b=(bounds[0]+x*resolution,bounds[3]-(y+h)*resolution,bounds[0]+(x+w)*resolution,bounds[3]-y*resolution)
            params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap','LAYERS':'2026_orthoHR','STYLES':'','CRS':'EPSG:28992','BBOX':','.join(map(str,b)),'WIDTH':w,'HEIGHT':h,'FORMAT':'image/jpeg'}
            url=requests.Request('GET','https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0',params=params).prepare().url
            name='aerial/'+'_'.join(map(str,(*b,resolution)))+'.jpg'
            source=archive(name,url,'CC-BY-4.0','Beeldmateriaal.nl / PDOK, 2026_orthoHR')
            with Image.open(source) as tile:image.paste(tile,(x,y))
    return image


def font(size):
    return ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',size)


def render(name,bounds,resolution,lines):
    raw=aerial(bounds,resolution)
    overlay=raw.copy()
    draw=ImageDraw.Draw(overlay)
    def pixel(p):return ((p[0]-bounds[0])/resolution,(bounds[3]-p[1])/resolution)
    area=box(*bounds)
    for mode in ('ferry','train','tram','metro'):
        segments={False:[],True:[]}
        for line in lines:
            if line['mode']!=mode:continue
            for path in line['paths']:
                if not LineString([p[:2] for p in path]).intersects(area):continue
                for a,b in zip(path,path[1:]):
                    tunnel=bool(len(a)>3 and (a[3] or b[3]))
                    segments[tunnel].append(LineString([a[:2],b[:2]]))
        # Shared lines/directions must not paint over each other's dash gaps.
        for tunnel,geometries in segments.items():
            if not geometries:continue
            merged=line_merge(unary_union([set_precision(g,.1) for g in geometries]))
            for geometry in parts(merged):
                phase=0
                coordinates=list(geometry.coords)
                for a,b in zip(coordinates,coordinates[1:]):
                    aa,bb=pixel(a),pixel(b)
                    length=math.dist(aa,bb)
                    if not tunnel:
                        draw.line([aa,bb],fill=COLORS[mode],width=1 if resolution==.5 else 2)
                    elif length:
                        for offset in range(math.ceil(length)):
                            if (phase+offset)%12<7:
                                t0,t1=offset/length,min(1,(offset+1)/length)
                                draw.line([(aa[0]+(bb[0]-aa[0])*t0,aa[1]+(bb[1]-aa[1])*t0),(aa[0]+(bb[0]-aa[0])*t1,aa[1]+(bb[1]-aa[1])*t1)],fill=COLORS[mode],width=1 if resolution==.5 else 2)
                    phase=(phase+round(length))%12
    panels=[raw,overlay] if resolution==.5 else [overlay]
    banner=92
    result=Image.new('RGB',(len(panels)*raw.width,raw.height+banner),'#14212b')
    label=ImageDraw.Draw(result)
    for i,panel in enumerate(panels):
        result.paste(panel,(i*raw.width,banner))
        label.text((i*raw.width+12,8),f'{name} | {resolution} m/pixel | '+('2026 aerial' if len(panels)>1 and i==0 else 'Transit paths'),fill='white',font=font(17))
        label.text((i*raw.width+12,34),'Pink: tram | cyan: metro (dashed tunnel) | yellow: train | green: ferry',fill='white',font=font(13))
        label.text((i*raw.width+12,58),'North up | Aerial: Beeldmateriaal.nl / PDOK (CC BY 4.0)',fill='white',font=font(13))
        x,y=i*raw.width+15,result.height-25
        label.line([(x,y),(x+100/resolution,y)],fill='white',width=3)
        label.text((x,y-20),'100 m',fill='white',stroke_width=1,stroke_fill='black',font=font(13))
    RENDERS.mkdir(parents=True,exist_ok=True)
    output=RENDERS/f'{name}-{resolution}m.png'
    result.save(output)
    print(output,flush=True)
    return str(output)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--planar',action='store_true')
    args=parser.parse_args()
    lines=json.loads((SOURCE/'planar.json').read_text()) if args.planar else json.loads((OUTPUT/'transit.json').read_text())['lines']
    render('m1-plus-2km',BOUNDS,2,lines)
    render('delfshaven',(89950,435950,90450,436350),.5,lines)


if __name__=='__main__':main()
