"""Acquire faithful OSM M1 source. Written by AI on 2026-10-26 by GPT-6 Astra.

Run in devenv, with ephemeral osmium-tool supplied by Nix if unavailable:
  devenv shell -- nix shell nixpkgs#osmium-tool --command python pipeline/networks/osm_source.py
No road eligibility or graph topology is inferred here.
"""
import datetime
import gzip
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from pyproj import Transformer

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SOURCE = ROOT / 'sources/network-osm/2026-10-26'
URL = 'https://download.geofabrik.de/europe/netherlands/zuid-holland-261025.osm.pbf'
BBOX = [89750, 434750, 96500, 438000]
BUFFER = 500


def fingerprint(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return {'path': path.name, 'bytes': path.stat().st_size, 'sha256': sha.hexdigest()}


def main():
    SOURCE.mkdir(parents=True, exist_ok=True)
    raw_path = SOURCE / URL.rsplit('/', 1)[1]
    manifest_path = SOURCE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'dataset': 'OpenStreetMap Zuid-Holland via Geofabrik',
        'license': 'ODbL-1.0', 'license_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
        'attribution': '© OpenStreetMap contributors',
        'attribution_url': 'https://www.openstreetmap.org/copyright',
        'download_page': 'https://download.geofabrik.de/europe/netherlands/zuid-holland.html',
        'source_data_timestamp': '2026-10-25T21:21:21Z', 'files': []}
    if not raw_path.exists():
        response = requests.get(URL, stream=True, timeout=120)
        response.raise_for_status()
        with raw_path.open('wb') as stream:
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)
        manifest['http_last_modified'] = response.headers.get('Last-Modified')
    raw_record = fingerprint(raw_path)
    # Geofabrik publishes the MD5 independently; validate even a cached download.
    checksum_url = URL + '.md5'
    checksum = requests.get(checksum_url, timeout=60)
    checksum.raise_for_status()
    expected = checksum.text.split()[0]
    md5 = hashlib.md5()
    with raw_path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            md5.update(chunk)
    if expected != md5.hexdigest():
        raise ValueError('Geofabrik MD5 does not match source file')
    raw_record.update(url=URL, checksum_url=checksum_url, md5=expected,
                      acquired_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    manifest['files'] = [raw_record]
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    osmium = shutil.which('osmium')
    if not osmium:
        raise RuntimeError('Supply osmium-tool with the documented Nix command')
    manifest['osmium_version'] = subprocess.check_output([osmium, '--version'], text=True).splitlines()[0]
    to_wgs = Transformer.from_crs(28992, 4326, always_xy=True)
    corners = [to_wgs.transform(x, y) for x in (BBOX[0]-BUFFER, BBOX[2]+BUFFER)
               for y in (BBOX[1]-BUFFER, BBOX[3]+BUFFER)]
    geographic_bbox = [min(p[0] for p in corners), min(p[1] for p in corners),
                       max(p[0] for p in corners), max(p[1] for p in corners)]
    extract_path = SOURCE / 'm1-buffer.osm.pbf'
    extract_command = [osmium, 'extract', '-s', 'smart', '-S', 'types=restriction',
                       '-b', ','.join(map(str, geographic_bbox)), str(raw_path), '-o', str(extract_path)]
    if not extract_path.exists():
        subprocess.run(extract_command, check=True)
    print('OSM extract complete', flush=True)
    process = subprocess.Popen([osmium, 'cat', str(extract_path), '-f', 'osm'], stdout=subprocess.PIPE)
    nodes, node_tags, ways, restrictions = {}, {}, [], []
    to_rd = Transformer.from_crs(4326, 28992, always_xy=True)
    for event, element in ET.iterparse(process.stdout, events=('end',)):
        if element.tag not in ('node', 'way', 'relation'):
            continue
        object_id = int(element.attrib['id'])
        tags = {child.attrib['k']: child.attrib['v'] for child in element.findall('tag')}
        if element.tag == 'node':
            nodes[object_id] = list(to_rd.transform(float(element.attrib['lon']), float(element.attrib['lat'])))
            if tags:
                node_tags[object_id] = tags
        elif element.tag == 'way':
            ways.append({'id': object_id, 'refs': [int(child.attrib['ref']) for child in element.findall('nd')], 'tags': tags})
        elif tags.get('type') == 'restriction':
            restrictions.append({'id': object_id, 'tags': tags, 'members': [
                {'type': child.attrib['type'], 'ref': int(child.attrib['ref']), 'role': child.attrib['role']}
                for child in element.findall('member')]})
        element.clear()
    if process.wait():
        raise RuntimeError('osmium XML export failed')
    highway_ids = {way['id'] for way in ways if 'highway' in way['tags']}
    restrictions = [relation for relation in restrictions if any(
        member['type'] == 'way' and member['ref'] in highway_ids for member in relation['members'])]
    relation_way_ids = {member['ref'] for relation in restrictions for member in relation['members'] if member['type'] == 'way'}
    ways = [way for way in ways if way['id'] in highway_ids | relation_way_ids]
    required_nodes = {node for way in ways for node in way['refs']}
    required_nodes.update(member['ref'] for relation in restrictions for member in relation['members'] if member['type'] == 'node')
    missing_nodes = sorted(required_nodes - nodes.keys())
    if missing_nodes:
        raise ValueError(f'Incomplete OSM node references: {len(missing_nodes)}')
    missing_ways = relation_way_ids - {way['id'] for way in ways}
    if missing_ways:
        raise ValueError(f'Incomplete restriction way references: {len(missing_ways)}')
    output = {'bbox_rd': BBOX, 'buffer_m': BUFFER, 'extract_bbox_wgs84': geographic_bbox,
              'nodes': {node: coords for node, coords in nodes.items() if node in required_nodes},
              'node_tags': {node: tags for node, tags in node_tags.items() if node in required_nodes},
              'ways': ways, 'restrictions': restrictions}
    output_path = SOURCE / 'm1-buffer.json.gz'
    with gzip.open(output_path, 'wt', encoding='utf-8') as stream:
        json.dump(output, stream, separators=(',', ':'))
    manifest['files'].extend([fingerprint(extract_path), fingerprint(output_path)])
    manifest['extract'] = {'bbox_rd': BBOX, 'buffer_m': BUFFER, 'bbox_wgs84': geographic_bbox,
        'strategy': 'osmium smart, complete highway ways and restriction relations',
        'nodes': len(output['nodes']), 'ways': len(ways), 'restrictions': len(restrictions),
        'coordinates': 'EPSG:28992 metres; full precision; original OSM way node order preserved'}
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest['extract']), flush=True)


if __name__ == '__main__':
    main()
