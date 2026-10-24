"""Written by AI, gpt-6-astra, 2026-10-24. Bounded observed-ground fit for occluded stack bases.
Same flight, same terminal mask, exact retained survey water.
"""
import hashlib
import json
from pathlib import Path
import laspy
import numpy as np
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape, box, Point, LineString, Polygon
from shapely.ops import transform, unary_union
from pyproj import Transformer

class MeasuredGround:

    def __init__(self, project_root, source_config, inventory):
        source_cloud = laspy.read(project_root / source_config['rawPointCloudCache'])
        source_gps_days = np.floor(np.asarray(source_cloud.gps_time) / 86400).astype(int)
        accepted_samples = (
            (np.asarray(source_cloud.classification) == 2)
            & (np.asarray(source_cloud.point_source_id) == source_config['pointSourceId'])
            & (source_gps_days == source_config['gpsDay'])
        )
        points = np.stack([source_cloud.x, source_cloud.y, source_cloud.z], axis=1)[accepted_samples]
        self.terminal = shape(json.loads((project_root / source_config['selectionMask']).read_text())['geometry'])
        points = points[contains_xy(self.terminal, points[:, 0], points[:, 1])]
        _, indices = np.unique(np.floor(points[:, :2]).astype(int), axis=0, return_index=True)
        self.points = points[indices]
        self.tree = cKDTree(self.points[:, :2])
        rd_to_geographic = Transformer.from_crs(28992, 4326, always_xy=True)
        geographic_to_rd = Transformer.from_crs(4326, 28992, always_xy=True)
        # Eligibility must cover observed roofs over water, not only observed dry ground.
        source_bounds = np.asarray(source_config['boundsRD_NAP'])
        bounds = [source_bounds[0, :2] - 50, source_bounds[1, :2] + 50]
        area = box(*bounds[0], *bounds[1])
        geographic_area = transform(rd_to_geographic.transform, area)
        polygons = []
        self.water_sources = []
        for record in inventory:
            cached = project_root / 'work/data-cache' / (hashlib.sha256(record['url'].encode()).hexdigest() + '.json')
            content = cached.read_bytes()
            if hashlib.sha256(content).hexdigest() != record['sha256']:
                raise ValueError('Retained water cache hash differs')
            for feature in json.loads(content)['features']:
                properties = feature.get('properties', {})
                if '/kadaster/bgt/' in record['url'] and (
                    properties.get('status') != 'bestaand'
                    or properties.get('termination_date')
                    or properties.get('type') not in ['waterloop', 'watervlakte']
                ):
                    continue
                geometry = shape(feature['geometry'])
                if geometry.intersects(geographic_area):
                    polygons.append(transform(geographic_to_rd.transform, geometry).intersection(area))
            self.water_sources.append(record)
        self.water = unary_union(polygons)
        self.counts = {
            'measuredGroundCells': len(self.points),
            'fits': 0,
            'water': 0,
            'insufficientSupport': 0,
            'nonplanar': 0,
            'outsideTerminal': 0,
            'storageFootprintsCrossingWater': 0
        }

    def accepts_storage_footprint(self, corners_rd):
        footprint = Polygon(corners_rd)
        if footprint.intersection(self.water).area > 0:
            self.counts['storageFootprintsCrossingWater'] += 1
            return False
        return True

    def estimate(self, centre):
        if not self.terminal.covers(Point(*centre)):
            self.counts['outsideTerminal'] += 1
            return None
        if self.water.covers(Point(*centre)):
            self.counts['water'] += 1
            return None
        if len(self.points) < 8:
            self.counts['insufficientSupport'] += 1
            return None
        distances, indices = self.tree.query(centre, k=min(48, len(self.points)))
        selected = indices[distances <= 30]
        selected = np.array(
            [index for index in selected if not self.water.intersects(LineString([
                centre,
                self.points[index, :2]
            ]))],
            dtype=int
        )
        if len(selected) < 8:
            self.counts['insufficientSupport'] += 1
            return None
        points = self.points[selected]
        horizontal_offsets = points[:, :2] - centre
        design = np.column_stack([horizontal_offsets, np.ones(len(horizontal_offsets))])
        accepted_samples = np.ones(len(points), bool)
        for _ in range(3):
            coefficients = np.linalg.lstsq(design[accepted_samples], points[accepted_samples, 2], rcond=None)[0]
            residual = points[:, 2] - design @ coefficients
            scale = max(0.08, float(np.median(abs(residual[accepted_samples]))) * 3)
            accepted_samples = abs(residual) <= scale
            if accepted_samples.sum() < 8:
                self.counts['insufficientSupport'] += 1
                return None
        error = float(np.quantile(abs(residual[accepted_samples]), 0.9))
        slope = float(np.linalg.norm(coefficients[:2]))
        if error > 0.25 or slope > 0.04:
            self.counts['nonplanar'] += 1
            return None
        self.counts['fits'] += 1
        return {
            'heightNAP': float(coefficients[2]),
            'method': 'same-flight class2 local plane across occluded DTM; no survey-water crossing; same terminal mask',
            'observedCells': int(accepted_samples.sum()),
            'nearestMetres': float(np.min(np.linalg.norm(horizontal_offsets[accepted_samples], axis=1))),
            'farthestMetres': float(np.max(np.linalg.norm(horizontal_offsets[accepted_samples], axis=1))),
            'residual90Metres': error,
            'slope': slope,
            'sourceGroundCellIndices': selected[accepted_samples].tolist()
        }
