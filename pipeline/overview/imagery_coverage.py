"""Measure white aerial gaps inside GM0599. Written by AI, GPT-6, 2026-10-26."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import label, find_objects
from shapely.geometry import shape, box
ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE=ROOT/'scene/overview-v1'
index=json.loads((SCENE/'tile-index.json').read_text())
boundary=shape(index['boundary_rd'])
inside_count=0
white_inside_count=0
large_count=0
class_counts=np.zeros(256,dtype=np.int64)
records={}
for tile_id,record in index['tiles'].items():
    x,y,xmax,ymax=record['bounds_rd']
    clipped=boundary.intersection(box(x,y,xmax,ymax))
    mask=Image.new('1',(1000,1000));draw=ImageDraw.Draw(mask)
    polygons=[clipped] if clipped.geom_type=='Polygon' else [p for p in clipped.geoms if p.geom_type=='Polygon']
    for polygon in polygons:
        draw.polygon([(a-x,ymax-b) for a,b in polygon.exterior.coords],fill=1)
        for hole in polygon.interiors:
            draw.polygon([(a-x,ymax-b) for a,b in hole.coords],fill=0)
    inside=np.asarray(mask)
    photo=np.asarray(Image.open(SCENE/'tiles'/tile_id/'ortho.jpg'))
    white=np.all(photo>=250,axis=2)&inside
    inside_count+=int(inside.sum());white_inside_count+=int(white.sum())
    labels,number=label(white)
    sizes=np.bincount(labels.ravel());sizes[0]=0
    selected=np.flatnonzero(sizes>=10000)
    if len(selected):
        large=int(sizes[selected].sum());large_count+=large
        class_path=SCENE/'tiles'/tile_id/'classes.png'
        if class_path.exists():
            classes=np.asarray(Image.open(class_path))[:,:,0]
            class_counts[:]+=np.bincount(classes[np.isin(labels,selected)],minlength=256)
        records[tile_id]={'white_inside_m2':int(white.sum()),'large_white_components_m2':large,'largest_component_m2':int(sizes.max())}
report={'method':'Rasterize exact GM0599 polygon at 1 m (including holes). Near-white source pixels have all RGB >=250. Large components have >=10,000 connected pixels within an individual tile. These identify visible missing-source areas; bright roofs may also contribute to small white-pixel totals.', 'boundary_inside_raster_m2':inside_count,'near_white_inside_m2':white_inside_count,'large_white_components_inside_m2':large_count,'large_white_fraction_of_municipality':large_count/inside_count,'tiles_with_large_white_components':records,'classes_under_large_white_components':{str(i):int(n) for i,n in enumerate(class_counts) if n}}
(SCENE/'imagery-coverage-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
