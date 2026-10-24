#!/usr/bin/env python3
"""Compile the explicitly reviewed strict source subset, never all fuzzy matches."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'source-data/traffic'
parser=argparse.ArgumentParser();parser.add_argument('--pilot',action='store_true',help='Reproduce the original central ten-rule subset');args=parser.parse_args()
audit_path=SOURCE/('osm-turn-restriction-audit.json' if args.pilot else 'osm-municipality-turn-audit.json')
audit=json.loads(audit_path.read_bytes())
# Evidence reviewed: original IDs, exact street names or proven short source-name continuations, local segment orientation,
# source endpoint locations <=2m. Explicit allow-list prevents new refresh matches
# entering the runtime automatically without another review.
reviewed={1312594,14966194,14966196,4063857,11231184,11758547,11783357,13774733,14966195,18990384}
if not args.pilot:
 review=json.loads((SOURCE/'osm-municipality-turn-review.json').read_bytes())
 if review['auditSha256']!=hashlib.sha256(audit_path.read_bytes()).hexdigest() or review['rawSourceSha256']!=audit['rawSha256']:raise SystemExit('Municipal audit changed; explicit source review must be renewed')
 if audit.get('coverageComplete') is not True:raise SystemExit('Municipal review requires complete acquisition')
 reviewed=set(review['selectedRelations'])
by_id={r['osmRelation']:r for r in audit['relations']}
rules=[]
for relation in sorted(reviewed):
 r=by_id[relation]
 if r['status']!='review-candidate' or relation not in audit['strictCandidateRelations']:raise SystemExit(f'Reviewed match no longer meets strict gates: {relation}')
 rules.append({'osmRelation':relation,'restriction':r['restriction'],'from':r['fromNWB'],'via':r['nwbJunction'],'to':r['toNWB'],'fromDirection':-1 if r['matches']['from']['nwbAtStart'] else 1,'toDirection':1 if r['matches']['to']['nwbAtStart'] else -1})
output={'version':1,'mode':'motorcar','license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','attributionUrl':'https://www.openstreetmap.org/copyright','source':'https://github.com/joshp123/010/tree/main/source-data/traffic','rawSourceSha256':audit['rawSha256'],'nwbSourceSha256':audit['nwbSha256'],'auditSha256':hashlib.sha256(audit_path.read_bytes()).hexdigest(),'coverage':f'{len(rules)} explicitly reviewed source matches across '+('the central pilot' if args.pilot else 'municipality acquisition')+'; not exhaustive legal routing; conditional and via-way restrictions unsupported','rules':rules}
(ROOT/'public/data/traffic/turn-restrictions.json').write_text(json.dumps(output,indent=2)+'\n')
print(f'Compiled {len(rules)} motorcar restriction rules')
