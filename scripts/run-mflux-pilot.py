#!/usr/bin/env python3
"""Pinned local Apple Silicon experiment. No model installation unless --run is given."""
import argparse, datetime, hashlib, json, os, platform, shutil, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COMMIT='a3b21fcaa88726b2267bd42bfc2e2d722f7d5a47'
REVISION='e7b7dc27f91deacad38e78976d1f2b499d76a294'
MODEL='black-forest-labs/FLUX.2-klein-4B'
# Pinned Flux2KleinWeightDefinition components; omit redundant root checkpoint.
DOWNLOAD_PATTERNS=['vae/*','transformer/*','text_encoder/*','tokenizer/*',
                   'scheduler/*','model_index.json','LICENSE*','README.md']
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ssd-root',type=Path,required=True);p.add_argument('--style',type=Path,required=True);p.add_argument('--style-status',default='reference only; not architectural evidence or output acceptance',help='Exact review status, e.g. unapproved candidate; never implied approval');p.add_argument('--run-name',default='facade-seed42');p.add_argument('--run',action='store_true');a=p.parse_args()
 if Path(a.run_name).name!=a.run_name: p.error('run-name must be a single path component')
 if not a.style.is_file():p.error('style must be an existing image supplied by manager/artworker')
 ssd=a.ssd_root.expanduser().resolve(); checkout=ssd/'mflux'/COMMIT; run=ssd/'runs'/a.run_name
 if run.exists():p.error('run folder already exists; use a new run-name to preserve earlier evidence')
 if a.run and (platform.system()!='Darwin' or platform.machine()!='arm64'):p.error('real execution requires Apple Silicon macOS; this cloud worker only prepares evidence')
 run.mkdir(parents=True); inp=run/'inputs';inp.mkdir();pilot=ROOT/'source-data/mflux-pilot'
 for name in ['source-panel.png','source.json','surface-map.npz','edit-mask.png','interpretation.txt']:shutil.copy2(pilot/name,inp/name)
 style=inp/('style'+a.style.suffix.lower());shutil.copy2(a.style,style)
 env=os.environ.copy();env.update(HF_HOME=str(ssd/'hf'),UV_CACHE_DIR=str(ssd/'uv-cache'),UV_PYTHON_INSTALL_DIR=str(ssd/'python'),UV_PROJECT_ENVIRONMENT=str(ssd/'venvs'/COMMIT),TOKENIZERS_PARALLELISM='false')
 snapshot=ssd/'models'/'FLUX.2-klein-4B'/REVISION
 cli=[str(Path(env['UV_PROJECT_ENVIRONMENT'])/'bin/mflux-generate-flux2-edit'),'--model',str(snapshot),'--base-model','flux2-klein-4b','--image-paths',str(inp/'source-panel.png'),str(style),'--prompt-file',str(inp/'interpretation.txt'),'--width','512','--height','1024','--steps','4','--seed','42','--quantize','8','--low-ram','--metadata','--output',str(run/'candidate.png')]
 record={'status':'prepared; no inference run','mfluxCommit':COMMIT,'model':MODEL,'modelRevision':REVISION,'modelLicense':'Apache-2.0','modelDownloadPatterns':DOWNLOAD_PATTERNS,'styleStatus':a.style_status,'inputs':{f.name:sha(f) for f in inp.iterdir()},'command':cli,'cacheEnvironment':{k:env[k] for k in ['HF_HOME','UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','UV_PROJECT_ENVIRONMENT']},'createdUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'pythonRequested':'3.13','publication':'No automatic UV bake or runtime mutation; generated output requires architectural review'}
 (run/'provenance.json').write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record,indent=2))
 if not a.run:return
 def call(cmd,**kw):subprocess.run(cmd,check=True,env=env,**kw)
 try:
  if not checkout.exists():
   checkout.parent.mkdir(parents=True,exist_ok=True);call(['git','clone','--filter=blob:none','https://github.com/mflux-community/mflux.git',str(checkout)])
  call(['git','checkout','--detach',COMMIT],cwd=checkout)
  record['upstreamUvLockSha256']=sha(checkout/'uv.lock')
  audit=json.loads((pilot/'upstream-audit.json').read_text())
  if record['upstreamUvLockSha256']!=audit['upstreamUvLockSha256']:raise RuntimeError('Upstream lock differs from retained audit')
  call(['uv','sync','--project',str(checkout),'--frozen','--no-dev','--python','3.13'])
  python=Path(env['UV_PROJECT_ENVIRONMENT'])/'bin/python'
  download='from huggingface_hub import snapshot_download; import sys,json; snapshot_download(repo_id=sys.argv[1],revision=sys.argv[2],local_dir=sys.argv[3],allow_patterns=json.loads(sys.argv[4]))'
  call([str(python),'-c',download,MODEL,REVISION,str(snapshot),json.dumps(DOWNLOAD_PATTERNS)])
  record['modelFiles']={str(f.relative_to(snapshot)):sha(f) for f in snapshot.rglob('*') if f.is_file() and '.cache' not in f.parts}
  record['resolvedPackages']=subprocess.check_output(['uv','pip','freeze','--python',str(python)],env=env,text=True)
  record['platform']=platform.platform();record['pythonVersion']=subprocess.check_output([str(python),'--version'],text=True).strip()
  env['HF_HUB_OFFLINE']='1'
  with (run/'inference.log').open('w') as log:call(cli,stdout=log,stderr=subprocess.STDOUT)
  if not (run/'candidate.png').is_file():raise RuntimeError('CLI returned without output; inspect inference.log')
  record['outputSha256']=sha(run/'candidate.png');record['status']='inference completed; unreviewed architectural/art candidate'
 except Exception as exc:
  record['status']='failed';record['error']=str(exc);raise
 finally:(run/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
if __name__=='__main__':main()
