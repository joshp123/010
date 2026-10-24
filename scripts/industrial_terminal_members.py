"""Written by AI, gpt-6-astra, 2026-10-24. Straight member fitting from a single measured source flight.
No crane prefab or invented engineering connections. Roof-grid claiming avoids fitting broad roofs as beams.
"""
import numpy as np
from scipy.ndimage import binary_closing, generic_filter, gaussian_filter1d
from scipy.signal import find_peaks

def fit_members(points, local_points, quality):
    horizontal_surface = (abs(quality['normal'][:, 2]) > 0.85) & (quality['eigenvalues'][:, 0] < 0.25)
    resolution = 1.0
    minimum = np.floor(local_points[:, :2].min(axis=0) / resolution) * resolution
    grid_coordinates = np.floor((local_points[:, :2] - minimum) / resolution).astype(int)
    grid_shape = grid_coordinates.max(axis=0) + 1
    grid_keys, point_cell_indices = np.unique(grid_coordinates, axis=0, return_inverse=True)
    order = np.argsort(point_cell_indices)
    cuts = np.r_[0, np.flatnonzero(np.diff(point_cell_indices[order])) + 1, len(order)]
    height_map = np.full(grid_shape, np.nan)
    for key, first, last in zip(grid_keys, cuts[:-1], cuts[1:]):
        group = order[first:last]
        if len(group) < 2:
            continue
        height = float(np.quantile(local_points[group, 2], 0.9))
        if height < 6 or height > 25:
            continue
        height_map[tuple(key)] = height
    from scipy.ndimage import generic_filter
    smoothed_heights = generic_filter(height_map, np.nanmedian, size=3, mode='constant', cval=np.nan)
    observed = np.isfinite(height_map)
    closed = binary_closing(observed, structure=np.ones((3, 3)))
    valid = closed & np.isfinite(smoothed_heights)
    height_map[valid] = smoothed_heights[valid]
    height_map[~valid] = np.nan
    from scipy.ndimage import gaussian_filter1d
    from scipy.signal import find_peaks
    hist, edges = np.histogram(
        local_points[horizontal_surface & (local_points[:, 2] < 25), 2],
        bins=np.arange(5, 25.25, 0.25)
    )
    peaks, _ = find_peaks(gaussian_filter1d(hist.astype(float), 1), distance=5, prominence=70)
    roof_levels = (edges[:-1] + edges[1:])[peaks] / 2
    if len(roof_levels):
        finite = np.isfinite(height_map)
        values = height_map[finite]
        nearest = np.argmin(abs(values[:, None] - roof_levels), axis=1)
        snapped = roof_levels[nearest]
        height_map[finite] = np.where(abs(snapped - values) < 1, snapped, values)
    heights = height_map[tuple(grid_coordinates.T)]
    claimed = np.isfinite(heights) & (local_points[:, 2] <= heights + 1)
    remaining = ~claimed
    line_like = quality['eigenvalues'][:, 1] / np.maximum(quality['eigenvalues'][:, 2], 1e-10) < 0.18
    indices = np.flatnonzero(remaining & (line_like | (local_points[:, 2] > 25)))
    active = np.ones(len(indices), bool)
    random_generator = np.random.default_rng(10)
    beams = []
    _, unique = np.unique(np.floor(local_points[indices] / 0.75).astype(int), axis=0, return_index=True)
    indices = indices[unique]
    active = np.ones(len(indices), bool)
    for axis in range(3):
        available = indices[active]
        data = local_points[available]
        across = [coordinate_axis for coordinate_axis in range(3) if coordinate_axis != axis]
        grid_keys, point_cell_indices = np.unique(
            np.floor(data[:, across] / 2).astype(int),
            axis=0,
            return_inverse=True
        )
        order = np.argsort(point_cell_indices)
        cuts = np.r_[0, np.flatnonzero(np.diff(point_cell_indices[order])) + 1, len(order)]
        consumed = []
        for first, last in zip(cuts[:-1], cuts[1:]):
            group = order[first:last]
            if len(group) < 10:
                continue
            group = group[np.argsort(data[group, axis])]
            coordinates = data[group, axis]
            divisions = np.r_[0, np.flatnonzero(np.diff(coordinates) > 3) + 1, len(group)]
            for start, end in zip(divisions[:-1], divisions[1:]):
                segment = group[start:end]
                if len(segment) < 10:
                    continue
                supported_points = data[segment]
                centre = np.mean(supported_points, axis=0)
                _, _, vectors = np.linalg.svd(supported_points - centre, full_matrices=False)
                direction = vectors[0]
                if abs(direction[axis]) < 0.96:
                    continue
                along = (supported_points - centre) @ direction
                lower_distance, upper_distance = np.quantile(along, [0.02, 0.98])
                length = upper_distance - lower_distance
                if length < 8 or len(np.unique(np.floor(along))) / length < 0.45:
                    continue
                residual = np.linalg.norm(supported_points - centre - along[:, None] * direction, axis=1)
                if np.quantile(residual, 0.9) > 1.1:
                    continue
                width = float(np.clip(np.quantile(residual, 0.8) * 2, 0.5, 2.0))
                member_start = centre + direction * lower_distance
                member_end = centre + direction * upper_distance
                beams.append({
                    'startLocal': member_start.tolist(),
                    'endLocal': member_end.tolist(),
                    'widthMetres': width,
                    'sourceSupport': len(supported_points),
                    'residual90Metres': float(np.quantile(residual, 0.9)),
                    'method': 'measured axis run'
                })
                consumed.extend(segment.tolist())
        if consumed:
            active[np.flatnonzero(active)[np.asarray(consumed)]] = False
    print('axis beams', len(beams), flush=True)
    for iteration in range(180):
        available = indices[active]
        if len(available) < 20:
            break
        data = local_points[available]
        sample = data if len(data) < 12000 else data[random_generator.choice(len(data), 12000, replace=False)]
        best = None
        for trial in range(120):
            anchor_index = int(random_generator.choice(available))
            member_start = local_points[anchor_index]
            direction = quality['principal'][anchor_index]
            offset = sample - member_start
            distance_along_member = offset @ direction
            distance = np.linalg.norm(offset - distance_along_member[:, None] * direction, axis=1)
            support = distance < 0.8
            if support.sum() >= 10:
                region = sample[support]
                member_start = region.mean(axis=0)
                _, _, vectors = np.linalg.svd(region - member_start, full_matrices=False)
                direction = vectors[0]
                offset = sample - member_start
                distance_along_member = offset @ direction
                distance = np.linalg.norm(offset - distance_along_member[:, None] * direction, axis=1)
                support = distance < 0.8
            score = int(support.sum())
            if score >= 12 and (best is None or score > best[0]):
                best = (score, member_start, direction)
        if best is None:
            break
        _, anchor, direction = best
        offset = data - anchor
        distance_along_member = offset @ direction
        distance = np.linalg.norm(offset - distance_along_member[:, None] * direction, axis=1)
        near_member = distance < 0.8
        supported = data[near_member]
        centre = np.median(supported, axis=0)
        _, _, principal_vectors = np.linalg.svd(supported - centre, full_matrices=False)
        direction = principal_vectors[0]
        projected = (supported - centre) @ direction
        order = np.argsort(projected)
        cuts = np.r_[0, np.flatnonzero(np.diff(projected[order]) > 3) + 1, len(order)]
        accepted = []
        for first, last in zip(cuts[:-1], cuts[1:]):
            group = order[first:last]
            if len(group) < 10:
                continue
            coordinate = projected[group]
            lower_distance, upper_distance = np.quantile(coordinate, [0.02, 0.98])
            length = upper_distance - lower_distance
            if length < 8 or len(np.unique(np.floor(coordinate))) / length < 0.45:
                continue
            supported_points = supported[group]
            error = np.linalg.norm(supported_points - centre - coordinate[:, None] * direction, axis=1)
            width = float(np.clip(np.quantile(error, 0.8) * 2, 0.45, 1.6))
            member_start = centre + direction * lower_distance
            member_end = centre + direction * upper_distance
            member_eigenvalues = np.linalg.eigvalsh(np.cov(supported_points.T))
            if member_eigenvalues[-2] / member_eigenvalues[-1] > 0.035:
                continue
            beams.append({
                'startLocal': member_start.tolist(),
                'endLocal': member_end.tolist(),
                'widthMetres': width,
                'sourceSupport': len(group),
                'residual90Metres': float(np.quantile(error, 0.9))
            })
            accepted.extend(np.flatnonzero(near_member)[group].tolist())
        if not accepted:
            active[np.flatnonzero(active)[np.flatnonzero(near_member)]] = False
        else:
            selected_positions = np.flatnonzero(active)[np.array(accepted)]
            active[selected_positions] = False
        if iteration % 20 == 0:
            print('beams', len(beams), 'iteration', iteration, flush=True)
    return (beams, roof_levels)
