#!/usr/bin/env python3
"""Bind model-drawn materials and retained observed paint to surveyed surfaces.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

parser = argparse.ArgumentParser()
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--drawing', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
metadata = json.loads((args.runtime/'work/public-space-neighbourhood/source-mask.json').read_text())
source = np.load(args.runtime/'work/public-space-neighbourhood/source-mask.npz')
features = source['feature']
height, width = features.shape
pixel_metres = (metadata['boundsRD'][2]-metadata['boundsRD'][0])/width
rows, columns = np.indices((height, width))
drawing = Image.open(args.drawing).convert('RGB')
panel_width, panel_height = drawing.width//2, drawing.height//2
patches = []
for x, y, patch_metres in [(0, 0, 16), (1, 0, 4), (0, 1, 1.6), (1, 1, 4)]:
    # Scale model material units to the observed surface: broad asphalt tones,
    # sub-metre stone joints and small brick units, never metre-wide paving.
    panel = drawing.crop((x*panel_width, y*panel_height, (x+1)*panel_width, (y+1)*panel_height))
    patches.append(np.array(panel.resize((round(patch_metres/pixel_metres),)*2, Image.Resampling.BOX), dtype=float))

rgb = np.zeros((height, width, 3), dtype=float)
material = np.zeros((height, width), dtype=np.uint8)
source_ids = []
for record in metadata['features']:
    mask = features == record['batchId']
    if not mask.any():
        continue
    kind = int(source['surface'][mask][0])
    if not kind:
        continue
    attributes = record['attributes']
    physical = attributes.get('FYSIEKVK', '').lower()
    purpose = attributes.get('FUNCTIE', '').lower()
    if purpose == 'fietspad':
        kind = 2
    elif 'open verharding' in physical and purpose in {'rijbaan lokale weg', 'parkeervlak'}:
        kind = 6
    elif purpose == 'ov-baan':
        kind = 7
    material[mask] = kind
    source_ids.append(str(attributes.get('DGDT_ID', record['id'])))
    if kind == 5:
        # No observed waves, tidal state or depth are inferred from an aerial.
        rgb[mask] = [67, 87, 91]
        continue
    patch_index = {1:0, 2:2, 3:1, 4:3, 6:2, 7:2}[kind]
    patch = patches[patch_index]
    points = np.column_stack(np.nonzero(mask))[:, ::-1].astype(float)
    axis = np.linalg.eigh(np.cov(points.T))[1][:, -1] if len(points)>2 else np.array([1., 0.])
    along = columns*axis[0] + rows*axis[1]
    across = -columns*axis[1] + rows*axis[0]
    def mirrored_index(coordinate, size):
        coordinate = np.floor(coordinate).astype(int) % (2*size)
        return np.where(coordinate < size, coordinate, 2*size-1-coordinate)
    field = patch[mirrored_index(across, patch.shape[0]), mirrored_index(along, patch.shape[1])]
    rgb[mask] = field[mask]

eligible = material > 0
# Retain exact already-reviewed paint support, without interpreting dark aerial
# pixels as markings or transferring any model-created geographic detail.
previous = np.array(Image.open(args.runtime/'public/data/ground-artwork-neighbourhood-v3/neighbourhood-ground.png').convert('RGBA'))
paint = np.all(previous[:, :, :3] == [222, 219, 200], axis=2) & eligible
rgb[paint] = [222, 219, 200]

# Native shared feature boundaries remain the only edge geometry. No invented
# grids, extra curbs or duplicate texture outline is introduced here.
nearest = ndimage.distance_transform_edt(~eligible, return_distances=False, return_indices=True)
rgb[~eligible] = rgb[nearest[0][~eligible], nearest[1][~eligible]]
rgba = np.dstack((np.clip(rgb, 0, 255).astype('uint8'), eligible.astype('uint8')*255))
args.output.mkdir(parents=True, exist_ok=True)
Image.fromarray(rgba).save(args.output/'neighbourhood-ground.png')
manifest = {key:metadata[key] for key in ['boundsRD', 'imageSize', 'worldToImageUV', 'sourceDecodedSha256', 'orthophotoSha256', 'projectionMaximumErrorPixels']}
manifest.update(status='review-candidate', texture='neighbourhood-ground.png', sourceFeatureIds=source_ids,
    drawingSha256=hashlib.sha256(args.drawing.read_bytes()).hexdigest(),
    interpretation='Model-drawn ground materials bound to exact surveyed feature footprints and physical classes. Existing reviewed source road-paint support retained. No model-created geographic objects transfer.',
    notSurveyed='Small drawn surface marks describe material only; individual paving joints and wear are not surveyed objects.',
    acceptance='Pending complete adjoining-city opposing desktop and phone review.')
(args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(args.output)
