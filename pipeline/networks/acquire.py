"""Archive the M1 NWB source. Written by AI on 2026-10-26 by model GPT-6 Astra."""
import datetime
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SOURCE = ROOT / 'sources/nwb-networks/2026-10-26'
ENDPOINT = 'https://api.pdok.nl/rws/nationaal-wegenbestand-wegen/ogc/v1/collections/wegvakken/items'
PARAMETERS = {'f': 'json', 'bbox': '89750,434750,96500,438000',
              'bbox-crs': 'http://www.opengis.net/def/crs/EPSG/0/28992',
              'crs': 'http://www.opengis.net/def/crs/EPSG/0/28992', 'limit': 1000}


def main():
    SOURCE.mkdir(parents=True, exist_ok=True)
    manifest_path = SOURCE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'dataset': 'NWB wegvakken M1', 'license': 'CC0-1.0',
        'credit': 'Rijkswaterstaat / PDOK', 'files': {}}
    url = requests.Request('GET', ENDPOINT, params=PARAMETERS).prepare().url
    index = 0
    while url:
        name = f'page-{index:03}.json'
        path = SOURCE / name
        if path.exists():
            raw = path.read_bytes()
            assert manifest['files'][name]['url'] == url
            assert manifest['files'][name]['sha256'] == hashlib.sha256(raw).hexdigest()
        else:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            raw = response.content
            json.loads(raw)['features']
            path.write_bytes(raw)
            manifest['files'][name] = {'url': url, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
            manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        page = json.loads(raw)
        print(name, len(page['features']), flush=True)
        url = next((link['href'] for link in page['links'] if link['rel'] == 'next'), None)
        index += 1



def acquire_wkd():
    """Optional open RWS source explicitly authorised in the follow-up steering."""
    folder = ROOT / 'sources/network-wkd/2026-10-26'
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'license': 'CC0-1.0', 'credit': 'Rijkswaterstaat / NDW', 'files': []}
    entries = {entry['path']:entry for entry in manifest['files']}
    for name,url in [
        ('verkeerstypen.zip','https://downloads.rijkswaterstaatdata.nl/wkd/geogegevens/CSV-bestand/Verkeerstypen/01-10-2026.zip'),
        ('metadata.xml','https://www.nationaalgeoregister.nl/geonetwork/srv/api/records/85c23640-dea3-4a19-8620-4b9bf0cf8b89/formatters/xml')]:
        path=folder/name
        if path.exists():
            raw=path.read_bytes()
            assert entries[name]['sha256']==hashlib.sha256(raw).hexdigest()
        else:
            response=requests.get(url,timeout=120);response.raise_for_status();raw=response.content
            if name.endswith('.xml'):assert b'creativecommons.org/publicdomain/zero/1.0' in raw
            path.write_bytes(raw)
            entries[name]={'path':name,'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                           'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        manifest['files']=list(entries.values())
        manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')


if __name__ == '__main__':
    main()
    acquire_wkd()
