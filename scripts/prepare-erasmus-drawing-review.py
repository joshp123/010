#!/usr/bin/env python3
"""Place the retained source-bound bridge drawing in the existing city frame.
Written by AI on 2026-10-25 by model GPT-6 Astra.
"""
import json,struct
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1];folder=root/'public/data/erasmus-structure-drawing';raw=(folder/'structure.glb').read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);position_indices={p['attributes']['POSITION'] for mesh in doc['meshes'] for p in mesh['primitives']};bounds=np.array([(doc['accessors'][i]['min'],doc['accessors'][i]['max']) for i in position_indices]);lo=bounds[:,0].min(0);hi=bounds[:,1].max(0);centre=(lo+hi)/2;half=(hi-lo)/2;template=json.loads((root/'public/data/bridge-surfaces/tileset.json').read_text());box=[centre[0],-centre[2],centre[1],half[0],0,0,0,half[2],0,0,0,half[1]]
(folder/'tileset.json').write_text(json.dumps({'asset':{'version':'1.1'},'geometricError':0,'root':{'transform':template['root']['transform'],'boundingVolume':{'box':box},'geometricError':0,'content':{'uri':'structure.glb'}}},indent=2)+'\n')
