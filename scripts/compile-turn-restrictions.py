#!/usr/bin/env python3
"""Compile the explicitly reviewed strict pilot subset, never all fuzzy matches."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'source-data/traffic'
audit=json.loads((SOURCE/'osm-turn-restriction-audit.json').read_bytes())
# Evidence reviewed: original IDs, exact street names, local segment orientation,
# source endpoint locations <=2m. Explicit allow-list prevents new refresh matches
# entering the runtime automatically without another review.
reviewed={4063857,11231184,11758547,11783357,13774733,14966195,18990384}
by_id={r['osmRelation']:r for r in audit['relations']}
rules=[]
for relation in sorted(reviewed):
 r=by_id[relation]
 if r['status']!='review-candidate' or relation not in audit['strictCandidateRelations']:raise SystemExit(f'Reviewed match no longer meets strict gates: {relation}')
 rules.append({'osmRelation':relation,'restriction':r['restriction'],'from':r['fromNWB'],'via':r['nwbJunction'],'to':r['toNWB'],'fromDirection':-1 if r['matches']['from']['nwbAtStart'] else 1,'toDirection':1 if r['matches']['to']['nwbAtStart'] else -1})
output={'version':1,'mode':'motorcar','license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','attributionUrl':'https://www.openstreetmap.org/copyright','source':'https://github.com/joshp123/010/tree/main/source-data/traffic','rawSourceSha256':audit['rawSha256'],'nwbSourceSha256':audit['nwbSha256'],'auditSha256':hashlib.sha256((SOURCE/'osm-turn-restriction-audit.json').read_bytes()).hexdigest(),'coverage':'Seven manually selected geometrically unambiguous pilot matches, not exhaustive legal routing; conditional and via-way restrictions unsupported','rules':rules}
(ROOT/'public/data/traffic/turn-restrictions.json').write_text(json.dumps(output,indent=2)+'\n')
print(f'Compiled {len(rules)} motorcar restriction rules')
