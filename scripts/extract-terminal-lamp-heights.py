#!/usr/bin/env python3
"""Infer terminal mast structure from cached selected-flight AHN points at BGT fixtures.

Written by AI on 2026-10-24 by model GPT-6.1 Sol. No network acquisition.
"""
import gzip
import hashlib
import json
import math
import time
from pathlib import Path

import laspy
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/industrial-structures/terminal-sources.json'
BGT = ROOT / 'source-data/supplementary-lamps.geojson.gz'
OUTPUT = ROOT / 'source-data/supplementary-lamp-heights.json'


def main():
    started = time.monotonic()
    source_inputs = json.loads(SOURCE.read_bytes())['sources']
    fixtures = json.loads(gzip.decompress(BGT.read_bytes()))['features']
    geographic_positions = np.array([
        fixture['geometry']['coordinates'] for fixture in fixtures
    ])
    rd_eastings, rd_northings = Transformer.from_crs(
        4326, 28992, always_xy=True
    ).transform(geographic_positions[:, 0], geographic_positions[:, 1])
    fixture_positions_rd = np.array([rd_eastings, rd_northings]).T

    source_configs_by_cache = {}
    observations = []
    selected_observation_by_fixture = {}
    retained_sources = []
    for source_index, source_config in enumerate(source_inputs):
        source_configs_by_cache.setdefault(
            source_config['rawPointCloudCache'], []
        ).append((source_index, source_config))

    for cache_path, source_configs in sorted(source_configs_by_cache.items()):
        point_cloud = laspy.read(ROOT / cache_path)
        all_points = np.array([
            point_cloud.x, point_cloud.y, point_cloud.z
        ]).T
        source_configs_by_flight = {}
        for source_index, source_config in source_configs:
            flight_key = (
                source_config['pointSourceId'], source_config['gpsDay']
            )
            source_configs_by_flight.setdefault(flight_key, []).append(
                (source_index, source_config)
            )

        for flight_key, source_group in source_configs_by_flight.items():
            flight_source_id, flight_gps_day = flight_key
            reconstruction_masks = [
                shape(json.loads(
                    (ROOT / source_config['selectionMask']).read_bytes()
                )['geometry'])
                for _, source_config in source_group
            ]
            reconstruction_mask = unary_union(reconstruction_masks)
            source_bounds = np.array(source_group[0][1]['boundsRD_NAP'])
            eligible_fixtures = (
                contains_xy(
                    reconstruction_mask,
                    fixture_positions_rd[:, 0], fixture_positions_rd[:, 1]
                )
                & (fixture_positions_rd[:, 0] >= source_bounds[0, 0])
                & (fixture_positions_rd[:, 0] <= source_bounds[1, 0])
                & (fixture_positions_rd[:, 1] >= source_bounds[0, 1])
                & (fixture_positions_rd[:, 1] <= source_bounds[1, 1])
            )
            fixture_indexes = np.flatnonzero(eligible_fixtures)
            if not len(fixture_indexes):
                continue

            selected_returns = (
                (np.array(point_cloud.point_source_id) == flight_source_id)
                & (
                    np.floor(np.array(point_cloud.gps_time) / 86400)
                    == flight_gps_day
                )
                & (np.array(point_cloud.classification) == 1)
            )
            flight_points = all_points[selected_returns]
            point_index = cKDTree(flight_points[:, :2])
            source_config = source_group[0][1]
            retained_source_index = len(retained_sources)
            retained_sources.append({
                'terminalSourceIndices': [index for index, _ in source_group],
                'rawPointCloudCache': cache_path,
                'sourceCropSha256': source_config['sourceCropSha256'],
                'pointSourceId': flight_source_id,
                'gpsDay': flight_gps_day,
                'surveyTimeUTC': source_config['surveyTimeUTC'],
                'rawGroundCache': source_config['rawGroundCache'],
                'source': source_config['source'],
                'selectedUnclassifiedReturns': len(flight_points),
            })

            with Image.open(ROOT / source_config['rawGroundCache']) as image:
                terrain = np.asarray(image)
                terrain_left, terrain_top = image.tag_v2[33922][3:5]
                cell_size = image.tag_v2[33550][0]
                for fixture_index in fixture_indexes:
                    fixture_position = fixture_positions_rd[fixture_index]
                    fixture = fixtures[fixture_index]
                    observation = {
                        'fixtureId': fixture['id'],
                        'sourceIndex': retained_source_index,
                        'positionRD': fixture_position.tolist(),
                        'status': 'unsupported',
                    }
                    observations.append(observation)
                    terrain_row = int(
                        (terrain_top - fixture_position[1]) / cell_size
                    )
                    terrain_column = int(
                        (fixture_position[0] - terrain_left) / cell_size
                    )
                    if not (
                        0 <= terrain_row < terrain.shape[0]
                        and 0 <= terrain_column < terrain.shape[1]
                    ):
                        observation['reason'] = 'outside retained terrain tile'
                        continue

                    terrain_window = terrain[
                        max(0, terrain_row - 4):terrain_row + 5,
                        max(0, terrain_column - 4):terrain_column + 5,
                    ]
                    valid_terrain = terrain_window[
                        (terrain_window != -9999) & np.isfinite(terrain_window)
                    ]
                    if not len(valid_terrain):
                        observation['reason'] = 'no valid terrain within 2m'
                        continue
                    ground_height = float(terrain[terrain_row, terrain_column])
                    if ground_height == -9999 or not math.isfinite(ground_height):
                        ground_height = float(np.median(valid_terrain))

                    nearby_points = flight_points[
                        point_index.query_ball_point(fixture_position, 4)
                    ].copy()
                    nearby_points[:, :2] -= fixture_position
                    shaft_points = nearby_points[
                        np.linalg.norm(nearby_points[:, :2], axis=1) <= 1
                    ]
                    shaft_points = shaft_points[
                        shaft_points[:, 2] > ground_height + 2
                    ]
                    if len(shaft_points) < 12:
                        observation['reason'] = 'insufficient shaft returns'
                        continue

                    shaft_top = float(np.quantile(shaft_points[:, 2], .995))
                    shaft_height = shaft_top - ground_height
                    observation.update({
                        'groundNAP': ground_height,
                        'coreTopNAP': shaft_top,
                        'heightMetres': shaft_height,
                        'coreReturns': len(shaft_points),
                    })
                    if shaft_height < 15:
                        observation['reason'] = 'below terminal tall-mast scope'
                        continue

                    metre_levels = np.arange(
                        math.ceil(ground_height + 2), math.floor(shaft_top)
                    )
                    occupied_levels = []
                    median_radii = []
                    for metre_level in metre_levels:
                        level_points = shaft_points[
                            (shaft_points[:, 2] >= metre_level)
                            & (shaft_points[:, 2] < metre_level + 1)
                        ]
                        occupied_levels.append(bool(len(level_points)))
                        if len(level_points):
                            median_radii.append(float(np.median(np.linalg.norm(
                                level_points[:, :2], axis=1
                            ))))
                    occupied_fraction = (
                        float(np.mean(occupied_levels))
                        if len(occupied_levels) else 0
                    )
                    longest_missing_run = 0
                    current_missing_run = 0
                    for occupied in occupied_levels:
                        current_missing_run = (
                            0 if occupied else current_missing_run + 1
                        )
                        longest_missing_run = max(
                            longest_missing_run, current_missing_run
                        )
                    median_shaft_radius = (
                        float(np.median(median_radii)) if median_radii else 4
                    )
                    head_points = nearby_points[
                        nearby_points[:, 2] >= shaft_top - 2
                    ]
                    head_span = (
                        np.ptp(head_points[:, :2], axis=0)
                        if len(head_points) else np.array([0, 0])
                    )
                    observation.update({
                        'occupiedMetreBinFraction': occupied_fraction,
                        'longestMissingMetreRun': longest_missing_run,
                        'medianColumnRadiusMetres': median_shaft_radius,
                        'upperReturns': len(head_points),
                        'upperSpanXYMetres': head_span.tolist(),
                    })
                    if (
                        occupied_fraction < .8
                        or longest_missing_run > 3
                        or median_shaft_radius > .65
                    ):
                        observation['reason'] = 'no continuous narrow shaft'
                        continue
                    if (
                        len(head_points) < 8
                        or max(head_span) < 1
                        or max(head_span) > 6
                    ):
                        observation['reason'] = (
                            'upper cluster absent or merges with broad adjacent structure'
                        )
                        continue

                    observation.update({
                        'status': 'supported',
                        'reason': 'continuous narrow shaft and compact broadened head cluster',
                        'headNAP': float(np.median(head_points[:, 2])),
                        'hardwareTopNAP': float(np.quantile(head_points[:, 2], .995)),
                    })
                    previous_index = selected_observation_by_fixture.get(
                        fixture['id']
                    )
                    if (
                        previous_index is None
                        or occupied_fraction > observations[previous_index][
                            'occupiedMetreBinFraction'
                        ]
                    ):
                        selected_observation_by_fixture[fixture['id']] = (
                            len(observations) - 1
                        )

            print(
                f'{cache_path}: {len(fixture_indexes)} inspected, '
                f'{len(selected_observation_by_fixture)} supported unique fixtures',
                flush=True,
            )
        del point_cloud, all_points

    result = {
        'writtenBy': 'AI, GPT-6.1 Sol, 2026-10-24',
        'terminalSourcesSha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'bgtSourceSha256': hashlib.sha256(BGT.read_bytes()).hexdigest(),
        'license': 'CC BY 4.0; BGT positions CC0 1.0',
        'attribution': (
            'Actueel Hoogtebestand Nederland / Het Waterschapshuis; '
            'Kadaster / PDOK / BGT source holders'
        ),
        'method': {
            'scope': 'Existing BGT positions within retained terminal reconstruction masks and source crop; selected original flight/day, classification1 returns only. No acquisition, invented positions or cross-flight averaging.',
            'core': 'Within1m plan radius; at least12 returns above terrain+2m. Core top99.5th percentile. Tall-mast scope >=15m above terrain.',
            'shaft': 'At least80% occupied1m vertical bins; no gap longer than3bins; median per-bin radial distance <=0.65m.',
            'head': 'At least8 returns in upper2m of core top within4m plan radius; maximumXYspan between1m and6m. Median upper-cluster elevation supplies approximate head placement, not a measured photometric centre.',
            'rejection': 'Unsupported records retain10m renderer illustration. Structure merging, sparse returns and missing source coverage remain explicit.',
            'sourceChoice': 'If masks overlap, choose the supported selected-flight observation with greatest vertical-bin occupancy. Never combine flights.',
        },
        'sources': retained_sources,
        'observations': observations,
        'fixtures': {
            fixture_id: {
                'observationIndex': observation_index,
                'headNAP': observations[observation_index]['headNAP'],
                'groundNAP': observations[observation_index]['groundNAP'],
            }
            for fixture_id, observation_index
            in sorted(selected_observation_by_fixture.items())
        },
        'processingSeconds': round(time.monotonic() - started, 2),
    }
    OUTPUT.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(json.dumps({
        'supported': len(selected_observation_by_fixture),
        'observations': len(observations),
        'sources': len(retained_sources),
        'seconds': result['processingSeconds'],
        'bytes': OUTPUT.stat().st_size,
    }, indent=2))


if __name__ == '__main__':
    main()
