#!/usr/bin/env python3
"""Retain exact regional WKD permission rows plus missing NWB geometries.
No geometry conflation: join only on WVK_ID. Existing runtime is not changed.
"""
import argparse,csv,datetime,gzip,hashlib,io,json,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/traffic'
URL='https://downloads.rijkswaterstaatdata.nl/wkd/geogegevens/CSV-bestand/Verkeerstypen/01-10-2026.zip'
def sha(data): return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--archive',type=Path);p.add_argument('--download',action='store_true');a=p.parse_args()
 if a.archive: payload=a.archive.read_bytes()
 elif a.download:
  with urllib.request.urlopen(URL,timeout=60) as response: payload=response.read()
 else: p.error('Use --archive path.zip or --download. Compilation later requires neither.')
 archive=zipfile.ZipFile(io.BytesIO(payload));entry=next(n for n in archive.namelist() if n.lower().endswith('.csv'));definition=archive.read(next(n for n in archive.namelist() if n.endswith('Definitie.txt')))
 existing={str(f['properties']['wvk_id']):f for file in ['nwb-roads.geojson.gz','nwb-cycleways.geojson.gz'] for f in json.loads(gzip.decompress((SOURCE/file).read_bytes()))['features']}
 pages=sorted((ROOT/'work/data-cache/traffic').glob('nwb-rotterdam-*.json'))
 if not pages or any(l['rel']=='next' for l in json.loads(pages[-1].read_bytes())['links']): raise SystemExit('First acquisition requires complete municipal NWB pages (build-traffic.py --download).')
 municipal={str(f['properties']['wvk_id']):f for page in pages for f in json.loads(page.read_bytes())['features']}
 raw=archive.read(entry);reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';');rows=[r for r in reader if r['WVK_ID'] in municipal]
 out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=reader.fieldnames,delimiter=';',lineterminator='\r\n');writer.writeheader();writer.writerows(rows)
 selected=gzip.compress(out.getvalue().encode(),mtime=0);(SOURCE/'wkd-cycling-access.csv.gz').write_bytes(selected)
 extra=[municipal[r['WVK_ID']] for r in rows if r['WVK_ID'] not in existing and 'J' in (r['FIETS_H'],r['FIETS_T'])]
 extra_payload=gzip.compress(json.dumps({'type':'FeatureCollection','features':extra},separators=(',',':')).encode(),mtime=0);(SOURCE/'nwb-cycling-access-extra.geojson.gz').write_bytes(extra_payload)
 (SOURCE/'wkd-cycling-definition.txt').write_bytes(definition)
 report={'source':URL,'retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'license':'CC0-1.0','licenseSource':'https://data.overheid.nl/dataset/73747-wegkenmerkendatabase-voor-verkeerstypen','schema':'https://docs.ndw.nu/handleidingen/wkd/wkd_verkeerstypen/','archiveSha256':sha(payload),'archiveEntry':entry,'csvSha256':sha(raw),'selectedRows':len(rows),'municipalNWBFeatures':len(municipal),'additionalNWBFeatures':len(extra),'selectedCsvSha256':sha(selected),'extraNWBSha256':sha(extra_payload),'snapshotDate':'2026-10-07','snapshotDateEvidence':'Peildatum in retained archive Definitie.txt','join':'exact WVK_ID only; NWB feature dates newer than snapshot excluded by compiler; matching publication editions not established','sourceCaveats':['NDW reports incomplete updates and known bicycle direction/parallel-path errors; this is source evidence, not verified legal routing.','No turn restrictions, time conditions or complete surveyed elevation.'],'rawNWBPageSha256':{p.name:sha(p.read_bytes()) for p in pages}}
 (SOURCE/'cycling-access-provenance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rawNWBPageSha256'},indent=2))
if __name__=='__main__':main()
