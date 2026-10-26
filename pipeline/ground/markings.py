"""Municipal marking vectors; written by AI on 2026-10-25 by model GPT-6.1 Sol.

The municipal endpoint is public, but publishes no licence in iteminfo or
metadata. This is recorded explicitly, not relabelled as CC0. Lines encode
width in centimetres (B10) and dash/gap lengths in metres. Dashed lines are
continuous survey axes: their dash phase is NOT recorded. The aerial photo
therefore determines the actual painted pixels inside that narrow support.
Polygon parking areas are whole zones, not white paint; point symbols have
no orientation. Neither is filled with invented paint geometry.
"""
import json
import re
from urllib.parse import urlencode

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import LineString, Point, Polygon, box

try:
    from . import archive
except ImportError:
    import archive

DATASET = 'rotterdam-markings'
BASE = 'https://diensten.rotterdam.nl/arcgis/rest/services/SB_Infra/'
LAYERS = {'lines': ('Wegmarkeringen_Lijnen', 2),
          'areas': ('Wegmarkering_Vlakken', 1),
          'points': ('Wegmarkeringen_Punten', 0)}
archive.LICENSES[DATASET] = (
    'unspecified; public municipal endpoint; licence fields blank',
    'Gemeente Rotterdam — Stadsbeheer wegmarkeringen')


def fetch_markings(bounds):
    """Archive all three layers and return records with RD Shapely geometry.

    bounds is (west,south,east,north). Raw responses and licensing metadata
    are retained byte-for-byte. Every record includes kind, attributes and
    geometry; keep attributes when building source/method statistics.
    """
    records = []
    bbox_name = '_'.join(str(int(value)) for value in bounds)
    for kind, (service, layer) in LAYERS.items():
        endpoint = BASE + service + '/MapServer'
        archive.fetch(DATASET, service + '_iteminfo.json', endpoint + '/info/iteminfo?f=pjson')
        archive.fetch(DATASET, service + '_layer.json', endpoint + f'/{layer}?f=pjson')
        selection = dict(f='json', where='1=1', geometry=','.join(map(str,bounds)),
                         geometryType='esriGeometryEnvelope', inSR=28992,
                         spatialRel='esriSpatialRelIntersects', returnIdsOnly='true')
        identifiers = json.loads(archive.fetch(DATASET, f'{kind}_{bbox_name}_ids.json',
                                endpoint+f'/{layer}/query?'+urlencode(selection)))
        if 'error' in identifiers:
            raise RuntimeError(identifiers['error'])
        identifiers = sorted(identifiers.get('objectIds', []))
        for offset in range(0,len(identifiers),500):
            batch = identifiers[offset:offset+500]
            params = dict(f='json', objectIds=','.join(map(str,batch)), outSR=28992,
                          outFields='*', returnGeometry='true')
            url = endpoint + f'/{layer}/query?' + urlencode(params)
            response = json.loads(archive.fetch(DATASET, f'{kind}_{bbox_name}_ids_batch_{offset}.json', url))
            if 'error' in response:
                raise RuntimeError(response['error'])
            features = response.get('features', [])
            if {feature['attributes']['ID'] for feature in features} != set(batch):
                raise RuntimeError('Municipal marking ID batch is incomplete')
            for feature in features:
                source = feature.get('geometry')
                if not source:
                    continue
                geometries = []
                if kind == 'lines':
                    geometries = [LineString(path) for path in source['paths'] if len(path) > 1]
                elif kind == 'areas':
                    # Retained as survey zones only. Ring topology is not
                    # used to manufacture paint or parking-bay boundaries.
                    geometries = [Polygon(ring) for ring in source['rings'] if len(ring) > 3]
                else:
                    geometries = [Point(source['x'], source['y'])]
                for geometry in geometries:
                    records.append(dict(kind=kind, attributes=feature['attributes'], geometry=geometry))
    return records


def _draw_geometry(mask, geometry, bounds, pixel_size):
    west, south, east, north = bounds
    drawing = ImageDraw.Draw(mask)
    polygons = list(geometry.geoms) if geometry.geom_type == 'MultiPolygon' else [geometry]
    for polygon in polygons:
        if polygon.is_empty or polygon.geom_type != 'Polygon':
            continue
        def pixels(ring):
            return [((x-west)/pixel_size, (north-y)/pixel_size) for x, y in ring.coords]
        drawing.polygon(pixels(polygon.exterior), fill=1)
        for hole in polygon.interiors:
            drawing.polygon(pixels(hole), fill=0)


