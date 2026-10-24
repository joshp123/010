"""Written by AI, gpt-6-astra, 2026-10-24. Rail-aligned measured roof bands and illustrative material tiers.
Hidden sidewalls/bases are inference; tier joints are display interpretation, not surveyed container identities.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter, binary_closing, distance_transform_edt
from scipy.signal import find_peaks
from PIL import Image

def reconstruct_roofs(
    project_root,
    source_config,
    points,
    source_rgb,
    quality,
    frames,
    roof_levels,
    measured_ground,
    industrial_builder
):
    origin = np.array(source_config['displayOriginRD'])
    angle = np.radians(source_config['orientationDegrees'])
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    local_points = (points - origin) @ rotation
    normal = quality['normal']
    point_eigenvalues = quality['eigenvalues']
    horizontal_surface = (
        (abs(normal[:, 2]) > 0.85)
        & (point_eigenvalues[:, 0] < 0.25)
        & (local_points[:, 2] < 25)
        & (local_points[:, 2] > 6)
    )
    low = np.floor(local_points[horizontal_surface, 1].min())
    roof_histogram, edges = np.histogram(
        local_points[horizontal_surface, 1],
        bins=np.arange(low, local_points[horizontal_surface, 1].max() + 0.5, 0.25)
    )
    smoothed_counts = gaussian_filter1d(roof_histogram.astype(float), 1)
    peaks, _ = find_peaks(smoothed_counts, distance=7, prominence=25)
    peaks = peaks[smoothed_counts[peaks] >= 40]
    peak_centres = edges[peaks] + 0.125
    separation = np.diff(peak_centres)
    near_separation = separation[(separation > 1.7) & (separation < 4)]
    measured_row_pitch = float(np.median(near_separation))
    roof_levels = np.asarray(roof_levels)

    def palette(values):
        hsv = industrial_builder.rgb2hsv(np.asarray(values).reshape(-1, 3))
        hsv[:, 1] *= 0.8
        hsv[:, 2] = np.maximum(hsv[:, 2], 0.55)
        return np.argmin(
            np.sum(
                (industrial_builder.rgb2lab(industrial_builder.hsv2rgb(hsv))[:, None, :] - industrial_builder.rgb2lab(industrial_builder.PALETTE_RGB)[None, :, :]) ** 2,
                axis=2
            ),
            axis=1
        )

    def box_faces(lower, upper):
        x, y, z = lower
        X, Y, Z = upper
        return np.array([
            [[x, y, z], [x, Y, z], [X, Y, z], [X, y, z]],
            [[x, y, Z], [X, y, Z], [X, Y, Z], [x, Y, Z]],
            [[x, y, z], [X, y, z], [X, y, Z], [x, y, Z]],
            [[X, Y, z], [x, Y, z], [x, Y, Z], [X, Y, Z]],
            [[x, Y, z], [x, y, z], [x, y, Z], [x, Y, Z]],
            [[X, y, z], [X, Y, z], [X, Y, Z], [X, y, Z]]
        ])

    def beam_faces(member_start, member_end, width):
        direction = member_end - member_start
        direction /= np.linalg.norm(direction)
        across = np.cross(direction, [0, 0, 1])
        if np.linalg.norm(across) < 0.01:
            across = np.cross(direction, [0, 1, 0])
        across /= np.linalg.norm(across)
        up = np.cross(direction, across)
        ring = np.array([-across - up, across - up, across + up, -across + up]) * width / 2
        member_vertices = np.concatenate([member_start + ring, member_end + ring])
        return member_vertices[np.array([
            [0, 3, 2, 1],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7]
        ])]
    image = Image.open(project_root / source_config['rawGroundCache'])
    ground = np.asarray(image)
    left, top = image.tag_v2[33922][3:5]
    cell = image.tag_v2[33550][0]
    rectangles = []
    colours = []
    roof_boxes = []
    bands = []
    omitted_roofs = []
    # These tier joints describe display scale, not surveyed individual container boundaries.
    level_gaps = np.diff(roof_levels)
    tier_spacing = float(np.median(level_gaps[(level_gaps > 2.5) & (level_gaps < 3.2)]))
    joint_height = 0.12
    corrections = []
    unsupported_local_roofs = 0
    extended_palette = np.concatenate([industrial_builder.PALETTE_RGB, industrial_builder.PALETTE_RGB * 0.78])

    def local_roof_top(roof_support_indices, previous_height):
        horizontal = roof_support_indices[(abs(normal[roof_support_indices, 2]) > 0.85) & (point_eigenvalues[roof_support_indices, 0] < 0.25)]
        if len(horizontal) < 6:
            return (
                previous_height,
                {
                    'method': 'previous top retained; insufficient horizontal local support',
                    'support': len(horizontal)
                }
            )
        counts, edges = np.histogram(local_points[horizontal, 2], bins=np.arange(6, 25.25, 0.25))
        smoothed_counts = gaussian_filter1d(counts.astype(float), 0.7)
        candidates, _ = find_peaks(smoothed_counts, prominence=1)
        candidates = candidates[smoothed_counts[candidates] >= max(3, smoothed_counts.max() * 0.2)]
        supported = []
        for peak in candidates:
            centre = (edges[peak] + edges[peak + 1]) / 2
            nearby_support = horizontal[abs(local_points[horizontal, 2] - centre) < 0.4]
            if len(nearby_support) < 6 or np.ptp(local_points[nearby_support, 0]) < min(
                2.0,
                0.4 * np.ptp(local_points[roof_support_indices, 0])
            ) or np.ptp(local_points[nearby_support, 1]) < 0.5:
                continue
            supported.append((
                float(np.median(local_points[nearby_support, 2])),
                len(nearby_support),
                int(peak)
            ))
        if not supported:
            return (
                previous_height,
                {'method': 'previous top retained; no broad local horizontal mode', 'support': len(horizontal)}
            )
        nearby_support = [value for value in supported if abs(value[0] - previous_height) < 0.75]
        selected = min(
            nearby_support,
            key=lambda value: abs(value[0] - previous_height)
        ) if nearby_support else max(supported, key=lambda value: value[1])
        return (
            selected[0],
            {
                'method': 'local horizontal source height mode',
                'support': selected[1],
                'previousGloballySnappedHeightNAP': previous_height,
                'candidateModesNAP': [value[0] for value in supported]
            }
        )

    def tiered_box(lower, upper, colour):
        faces = box_faces(lower, upper)
        rectangles.extend(faces[:2])
        colours.extend([colour] * 2)
        bottom = lower[2]
        top = upper[2]
        joints = np.arange(bottom + tier_spacing, top - 0.3, tier_spacing)
        for face in faces[2:]:
            boundaries = [bottom] + [value for joint in joints for value in [joint - joint_height / 2, joint + joint_height / 2]] + [top]
            for lower_strip_height, upper_strip_height in zip(boundaries[:-1], boundaries[1:]):
                strip = face.copy()
                strip[:, 2] = np.where(face[:, 2] == bottom, lower_strip_height, upper_strip_height)
                mid = (lower_strip_height + upper_strip_height) / 2
                is_joint = any((abs(mid - joint) < joint_height / 2 + 0.001 for joint in joints))
                rectangles.append(strip)
                colours.append(colour + len(industrial_builder.PALETTE_RGB) if is_joint else colour)
    # Retain measured roof support; only short longitudinal scan gaps are closed.
    claimed = np.zeros(len(points), bool)
    for row_index, peak in enumerate(peaks):
        centre = edges[peak] + 0.125
        lower_y = centre - measured_row_pitch * 0.45
        upper_y = centre + measured_row_pitch * 0.45
        if row_index:
            lower_y = max(lower_y, (centre + edges[peaks[row_index - 1]] + 0.125) / 2)
        if row_index + 1 < len(peaks):
            upper_y = min(upper_y, (centre + edges[peaks[row_index + 1]] + 0.125) / 2)
        if upper_y - lower_y < 0.8 or upper_y - lower_y > 5:
            continue
        selected = (local_points[:, 2] > 6) & (local_points[:, 2] < 25) & (local_points[:, 1] >= lower_y) & (local_points[:, 1] <= upper_y)
        support = np.flatnonzero(selected)
        if len(support) < 40:
            continue
        x0 = int(np.floor(local_points[support, 0].min()))
        x1 = int(np.ceil(local_points[support, 0].max())) + 1
        bins = np.floor(local_points[support, 0]).astype(int) - x0
        heights = np.full(x1 - x0, np.nan)
        colours_rgb = np.zeros((x1 - x0, 3))
        for index in np.unique(bins):
            group = support[bins == index]
            if len(group) < 2:
                continue
            heights[index] = np.quantile(local_points[group, 2], 0.9)
            upper = group[local_points[group, 2] >= np.quantile(local_points[group, 2], 0.5)]
            colours_rgb[index] = np.median(source_rgb[upper], axis=0)
        observed = np.isfinite(heights)
        if observed.sum() < 8:
            continue
        valid = binary_closing(observed, structure=np.ones(4))
        nearest = distance_transform_edt(~observed, return_distances=False, return_indices=True)[0]
        filled = heights[nearest]
        filled = median_filter(filled, size=5, mode='nearest')
        nearest_level = np.argmin(abs(filled[:, None] - roof_levels), axis=1)
        filled = median_filter(roof_levels[nearest_level], size=9, mode='nearest')
        rgb_filled = median_filter(colours_rgb[nearest], size=(5, 1), mode='nearest')
        sequence = np.where(valid, np.rint(filled * 8).astype(int), -1)
        start = 0
        while start < len(sequence):
            if sequence[start] < 0:
                start += 1
                continue
            end = start + 1
            while end < len(sequence) and sequence[end] == sequence[start]:
                end += 1
            if end - start < 2:
                start = end
                continue
            lower_x = x0 + start
            upper_x = x0 + end
            height = float(filled[start])
            colour = int(palette(np.median(rgb_filled[start:end], axis=0))[0])
            roof_support_indices = support[(local_points[support, 0] >= lower_x) & (local_points[support, 0] < upper_x)]
            if len(roof_support_indices) < 6:
                start = end
                continue
            y0, y1 = np.quantile(local_points[roof_support_indices, 1], [0.03, 0.97])
            y0 = max(lower_y, y0 - 0.15)
            y1 = min(upper_y, y1 + 0.15)
            if y1 - y0 < 0.7:
                start = end
                continue
            previous_height = height
            height, height_evidence = local_roof_top(roof_support_indices, height)
            corrections.append(height - previous_height)
            unsupported_local_roofs += int(height_evidence['method'] != 'local horizontal source height mode')
            footprint_local = np.array([
                [lower_x, y0, 0], [upper_x, y0, 0],
                [upper_x, y1, 0], [lower_x, y1, 0]
            ])
            footprint_world = footprint_local @ rotation.T + origin
            if not measured_ground.accepts_storage_footprint(footprint_world[:, :2]):
                omitted_roofs.append({
                    'footprintRD': footprint_world[:, :2].tolist(),
                    'heightNAP': height,
                    'sourceReturns': len(roof_support_indices),
                    'reason': 'Inferred storage footprint crosses retained surveyed water'
                })
                start = end
                continue
            centre_world = np.array([(lower_x + upper_x) / 2, (y0 + y1) / 2, 0]) @ rotation.T + origin
            ground_row = int(np.clip((top - centre_world[1]) / cell, 0, ground.shape[0] - 1))
            ground_column = int(np.clip((centre_world[0] - left) / cell, 0, ground.shape[1] - 1))
            base = float(ground[ground_row, ground_column])
            base_evidence = {'method': 'observed DTM cell', 'heightNAP': base}
            if base == -9999:
                base_evidence = measured_ground.estimate(centre_world[:2])
                if base_evidence is not None:
                    base = base_evidence['heightNAP']
            if base != -9999 and height - base > 1:
                tiered_box([lower_x, y0, base], [upper_x, y1, height], colour)
                roof_boxes.append({
                    'lowerLocal': [lower_x, float(y0), base],
                    'upperLocal': [upper_x, float(y1), height],
                    'baseEvidence': base_evidence,
                    'topEvidence': height_evidence,
                    'sourceReturns': len(roof_support_indices),
                    'residual90Metres': float(np.quantile(abs(local_points[roof_support_indices, 2] - height), 0.9)),
                    'observedLongitudinalFraction': float(observed[start:end].mean())
                })
                claimed |= (
                    (local_points[:, 0] >= lower_x) & (local_points[:, 0] <= upper_x)
                    & (local_points[:, 1] >= y0) & (local_points[:, 1] <= y1)
                    & (local_points[:, 2] <= height + 1)
                )
            else:
                omitted_roofs.append({
                    'footprintRD': footprint_world[:, :2].tolist(),
                    'heightNAP': height,
                    'sourceReturns': len(roof_support_indices),
                    'reason': 'No supported hidden base; exposed roof retained in raw source only'
                })
            start = end
        bands.append({
            'observedCells': int(observed.sum()),
            'closedCells': int(valid.sum()),
            'sequenceRuns': int(np.count_nonzero(np.diff(sequence))),
            'centre': float(centre),
            'lower': float(lower_y),
            'upper': float(upper_y),
            'planarRoofReturns': len(support)
        })
    for beam in frames:
        lower_strip_height = np.array(beam['startLocal'])
        upper_strip_height = np.array(beam['endLocal'])
        faces = beam_faces(lower_strip_height, upper_strip_height, beam['widthMetres'])
        rectangles.extend(faces)
        nearest = np.argmin(np.sum((local_points - (lower_strip_height + upper_strip_height) / 2) ** 2, axis=1))
        colour = int(palette(source_rgb[nearest])[0])
        colours.extend([colour] * 6)
    world = np.asarray(rectangles) @ rotation.T + origin
    report = {
        'method': 'Measured rail-aligned roof-density bands; longitudinal measured height/colour profiles; source-fit frame beams. Hidden box walls inferred to observed DTM or nearby same-flight terminal ground; survey-water crossings rejected. Short longitudinal scan gaps closed, no complete objects or missing flight coverage inserted.',
        'groundEvidence': measured_ground.counts,
        'illustrativeTierJoints': {'spacingMetres': tier_spacing, 'heightMetres': joint_height, 'meaning': 'Illustrative material joints from repeated source roof-level gaps, not surveyed individual container boundaries'},
        'localTopCorrections': {'quantilesMetres': np.quantile(corrections, [0, 0.1, 0.5, 0.9, 1]).tolist(), 'changedOver075Metres': int(np.count_nonzero(abs(np.array(corrections)) > 0.75)), 'withoutBroadLocalSupport': unsupported_local_roofs},
        'roofCapsWithoutBase': 0,
        'omittedRoofs': omitted_roofs,
        'omittedRoofsWithoutBase': sum('hidden base' in roof['reason'] for roof in omitted_roofs),
        'surveyWaterSourceInventory': measured_ground.water_sources,
        'measuredTypicalRowPitchMetres': measured_row_pitch,
        'bands': bands,
        'roofs': roof_boxes,
        'frameMembers': len(frames),
        'memberEvidence': frames,
        'sourceReturns': len(points),
        'returnsInsideRoofSolids': int(claimed.sum()),
        'triangles': len(rectangles) * 2
    }
    return (world, extended_palette[np.asarray(colours)], report)
