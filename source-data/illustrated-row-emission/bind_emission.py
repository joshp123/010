from pathlib import Path
import json,struct,copy,shutil
R=Path(__file__).resolve().parent;A=R/'runtime-candidate';(A/'masks').mkdir(exist_ok=True)
b=(A/'row-review.glb').read_bytes();jl=struct.unpack_from('<I',b,12)[0];j=json.loads(b[20:20+jl]);binary=b[28+jl:]
lookup={}
for i,im in enumerate(list(j['images'])):
 if not im.get('uri','').startswith('textures/atlas-'):continue
 for kind in ['glazing-mask','glazing-phase','emission']:
  source=R/f'{kind}-{i:02}.png'
  if source.exists():shutil.copyfile(source,A/'masks'/source.name)
 source=R/f'emission-{i:02}.png'
 if not source.exists():continue
 j['images'].append({'uri':f'masks/emission-{i:02}.png'});j['textures'].append({'source':len(j['images'])-1,'sampler':2});lookup[i]=len(j['textures'])-1
for m in j['materials']:
 bc=m.get('pbrMetallicRoughness',{}).get('baseColorTexture')
 if bc is None:continue
 i=j['textures'][bc['index']]['source']
 if i in lookup:
  m['emissiveTexture']={'index':lookup[i]};m['emissiveFactor']=[0,0,0]
  m.setdefault('extras',{}).update({'glazingMask':f'masks/glazing-mask-{i:02}.png','glazingPhase':f'masks/glazing-phase-{i:02}.png','occupancy':'illustrative phase; not live observation','nightControl':'Set emissiveFactor from 0 to desired night intensity; supplied RGB texture already contains illustrative per-opening occupancy. Phase maps permit a separate dynamic occupancy shader.'})
def write(doc,path):
 js=json.dumps(doc,separators=(',',':')).encode();js+=b' '*((-len(js))%4)
 out=struct.pack('<III',0x46546c67,2,28+len(js)+len(binary))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(binary),0x004e4942)+binary;path.write_bytes(out)
write(j,A/'row-review.glb')
night=copy.deepcopy(j)
for m in night['materials']:
 if 'emissiveTexture' in m:m['emissiveFactor']=[1,1,1]
write(night,A/'row-review-night.glb')
shutil.copyfile(R/'glazing-features.json',A/'glazing-features.json')
print('bound emission maps to',len(lookup),'source atlas slots; geometry binary untouched')
