#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24.
Reconcile dated native water with current surveyed industrial land and AHN6 terrain.
Run from the project root with OPENBLAS_NUM_THREADS=1 devenv shell -- python.
"""
import argparse
import gzip
import hashlib
import json
import time
from collections import defaultdict
from importlib.machinery import SourceFileLoader
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import box, shape
from shapely.ops import transform, triangulate, unary_union

from industrial_terminal_ground import MeasuredGround

PROJECT_ROOT = Path(__file__).resolve().parents[1]
industrial_builder = SourceFileLoader(
    'industrial_builder', str(PROJECT_ROOT / 'scripts/build-industrial-structures.py')
).load_module()
source_fetcher = SourceFileLoader(
    'industrial_ground_fetch', str(PROJECT_ROOT / 'scripts/fetch-industrial-ground.py')
).load_module()
mesh_partition = SourceFileLoader(
    'prepared_partition', str(PROJECT_ROOT / 'scripts/subdivide-prepared-meshes.py')
).load_module()
TO_RD = Transformer.from_crs(4326, 28992, always_xy=True).transform


def water_snapshot(bounds, snapshot):
    features, urls = source_fetcher.read_collection('waterdeel', bounds, snapshot)
    inventory = []
    for url in urls:
        cached = PROJECT_ROOT / 'work/data-cache' / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        content = cached.read_bytes()
        inventory.append({'url': url, 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})
    geometry = unary_union([
        make_valid(transform(TO_RD, shape(feature['geometry']))) for feature in features
        if feature['properties'].get('status') == 'bestaand'
        and not feature['properties'].get('termination_date')
        and feature['properties'].get('type') in ['waterloop', 'watervlakte']
    ])
    return geometry, inventory


def polygon_parts(geometry):
    if geometry.geom_type == 'Polygon':
        yield geometry
    elif hasattr(geometry, 'geoms'):
        for child in geometry.geoms:
            yield from polygon_parts(child)


class GroundSamples:
    def __init__(self, source_config, water_inventory):
        self.source_config = source_config
        self.water_inventory = water_inventory
        self.image = Image.open(PROJECT_ROOT / source_config['rawGroundCache'])
        self.values = np.asarray(self.image)
        self.left, self.top = self.image.tag_v2[33922][3:5]
        self.cell_size = self.image.tag_v2[33550][0]
        self.measured_ground = None
        self.samples = {}
        self.fit_evidence = []
        self.counts = {'directDtmVertices': 0, 'localGroundFits': 0, 'unsupportedVertices': 0}

    def height(self, coordinates):
        key = tuple(coordinates)
        if key in self.samples:
            return self.samples[key]
        east, north = coordinates
        row = int((self.top - north) / self.cell_size)
        column = int((east - self.left) / self.cell_size)
        value = None
        if 0 <= row < self.values.shape[0] and 0 <= column < self.values.shape[1]:
            observed = float(self.values[row, column])
            if np.isfinite(observed) and observed > -30:
                value = observed
                self.counts['directDtmVertices'] += 1
        if value is None:
            if self.measured_ground is None:
                self.measured_ground = MeasuredGround(PROJECT_ROOT, self.source_config, self.water_inventory)
            evidence = self.measured_ground.estimate(np.asarray(coordinates))
            if evidence is not None:
                value = evidence['heightNAP']
                self.counts['localGroundFits'] += 1
                self.fit_evidence.append({'coordinatesRD': list(coordinates), **evidence})
            else:
                self.counts['unsupportedVertices'] += 1
        self.samples[key] = value
        return value


def terrain_triangles(footprint, ground_samples, spacing):
    triangles = []
    unsupported_triangles = 0
    for polygon in polygon_parts(footprint):
        lower_x, lower_y, upper_x, upper_y = polygon.bounds
        for east in np.arange(np.floor(lower_x / spacing) * spacing, upper_x, spacing):
            for north in np.arange(np.floor(lower_y / spacing) * spacing, upper_y, spacing):
                cell = box(east, north, east + spacing, north + spacing)
                if not polygon.intersects(cell):
                    continue
                clipped = polygon.intersection(cell)
                for piece in polygon_parts(clipped):
                    for triangle in triangulate(piece):
                        if not piece.covers(triangle):
                            continue
                        plan = np.asarray(triangle.exterior.coords)[:3]
                        heights = [ground_samples.height(vertex) for vertex in plan]
                        if any(height is None for height in heights):
                            unsupported_triangles += 1
                            continue
                        # Keep the exact surveyed polygon edge; only heights are sampled/inferred.
                        points = np.column_stack([plan, heights])
                        first_edge = plan[1] - plan[0]
                        second_edge = plan[2] - plan[0]
                        signed_area = first_edge[0] * second_edge[1] - first_edge[1] * second_edge[0]
                        if signed_area < 0:
                            points = points[::-1]
                        triangles.append(points)
    return triangles, unsupported_triangles


def encode_terrain(surfaces, filename, height_evidence):
    document = {
        'asset': {'version': '2.0', 'generator': '010 dated industrial shore reconciliation'},
        'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
        'buffers': [{'byteLength': 0}], 'bufferViews': [], 'accessors': [],
        'extensionsUsed': ['KHR_mesh_quantization'], 'extensionsRequired': ['KHR_mesh_quantization']
    }
    binary = bytearray()
    all_positions = []

    def accessor(values, component_type, value_type, target, bounds=None):
        binary.extend(bytes((-len(binary)) % 4))
        raw = values.tobytes()
        stride = None
        if value_type == 'VEC3':
            padded = np.zeros((len(values), 4), dtype='<u2')
            padded[:, :3] = values
            raw = padded.tobytes()
            stride = 8
        view = {'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(raw), 'target': target}
        if stride:
            view['byteStride'] = stride
        document['bufferViews'].append(view)
        document['accessors'].append({
            'bufferView': len(document['bufferViews']) - 1, 'componentType': component_type,
            'count': len(values), 'type': value_type, **(bounds or {})
        })
        binary.extend(raw)
        return len(document['accessors']) - 1

    for kind, triangles in surfaces.items():
        rd = np.asarray(triangles).reshape(-1, 3)
        longitude, latitude = industrial_builder.RD_TO_GEOGRAPHIC.transform(rd[:, 0], rd[:, 1])
        earth = industrial_builder.earth_positions(longitude, latitude, rd[:, 2]) - industrial_builder.EARTH_ORIGIN
        positions = earth @ np.stack([
            industrial_builder.EAST, industrial_builder.UP, industrial_builder.SOUTH
        ], axis=1)
        all_positions.append(positions)
        minimum = positions.min(axis=0)
        scale = max(float(np.ptp(positions, axis=0).max()) / 65535, 1e-9)
        encoded = np.rint((positions - minimum) / scale).astype('<u2')
        unique, indices = np.unique(encoded, axis=0, return_inverse=True)
        position_accessor = accessor(unique, 5123, 'VEC3', 34962, {
            'min': unique.min(axis=0).tolist(), 'max': unique.max(axis=0).tolist()
        })
        indices = indices.astype('<u2' if len(unique) <= 65535 else '<u4')
        index_accessor = accessor(indices, 5123 if indices.dtype.itemsize == 2 else 5125, 'SCALAR', 34963)
        document['meshes'].append({
            'name': kind,
            'extras': {'surfaceKind': kind, 'sourceLayer': 'industrial-terrain',
                       'sourceStage': 'Current BGT industrial land replacing historical water; AHN6 measured or bounded inferred ground',
                       'heightEvidence': height_evidence},
            'primitives': [{'attributes': {'POSITION': position_accessor}, 'indices': index_accessor}]
        })
        document['nodes'].append({'mesh': len(document['meshes']) - 1,
                                  'translation': minimum.tolist(), 'scale': [scale] * 3})
        document['scenes'][0]['nodes'].append(len(document['nodes']) - 1)
    mesh_partition.write_glb(filename, document, binary)
    return industrial_builder.bounding_box([np.concatenate(all_positions).min(axis=0),
                                            np.concatenate(all_positions).max(axis=0)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--spacing', type=float, default=2)
    parser.add_argument('--only', type=int, nargs='*')
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    original_sources = json.loads((PROJECT_ROOT / 'source-data/industrial-structures/selection.json').read_text())
    dense_sources = json.loads((PROJECT_ROOT / 'source-data/industrial-structures/terminal-sources.json').read_text())['sources']
    dense_by_index = {source['originalSourceIndex']: source for source in dense_sources}
    selected_sources = [(index, source) for index, source in enumerate(original_sources)
                        if arguments.only is None or index in arguments.only]
    source_coverage = []
    for _, source in selected_sources:
        mask = shape(json.loads((PROJECT_ROOT / source['selectionMask']).read_text())['geometry'])
        bounds = source['boundsRD_NAP']
        source_coverage.append(mask.intersection(box(*bounds[0][:2], *bounds[1][:2])))
    coverage = unary_union(source_coverage)
    geographic_coverage = transform(industrial_builder.RD_TO_GEOGRAPHIC.transform, coverage)
    current_water, current_inventory = water_snapshot(geographic_coverage.bounds, '2026-10-23T00:00:00Z')
    historical_water, historical_inventory = water_snapshot(geographic_coverage.bounds, '2019-01-01T00:00:00Z')
    land_bytes = gzip.decompress((PROJECT_ROOT / 'source-data/industrial-ground.geojson.gz').read_bytes())
    land_source = json.loads(land_bytes)
    land_by_kind = defaultdict(list)
    kinds = {'erf': 'yard', 'gesloten verharding': 'closed-paving', 'open verharding': 'open-paving'}
    for feature in land_source['features']:
        if feature['sourceCollection'] != 'onbegroeidterreindeel':
            continue
        kind = kinds.get(feature['properties'].get('fysiek_voorkomen'))
        if kind:
            land_by_kind[kind].append(make_valid(transform(TO_RD, shape(feature['geometry']))))
    changed_by_kind = {
        kind: unary_union(polygons).intersection(historical_water).difference(current_water)
        for kind, polygons in land_by_kind.items()
    }
    tiles = []
    reports = []
    for source_index, original_source in selected_sources:
        source = dense_by_index.get(source_index, original_source)
        mask = shape(json.loads((PROJECT_ROOT / source['selectionMask']).read_text())['geometry'])
        bounds = source['boundsRD_NAP']
        coverage = mask.intersection(box(*bounds[0][:2], *bounds[1][:2]))
        footprints = {kind: changed.intersection(coverage) for kind, changed in changed_by_kind.items()}
        footprints = {kind: footprint for kind, footprint in footprints.items() if footprint.area > 0}
        if not footprints:
            continue
        ground_samples = GroundSamples(source, current_inventory)
        surfaces = {}
        omissions = 0
        for kind, footprint in footprints.items():
            triangles, unsupported = terrain_triangles(footprint, ground_samples, arguments.spacing)
            omissions += unsupported
            if triangles:
                surfaces[kind] = triangles
        rendered_area = 0.0
        for triangles in surfaces.values():
            points = np.asarray(triangles)
            first_edges = points[:, 1, :2] - points[:, 0, :2]
            second_edges = points[:, 2, :2] - points[:, 0, :2]
            rendered_area += float(np.abs(
                first_edges[:, 0] * second_edges[:, 1] - first_edges[:, 1] * second_edges[:, 0]
            ).sum() / 2)
        report = {'sourceIndex': source_index, 'region': source['region'], 'source': source,
                  'eligibleLandAreaSquareMetres': sum(footprint.area for footprint in footprints.values()),
                  'renderedLandAreaSquareMetres': rendered_area,
                  'vertices': ground_samples.counts, 'unsupportedTrianglesOmitted': omissions,
                  'triangles': sum(len(triangles) for triangles in surfaces.values())}
        if ground_samples.fit_evidence:
            evidence_path = PROJECT_ROOT / 'work/data-cache/industrial-terrain' / f'{source_index}-ground-fits.json'
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_bytes = (json.dumps(ground_samples.fit_evidence, separators=(',', ':')) + '\n').encode()
            evidence_path.write_bytes(evidence_bytes)
            report['inferredGroundEvidence'] = {
                'cache': str(evidence_path.relative_to(PROJECT_ROOT)),
                'sha256': hashlib.sha256(evidence_bytes).hexdigest(),
                'maximumSupportDistanceMetres': max(item['farthestMetres'] for item in ground_samples.fit_evidence),
                'maximumResidual90Metres': max(item['residual90Metres'] for item in ground_samples.fit_evidence),
                'maximumSlope': max(item['slope'] for item in ground_samples.fit_evidence)
            }
        if surfaces:
            filename = f'shore-{source_index}.glb'
            bounds = encode_terrain(surfaces, arguments.output / filename, ground_samples.counts)
            tiles.append({'boundingVolume': {'box': bounds}, 'geometricError': 0, 'content': {'uri': filename}})
            report['bytes'] = (arguments.output / filename).stat().st_size
        reports.append(report)
        print(json.dumps({key: value for key, value in report.items() if key != 'source'}), flush=True)
    if tiles:
        tileset = {'asset': {'version': '1.1'}, 'geometricError': 1000000, 'root': {
            'boundingVolume': {'box': mesh_partition.union_boxes([tile['boundingVolume']['box'] for tile in tiles])},
            'geometricError': 1000000, 'refine': 'ADD',
            'transform': industrial_builder.ROOT_TRANSFORM.flatten(order='F').tolist(), 'children': tiles
        }}
        (arguments.output / 'tileset.json').write_text(json.dumps(tileset, separators=(',', ':')))
    manifest = {
        'writtenBy': 'AI, gpt-6-astra, 2026-10-24',
        'generation': {
            'command': 'OPENBLAS_NUM_THREADS=1 devenv shell -- python scripts/build-industrial-terrain.py --output <fresh-output-directory>',
            'selectedSourceIndices': [index for index, _ in selected_sources],
            'currentSnapshot': '2026-10-23T00:00:00Z',
            'historicalSnapshot': '2019-01-01T00:00:00Z'
        },
        'rule': 'Current retained BGT industrial land intersecting historical2019BGT water, minus current BGT water, inside existing industrial source masks/bounds. No hand-drawn shoreline.',
        'heights': 'AHN6 2026 DTM observations; occluded cells may use bounded same-flight terminal ground planes. Unsupported triangles omitted. NAP follows existing whole-model numerical height convention.',
        'sourceLandSha256': hashlib.sha256(land_bytes).hexdigest(),
        'historicalWater': historical_inventory, 'currentWater': current_inventory,
        'spacingMetres': arguments.spacing, 'sources': reports, 'elapsedSeconds': time.monotonic() - started
    }
    (arguments.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'tiles': len(tiles), 'bytes': sum(report.get('bytes', 0) for report in reports),
                      'eligibleArea': sum(report['eligibleLandAreaSquareMetres'] for report in reports),
                      'seconds': time.monotonic() - started}), flush=True)


if __name__ == '__main__':
    main()
