"""Read delivered files against the scene contract. Written by AI on 2026-10-25 by model GPT-6.1 Sol.1 Sol."""
import hashlib,json,struct
import numpy as np
from PIL import Image
from archive import ROOT
from build import AREAS

def check(area='m0'):
 report=json.loads((ROOT/f'scene/v1/ground-{area}-report.json').read_text())
 x0,y0,x1,y1=AREAS[area];total_triangles=0;total_bytes=0
 for y in range(y0,y1,250):
  for x in range(x0,x1,250):
   name=f'x{x}_y{y}';directory=ROOT/'scene/v1/tiles'/name;record=report['tiles'][name]['ground']
   photo=Image.open(directory/'ortho.jpg');assert photo.size==(2500,2500) and photo.format=='JPEG',name
   mask=Image.open(directory/'classes.png');assert mask.size==(2500,2500) and mask.mode=='RGBA',name
   rgba=np.asarray(mask);assert rgba[:,:,0].max()<=16 and rgba[:,:,1].max()<=15 and not rgba[:,:,2].any() and np.all(rgba[:,:,3]==255),name
   actual_counts=np.bincount(rgba[:,:,0].ravel(),minlength=17)
   assert actual_counts.tolist()==[record['class_pixels'][str(i)] for i in range(17)],name
   body=(directory/'ground.glb').read_bytes();magic,version,size=struct.unpack_from('<4sII',body);assert(magic,version,size)==(b'glTF',2,len(body)),name
   json_size=struct.unpack_from('<I',body,12)[0];g=json.loads(body[20:20+json_size]);binary=body[28+json_size:]
   primitive=g['meshes'][0]['primitives'][0];attributes=primitive['attributes']
   positions=g['accessors'][attributes['POSITION']];view=g['bufferViews'][positions['bufferView']]
   vertices=np.frombuffer(binary,dtype='<f4',count=positions['count']*3,offset=view.get('byteOffset',0)).reshape(-1,3)
   assert np.isfinite(vertices).all() and vertices[:,0].min()>=-.001 and vertices[:,0].max()<=250.001 and vertices[:,2].min()>=-250.001 and vertices[:,2].max()<=.001,name
   assert vertices[:,1].min()>=-10 and vertices[:,1].max()<100,name
   class_accessor=g['accessors'][attributes['_CLASS']];assert class_accessor['count']==positions['count'] and class_accessor['componentType']==5121,name
   class_view=g['bufferViews'][class_accessor['bufferView']];vertex_classes=np.frombuffer(binary,dtype='u1',count=class_accessor['count'],offset=class_view.get('byteOffset',0));assert vertex_classes.max()<=16,name
   assert positions['count']//3==record['ground_triangles'],name
   for filename,metadata in record['files'].items():
    data=(directory/filename).read_bytes();assert hashlib.sha256(data).hexdigest()==metadata['sha256'],(name,filename)
    total_bytes+=len(data)
   total_triangles+=record['ground_triangles']
 print(json.dumps({'area':area,'tiles_checked':len(report['tiles']),'ground_triangles':total_triangles,'delivered_bytes':total_bytes,'class_shares':report['class_shares'],'uncovered_nonbuilding_ground_m2':sum(r['ground']['ground_uncovered_nonbuilding_area_m2'] for r in report['tiles'].values())},indent=2))
if __name__=='__main__':
 import sys
 check(sys.argv[1] if len(sys.argv)>1 else 'm0')
