"""Written by AI on 2026-10-26 by GPT-6 Astra. Drawn miniature parts; no photo pixels."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def seed_number(value):
    return int.from_bytes(hashlib.sha256(str(value).encode()).digest()[:8], 'little')


def load_library(directory):
    manifest_path = Path(directory)/'library.json'
    if not manifest_path.exists():
        return {'parts': [], 'path': str(directory)}
    result = json.loads(manifest_path.read_text())
    result['path'] = str(directory)
    return result


def part_image(library, kind, seed, subtype=None):
    candidates = [p for p in library.get('parts', []) if p['kind'] == kind and not p.get('applies_to_wall')
                  and (subtype is None or p.get('type') == subtype)]
    if not candidates:
        return None
    part = sorted(candidates, key=lambda p: p['path'])[seed_number(seed) % len(candidates)]
    path = Path(library['path'])/part['path']
    return Image.open(path).convert('RGB') if path.exists() else None


def restore_mean(image, colour):
    pixels = np.asarray(image, dtype=float)
    target = np.asarray(colour, dtype=float)
    for _ in range(5):
        pixels = np.clip(pixels + target-pixels.mean(axis=(0, 1)), 0, 255)
    return Image.fromarray(np.rint(pixels).astype(np.uint8))


def material_tile(colour, material='brick', seed='', size=(64, 64), library=None):
    """5 cm pixels: ordinary brick is four pixels long and 1-2 pixels high."""
    library = library or {'parts': []}
    swatch = part_image(library, 'material', seed, material)
    if swatch is not None:
        canvas = Image.new('RGB', size)
        for y in range(0, size[1], swatch.height):
            for x in range(0, size[0], swatch.width):
                canvas.paste(swatch, (x, y))
        return restore_mean(canvas, colour)
    if max(size) > 64:
        swatch = material_tile(colour, material, seed, (64,64), library)
        canvas = Image.new('RGB',size)
        for y in range(0,size[1],64):
            for x in range(0,size[0],64):
                canvas.paste(swatch,(x,y))
        return canvas
    rng = np.random.default_rng(seed_number(seed))
    target = np.asarray(colour, dtype=float)
    pixels = np.zeros((size[1], size[0], 3), dtype=float)+target
    # The surface is varied by material units, rather than television/static noise.
    if material == 'brick':
        for row, y in enumerate(range(0, size[1], 2)):
            for x in range(-4, size[0], 5):
                left = x+(row % 2)*2
                a, b = max(0,left), min(size[0],left+5)
                if a >= b:
                    continue
                shift = rng.choice([-8, -4, -2, 0, 0, 2, 4, 7])
                pixels[y:min(y+2,size[1]),a:b] += shift
                pixels[y,a:b] += 2
                if y+1 < size[1]:
                    pixels[y+1,max(a,b-1):b] += 9
        pixels += rng.integers(-1, 2, pixels.shape[:2])[...,None]
    else:
        broad = rng.integers(-3, 4, ((size[1]+7)//8, (size[0]+7)//8))
        variation = np.repeat(np.repeat(broad,8,axis=0),8,axis=1)[:size[1],:size[0]]
        pixels += variation[...,None]
        pixels += rng.integers(-1,2,pixels.shape[:2])[...,None]
    return restore_mean(Image.fromarray(np.uint8(np.clip(pixels,0,255))), colour)


def opening_part(size, kind, window_type, seed, library=None):
    library = library or {'parts': []}
    style_type = window_type if window_type not in ('unknown','other',None) else 'unknown'
    source = part_image(library, kind, seed, style_type)
    if source is not None:
        return source.resize(size, Image.Resampling.NEAREST), 'generated-part'
    width, height = size
    rng = np.random.default_rng(seed_number(seed))
    canvas = Image.new('RGB', size, (31,32,34))
    draw = ImageDraw.Draw(canvas)
    frame = tuple(int(v) for v in (np.array([195,190,170])+rng.integers(-8,9)))
    if kind == 'door':
        colour = tuple(int(v) for v in (np.array([51,61,58])+rng.integers(-10,11)))
        draw.rectangle((1,1,width-2,height-2),fill=colour)
        if width > 5 and height > 14:
            draw.rectangle((2,2,width-3,max(3,height//3)), fill=(42,48,50))
            draw.line((2,height//2,width-3,height//2),fill=(28,36,34))
            draw.rectangle((2,height//2+2,width-3,height-4),outline=tuple(min(255,c+13) for c in colour))
            draw.point((max(1,width-3),height*3//5),fill=(157,132,74))
    else:
        draw.rectangle((1,1,width-2,height-2),fill=frame)
        draw.rectangle((2,2,width-3,height-3),fill=(48,57,62))
        for y in range(3,max(3,height-3)):
            shift = int(7*y/max(1,height))
            draw.line((3,y,width-4,y),fill=(46+shift,55+shift,61+shift))
        # Minimal reflected pixels provide craft without extra architectural mullions.
        if width > 9 and height > 12:
            draw.line((3,3,3,max(3,height//2)),fill=(94,109,112))
            draw.line((4,3,min(width-4,7),3),fill=(112,120,117))
            draw.rectangle((width-5,height-7,width-4,height-4),fill=(34,42,46))
        if window_type == 'sash_with_transom':
            y = max(3,round(height*.30))
            draw.line((2,y,width-3,y),fill=frame,width=1)
            draw.line((width//2,y,width//2,height-3),fill=frame,width=1)
        elif window_type == 'casement':
            draw.line((width//2,2,width//2,height-3),fill=frame,width=1)
        # Unknown types have no invented internal divisions.
        if height > 5:
            draw.line((1,height-2,width-2,height-2),fill=tuple(min(255,c+16) for c in frame))
    return canvas, 'drawn-part-interpretation'


def cornice_part(size, kind, colour, seed, library=None):
    library = library or {'parts': []}
    source = part_image(library, 'cornice', seed, kind)
    if source is not None:
        return source.resize(size, Image.Resampling.NEAREST), 'generated-part'
    canvas = Image.new('RGB', size, tuple(int(v) for v in colour))
    draw = ImageDraw.Draw(canvas)
    for y, shift in ((0,15),(size[1]//3,-9),(size[1]-1,-24)):
        draw.line((0,y,size[0]-1,y),fill=tuple(int(max(0,min(255,c+shift))) for c in colour))
    return canvas, 'drawn-part-interpretation'


def component_part(size, component, seed, library):
    kind, subtype = component['kind'], component.get('type','unknown')
    colour = component.get('mean_colour_srgb',[160,155,150])
    if component.get('panes_px'):
        canvas = Image.new('RGB',size,tuple(int(min(255,c+60)) for c in colour))
        origin = component['box_px'][:2]
        for index,pane in enumerate(component['panes_px']):
            left,top,right,bottom = map(int,pane)
            part,_ = opening_part((right-left,bottom-top),'window','unknown',str(seed)+str(index),library)
            canvas.paste(part,(left-origin[0],top-origin[1]))
        return canvas,'generated-window-parts-at-individually-source-measured-pane-bounds'
    scoped = [p for p in library.get('parts',[]) if p.get('applies_to_wall') == component.get('wall_id')
              and p.get('applies_to_rectangle_px') == component.get('box_px')]
    source = (Image.open(Path(library['path'])/scoped[0]['path']).convert('RGB') if scoped
              else part_image(library,kind,seed,subtype))
    if source is not None:
        result = source.resize(size,Image.Resampling.NEAREST)
        # Preserve dark/light detail while honouring scalar colour for surface bands.
        if scoped or kind not in ('balcony','glazing_strip'):
            result = restore_mean(result,colour)
        return result,'generated-part-at-source-reviewed-bounds'
    if kind == 'cornice':
        return cornice_part(size,subtype,colour,seed,library)
    return material_tile(colour,'plaster/render',seed,size,library), 'drawn-scalar-colour-band-interpretation'
