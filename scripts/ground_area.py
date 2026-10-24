"""Small file-based area specification shared by the ground preparation commands."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
def resolve_area(path):
 if not path:return None
 p=Path(path);p=p if p.is_absolute() else ROOT/p
 a=json.loads(p.read_text());assert a['id'] and len(a['boundsRD'])==4
 assert a['boundsRD'][2]>a['boundsRD'][0] and a['boundsRD'][3]>a['boundsRD'][1]
 for extent,pixels in zip([a['boundsRD'][2]-a['boundsRD'][0],a['boundsRD'][3]-a['boundsRD'][1]],a['imageSize']):assert abs(extent/pixels-a['pixelMetres'])<1e-9
 for key in ['sourceDirectory','workDirectory','outputDirectory','nativeTile','nativeMetadata','materialSwatches']:a[key]=ROOT/a[key]
 a['sourceDirectory'].mkdir(parents=True,exist_ok=True);a['workDirectory'].mkdir(parents=True,exist_ok=True)
 return a