def marking_mask(records, bounds, aerial_rgb, surface_classes, pixel_size=0.1):
    """Extract thin bright neutral aerial structures, never invented paint.

    Register geometry is archived and measured as comparison support. It does
    not gate extraction: the M1 visual check found missing recorded dashes.
    Broad neutral components at a lower brightness threshold reject vehicle
    roofs before extraction, with 50 cm dilation to suppress bumpers. Remaining
    candidates must be elongated, narrow and at least about 1.2 m long.
    Parking is deliberately omitted: bumper highlights there outnumbered paint.
    Shadows, short dashes, fat symbols and zebra stripes can be missed.
    """
    height, width = surface_classes.shape
    support_image = Image.new('L', (width, height))
    extent = box(*bounds)
    counts = dict(line_records=0, symbol_records=0, area_records=0, skipped_untyped_lines=0)
    for record in records:
        geometry = record['geometry']
        if not geometry.intersects(extent):
            continue
        label = record['attributes'].get('TYPE') or ''
        if 'verwijderd' in label.lower():
            continue
        if record['kind'] == 'lines':
            width_match = re.search(r'_B(\d+)', label)
            if not width_match:
                counts['skipped_untyped_lines'] += 1
                continue
            paint_width = int(width_match.group(1)) / 100
            support = geometry.buffer(paint_width/2 + .15, cap_style=2)
            counts['line_records'] += 1
        elif record['kind'] == 'points':
            # A bounded search region, never an invented arrow or triangle.
            support = geometry.buffer(4)
            counts['symbol_records'] += 1
        else:
            support = geometry
            counts['area_records'] += 1
        _draw_geometry(support_image, support.intersection(extent), bounds, pixel_size)

    rgb = np.asarray(aerial_rgb, dtype=np.float32)
    brightness = rgb.mean(axis=2)
    saturation = rgb.max(axis=2) - rgb.min(axis=2)
    white_tophat = brightness - ndimage.grey_opening(brightness, size=(17, 17))
    eligible_surface = np.isin(surface_classes, [1, 2, 4, 5, 12, 15])
    bright_neutral = (brightness > 165) & (saturation < 40) & eligible_surface
    # Detect broad white roofs before clipping to narrow vector corridors;
    # otherwise a corridor could turn a car roof into a convincing thin line.
    roof_candidates = (brightness > 145) & (saturation < 60)
    roof_candidates = ndimage.binary_closing(roof_candidates, iterations=2)
    bright_labels, _ = ndimage.label(roof_candidates)
    vehicle_pixels = np.zeros(bright_neutral.shape, dtype=bool)
    for index, slices in enumerate(ndimage.find_objects(bright_labels), 1):
        if slices is None:
            continue
        component = bright_labels[slices] == index
        if 50 < component.sum() < 8000 and ndimage.distance_transform_edt(component).max() * pixel_size > .25:
            vehicle_pixels[slices] |= component
    vehicle_pixels = ndimage.binary_dilation(vehicle_pixels, iterations=5)
    candidates = (bright_neutral & ~vehicle_pixels &
                  (white_tophat > 18) & eligible_surface & (surface_classes != 4))
    # Preserve narrow dashes and painted symbols; reject broad car-roof blobs.
    labels, total = ndimage.label(candidates)
    mask = np.zeros(candidates.shape, dtype=bool)
    for index, slices in enumerate(ndimage.find_objects(labels), 1):
        if slices is None:
            continue
        component = labels[slices] == index
        area = int(component.sum())
        if area < 8 or area > 1400:
            continue
        max_radius = ndimage.distance_transform_edt(component).max() * pixel_size
        if max_radius > .35:
            continue
        yy, xx = np.nonzero(component)
        if len(xx) >= 3:
            eigenvalues = np.linalg.eigvalsh(np.cov(np.stack([xx, yy])))
            # Compact medium/large white blobs are vehicle-like; a few lost
            # fat symbol pieces are preferable to white cars becoming paint.
            if eigenvalues[1] / max(eigenvalues[0], .01) < 8 or np.sqrt(eigenvalues[1])*pixel_size < .35:
                continue
        mask[slices] |= component
    counts.update(candidate_pixels=int(candidates.sum()), painted_pixels=int(mask.sum()),
                  municipal_supported_painted_pixels=int((mask & (np.asarray(support_image)!=0)).sum()),
                  method='aerial white top-hat, neutral brightness, thin elongated components; vehicle rejection; parking omitted; municipal vectors diagnostic only')
    return mask, counts
