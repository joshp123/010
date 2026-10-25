"""Reproduce ground alignment evidence. Written by AI on 2026-10-25 by model GPT-6.1 Sol.

Reads the archived municipal ground, current BGT vectors and built class mask.
Writes only debug images and a report. Never modifies production scene files.
"""
import json
import struct
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import Point, shape
from shapely.ops import unary_union
import geometry
from archive import ROOT, DATE


def quantiles(distances):
    return dict(zip(['minimum','p10','p25','median','p75','p90','maximum'],
       map(float,np.quantile(distances,[0,.1,.25,.5,.75,.9,1]))))



def delivered_ground_coverage(tile_name, output):
    tile_path=ROOT/'scene/v1/tiles'/tile_name
    body=(tile_path/'ground.glb').read_bytes()
    json_size=struct.unpack_from('<I',body,12)[0]
    document=json.loads(body[20:20+json_size])
    binary=body[28+json_size:]
    coverage_image=Image.new('1',(2500,2500),0)
    draw=ImageDraw.Draw(coverage_image)
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            positions=geometry._accessor(document,binary,primitive['attributes']['POSITION'])
            if 'indices' in primitive:
                indices=geometry._accessor(document,binary,primitive['indices']).ravel()
                positions=positions[indices]
            for triangle in positions.reshape(-1,3,3):
                first=triangle[1,[0,2]]-triangle[0,[0,2]]
                second=triangle[2,[0,2]]-triangle[0,[0,2]]
                if abs(first[0]*second[1]-first[1]*second[0])<=1e-8:continue
                draw.polygon([(float(vertex[0])*10,(250+float(vertex[2]))*10) for vertex in triangle],fill=1)
    coverage=np.asarray(coverage_image,dtype=bool)
    classes=np.asarray(Image.open(tile_path/'classes.png'))[:,:,0]
    missing=(~coverage)&(classes!=11)
    photograph=np.asarray(Image.open(tile_path/'ortho.jpg').convert('RGB')).copy()
    photograph[missing]=(photograph[missing]*0.3+np.array([255,0,0])*0.7).astype(np.uint8)
    image_path=output/(tile_name+'-delivered-ground-coverage.png')
    Image.fromarray(photograph).save(image_path)
    by_class={str(int(class_id)):{'missing_m2':float(((classes==class_id)&missing).sum()/100),
        'fraction_of_class_missing':float(((classes==class_id)&missing).sum()/max((classes==class_id).sum(),1))}
        for class_id in np.unique(classes) if class_id!=11}
    return {'tile':tile_name,'overlay':str(image_path),'red_overlay':'Delivered ground mesh absent on nonbuilding class pixels',
       'missing_nonbuilding_area_m2':float(missing.sum()/100),
       'missing_nonbuilding_fraction':float(missing.sum()/max((classes!=11).sum(),1)),
       'missing_by_surface_class':by_class}


def main():
    source_report=geometry.prepare_geometry((89750,435750,90750,436750))
    triangles=geometry._TRIANGLES
    native_classes=geometry._SOURCE_CLASSES
    mask_path=ROOT/'scene/v1/tiles/x90250_y436000/classes.png'
    class_map=np.asarray(Image.open(mask_path))[:,:,0]
    if class_map.shape!=(2500,2500):raise ValueError(f'Wrong class raster size: {class_map.shape}')
    water_records=[]
    for path in sorted((ROOT/'sources/bgt'/DATE/'waterdeel').glob('m0-buffer-page*.json')):
        water_records.extend(json.loads(path.read_text())['features'])
    current_water=unary_union([shape(feature['geometry']) for feature in water_records
        if not feature['properties'].get('eind_registratie')
        and not feature['properties'].get('termination_date')
        and feature['properties'].get('status')=='bestaand'
        and feature['properties'].get('relatieve_hoogteligging',0)>=0])
    if current_water.is_empty:raise ValueError('No current archived BGT water features')
    vertices=np.unique(np.round(triangles[native_classes==8].reshape(-1,3),4),axis=0)
    focal=vertices[(vertices[:,0]>90250)&(vertices[:,0]<90500)&(vertices[:,1]>436000)&(vertices[:,1]<436250)]
    vector_distances=np.array([current_water.boundary.distance(Point(vertex[:2])) for vertex in focal])
    raster_water=class_map==8
    raster_edge=raster_water & ~ndimage.binary_erosion(raster_water,border_value=1)
    distance_pixels=ndimage.distance_transform_edt(~raster_edge)
    columns=np.clip(((focal[:,0]-90250)*10).astype(int),0,2499)
    rows=np.clip(((436250-focal[:,1])*10).astype(int),0,2499)
    raster_distances=distance_pixels[rows,columns]/10
    source_heights=triangles[native_classes==8][:,:,2]
    dates_min=[tile['survey_date_min'] for tile in source_report['tiles'] if tile['survey_date_min']]
    dates_max=[tile['survey_date_max'] for tile in source_report['tiles'] if tile['survey_date_max']]
    report={'focal_tile':'x90250_y436000','native_water_vertex_count':len(focal),
       'native_water_vertices_to_current_bgt_vector_boundary_distance_m':quantiles(vector_distances),
       'native_water_vertices_to_built_water_raster_edge_distance_m':quantiles(raster_distances),
       'built_class_mask':str(mask_path),'built_water_class_fraction':float(raster_water.mean()),
       'raster_comparison_resolution_m':0.1,
       'source_survey_date_min':min(dates_min),'source_survey_date_max':max(dates_max),
       'source_water_height_range_m':[float(source_heights.min()),float(source_heights.max())],
       'source_height_datum_evidence':source_report['height_datum_evidence'],
       'limitations':['Horizontal comparison tests stable water boundaries, not every ground feature.',
          'Municipal mesh surveys predate the 2026 photo and current BGT.',
          'Height datum is inferred from source numeric encoding, not independently surveyed.',
          'Raster-edge distances include 10cm raster quantisation and bridge masking.'],
       'source_archive':str(ROOT/'sources/ground3d'/DATE),
       'current_bgt_archive':str(ROOT/'sources/bgt'/DATE/'waterdeel')}
    # 500m square, north up: native municipal water in blue, current BGT edge red.
    xmin,ymin,size,pixels_per_metre=90000,436000,500,3
    image=Image.new('RGB',(size*pixels_per_metre,size*pixels_per_metre),'#eeeeee')
    draw=ImageDraw.Draw(image)
    def screen(vertex):return ((vertex[0]-xmin)*pixels_per_metre,(ymin+size-vertex[1])*pixels_per_metre)
    for triangle in triangles[native_classes==8]:
        if triangle[:,0].max()<xmin or triangle[:,0].min()>xmin+size or triangle[:,1].max()<ymin or triangle[:,1].min()>ymin+size:continue
        draw.polygon([screen(vertex) for vertex in triangle],fill='#7788ff')
    polygons=[current_water] if current_water.geom_type=='Polygon' else list(current_water.geoms)
    for polygon in polygons:
        draw.line([screen(vertex) for vertex in polygon.exterior.coords],fill='red',width=2)
        for interior in polygon.interiors:draw.line([screen(vertex) for vertex in interior.coords],fill='red',width=2)
    output=ROOT/'renders/debug-ground';output.mkdir(parents=True,exist_ok=True)
    image.save(output/'ground-water-boundary-probe.png')
    report['delivered_ground_coverage']=[delivered_ground_coverage(tile,output) for tile in ['x90250_y436000','x90000_y436000']]
    (output/'ground-water-alignment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
