"""Written by AI on 2026-10-26 by model GPT-6 Astra. Persist native tool evidence."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--directory',type=Path,required=True)
parser.add_argument('--started',required=True)
parser.add_argument('--ended',required=True)
parser.add_argument('--prompt',type=Path,required=True)
args=parser.parse_args()
destination=args.directory/'generated-raw.png'
if destination.exists():
    raise FileExistsError(destination)
shutil.copy2(args.source,destination)
prompt=args.prompt.read_bytes()
(args.directory/'prompt-used.md').write_bytes(prompt)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
record={'written_by':'AI, GPT-6 Astra, 2026-10-26','tool':'image_gen.imagegen',
        'call_count':1,'started_at':args.started,'ended_at':args.ended,
        'elapsed_seconds':(datetime.fromisoformat(args.ended.replace('Z','+00:00'))-datetime.fromisoformat(args.started.replace('Z','+00:00'))).total_seconds(),
        'status':'completed-awaiting-verification','model':None,'model_version':None,
        'model_reporting':'Tool returned no model name or version.',
        'prompt_source':str(args.prompt),'prompt_sha256':hashlib.sha256(prompt).hexdigest(),
        'prompt_snapshot':str(args.directory/'prompt-used.md'),
        'reference':str(args.directory/'reference.png'),'reference_sha256':sha(args.directory/'reference.png'),
        'output_raw':str(destination),'output_original':str(args.source),'output_sha256':sha(destination),
        'rate_limits_observed':[],'verified':False}
(args.directory/'generation.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'saved':str(destination),'seconds':record['elapsed_seconds']}))
