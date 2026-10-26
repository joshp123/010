"""Raw byte archives. Written by AI on 2026-10-25 by model GPT-6.1 Sol."""
import datetime, hashlib, json, threading, time, fcntl
from contextlib import contextmanager
from pathlib import Path
import requests
ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
DATE='2026-10-25'
LOCK=threading.Lock()
LICENSES={
 'bgt':('CC0-1.0','Kadaster / PDOK / BGT source holders'),
 'ortho2026':('CC-BY-4.0','Samenwerkingsverband Beeldmateriaal / PDOK — Luchtfoto 2026'),
 'ground3d':('public domain','Gemeente Rotterdam — Rotterdam 3D'),
 'proj-grids':('CC-BY-4.0','NSGI / PROJ-data')}
@contextmanager
def manifest_lock(folder):
 folder.mkdir(parents=True,exist_ok=True)
 with LOCK, (folder/'.manifest.lock').open('a') as lock_file:
  fcntl.flock(lock_file,fcntl.LOCK_EX)
  yield

def fetch(dataset,name,url):
 folder=ROOT/'sources'/dataset/DATE; path=folder/name
 with manifest_lock(folder):
  manifest_path=folder/'manifest.json'
  manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {'dataset':dataset,'license':LICENSES[dataset][0],'credit':LICENSES[dataset][1],'files':{}}
  if path.exists() and name in manifest['files']:
   if manifest['files'][name]['url']!=url:raise ValueError(f'Archive name reused for different URL: {path}')
   return path.read_bytes()
 for attempt in range(4):
  try:
   response=requests.get(url,timeout=120);response.raise_for_status();data=response.content;break
  except requests.RequestException:
   if attempt==3:raise
   time.sleep(2**attempt)
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
 with manifest_lock(folder):
  manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else manifest
  manifest['files'][name]={'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  temp=manifest_path.with_suffix('.tmp');temp.write_text(json.dumps(manifest,indent=2));temp.replace(manifest_path)
 return data
