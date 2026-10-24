#!/usr/bin/env python3
"""Written by AI on 2026-10-24 by model GPT-6.
Quiet neighbouring land from official BRT sea boundaries; Shapely/pyproj only.
"""
import hashlib
import json
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union

PROJECT = Path(__file__).resolve().parents[1]
CACHE = PROJECT / 'work/data-cache/context-land'
OUTPUT = PROJECT / 'public/data/context-land.json'
API = 'https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1'
BOUNDS = [3.3, 51.4, 5.2, 52.4]
SIMPLIFICATION_METRES = 2
TO_RD = Transformer.from_crs(4326, 28992, always_xy=True).transform
TO_GEOGRAPHIC = Transformer.from_crs(28992, 4326, always_xy=True).transform


def acquire_json(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest()+'.json')
    metadata_path = path.with_suffix('.source.json')
    if not path.exists():
        with urlopen(url, timeout=90) as response:
            raw = response.read()
            headers = dict(response.headers)
        json.loads(raw)
        path.write_bytes(raw)
        metadata_path.write_text(json.dumps({'url':url,'retrievedAt':datetime.now(timezone.utc).isoformat(),'sha256':hashlib.sha256(raw).hexdigest(),'headers':headers},indent=2)+'\n')
    return json.loads(path.read_bytes()), json.loads(metadata_path.read_text())


def collection_url(collection, filter_text):
    return API+'/collections/'+collection+'/items?'+urlencode({'filter':filter_text,'filter-lang':'cql2-text','limit':1000,'f':'json'})


def main():
    # The western/northern frame intersects every marine coastal subdivision in
    # this regional extent. Inland tiny ditches are not another detail layer.
    west,south,east,north=BOUNDS
    frame=f'S_INTERSECTS(geometry,LINESTRING({west} {south},{west} {north},{east} {north}))'
    url=collection_url('waterdeel_vlak',frame)
    coastal_features=[]; sources=[]
    while url:
        page,metadata=acquire_json(url);sources.append(metadata)
        coastal_features.extend(page['features'])
        url=next((link['href']for link in page.get('links',[])if link['rel']=='next'),None)
    marine=[feature for feature in coastal_features if feature['properties'].get('typewater')=='zee']
    if not marine: raise ValueError('Official regional sea geometry is missing')
    clip=box(*BOUNDS)
    sea=unary_union([make_valid(shape(feature['geometry']))for feature in marine])
    candidates=clip.difference(sea)
    candidates=list(candidates.geoms)if candidates.geom_type=='MultiPolygon' else [candidates]
    land=[]; component_evidence=[]
    # BRT sea stops at its offshore coverage limit. A terrestrial BRT record at
    # each component's interior seed distinguishes land from unmapped offshore.
    for component in candidates:
        point=component.representative_point()
        query=collection_url('terrein_vlak',f'S_INTERSECTS(geometry,POINT({point.x} {point.y}))')
        page,metadata=acquire_json(query);sources.append(metadata)
        records=page['features']
        component_evidence.append({'seed':[point.x,point.y],'terrestrialSourceIds':[feature['id']for feature in records],'retained':bool(records)})
        if records:land.append(component)
    if not land:raise ValueError('No terrestrial source-confirmed land components')
    land=unary_union(land)
    boundary_bytes=(PROJECT/'public/data/municipality.json').read_bytes()
    boundary_collection=json.loads(boundary_bytes)
    municipality=unary_union([shape(feature['geometry'])for feature in boundary_collection['features']if feature['properties'].get('identificatie')=='GM0599'])
    if municipality.is_empty:raise ValueError('Rotterdam GM0599 is missing')
    # Retained full source records include the actual adjoining estuary/harbours.
    # Only major open water is useful in this deliberately quiet context.
    fetch_data=SourceFileLoader('context_source_fetch',str(PROJECT/'scripts/fetch-data.py')).load_module()
    municipal_water=fetch_data.read_collection('waterdeel_vlak',municipality.bounds)
    water=[]; water_records=[]
    for feature in {feature['id']:feature for feature in municipal_water+coastal_features}.values():
        appearance=str(feature['properties'].get('voorkomen')or'').lower()
        if any(word in appearance for word in ['duiker','overkluisd','op brug']):continue
        geometry=make_valid(shape(feature['geometry'])).intersection(clip)
        if geometry.is_empty:continue
        if feature['properties'].get('typewater')=='zee' or transform(TO_RD,geometry).area>=10000:
            water.append(geometry);water_records.append(feature)
    land=land.difference(unary_union(water))
    land=transform(TO_GEOGRAPHIC,transform(TO_RD,land).simplify(SIMPLIFICATION_METRES,preserve_topology=True)).intersection(clip)
    # Subtract the exact city last: no simplification may overwrite city water.
    land=land.difference(municipality)
    if land.is_empty or not land.is_valid:raise ValueError('Context geometry is empty or invalid')
    output={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'kind':'land'},'geometry':mapping(land)}],
        'source':API+'/collections/waterdeel_vlak','sourceScale':'BRT TOP10NL 1:10,000',
        'bounds':BOUNDS,'simplificationMetres':SIMPLIFICATION_METRES,'excludedMunicipality':'GM0599',
        'excludedBoundarySource':boundary_collection['source'],'excludedBoundarySha256':hashlib.sha256(boundary_bytes).hexdigest(),
        'license':'CC BY 4.0','licenseUrl':'https://creativecommons.org/licenses/by/4.0/','attribution':'Kadaster / PDOK, BRT TOP10NL; shoreline extraction and 2 m simplification.',
        'purpose':'Quiet source-derived coastal land outside Rotterdam. Exact municipal area has priority; surrounding open water below 1 hectare is omitted.',
        'provenance':'../../source-data/context-land.json'}
    OUTPUT.write_text(json.dumps(output,separators=(',',':'))+'\n')
    provenance={'writtenBy':'AI, GPT-6, 2026-10-24','sources':sources,'marineSourceIds':[feature['id']for feature in marine],
        'sourceWaterRecords':len(water_records),'sourceWaterSha256':hashlib.sha256(json.dumps(water_records,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'waterRecordDates':sorted({feature['properties'].get('bronactualiteit')for feature in water_records if feature['properties'].get('bronactualiteit')}),
        'componentEvidence':component_evidence,'sourceLicense':{'title':'CC BY 4.0','url':'https://creativecommons.org/licenses/by/4.0/'},
        'outputSha256':hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),'outputBytes':OUTPUT.stat().st_size,
        'validation':{'valid':land.is_valid,'municipalOverlapSquareDegrees':land.intersection(municipality).area,
            'marineOverlapSquareMetres':transform(TO_RD,land.intersection(sea)).area}}
    (PROJECT/'source-data/context-land.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'bytes':OUTPUT.stat().st_size,'marineFeatures':len(marine),'landComponents':len(land.geoms)if hasattr(land,'geoms')else 1,'componentCandidates':len(candidates),**provenance['validation']}))

if __name__=='__main__':main()
