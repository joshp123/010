#!/usr/bin/env python3
"""Bind explicitly observed source opening patches onto drawn facade wall masses.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def read_json(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble(arguments):
    specification = importlib.util.spec_from_file_location('source_view_painter', arguments.painter_scripts / 'source-view-painter.py')
    painter = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(painter)
    source = painter.load_source(arguments.source)
    observations = read_json(arguments.observations)
    views_path = Path(observations['views'])
    views = read_json(views_path)
    assert painter.m.digest(source.raw) == views['sourceSha256']
    view = next(value for value in views['views'] if value['name'] == observations['view'])
    assert digest(Path(observations['sourceImage'])) == observations['sourceSha256']
    camera = view['camera']
    size = camera['size']
    depth = np.load(views_path.parent / view['depth'])
    toward = np.array(camera['basis'])[:, 2]
    facade_labels = Image.new('I', (size, size))
    source_patch_mask = Image.new('1', (size, size))
    opening_colours = Image.new('RGB', (size, size))
    opening_mask = Image.new('1', (size, size))
    opening_drawing = ImageDraw.Draw(opening_colours)
    opening_mask_drawing = ImageDraw.Draw(opening_mask)
    facade_drawing = ImageDraw.Draw(facade_labels)
    patch_drawing = ImageDraw.Draw(source_patch_mask)
    wall_colours = [None]
    facade_bag_ids = ['']
    for index, facade in enumerate(observations['facades'], 1):
        wall_colours.append(facade['wallRgb'])
        facade_bag_ids.append(facade['sourceBagId'])
        facade_drawing.polygon([tuple(point) for point in facade['replacementPolygon']], fill=index)
        for opening in facade.get('drawnOpenings', []):
            frame = [tuple(point) for point in opening['framePolygon']]
            facade_drawing.polygon(frame, fill=index)
            opening_drawing.polygon(frame, fill=tuple(observations['drawingPalette']['frame']))
            opening_mask_drawing.polygon(frame, fill=1)
            opening_drawing.line([frame[3], frame[0], frame[1]], fill=tuple(observations['drawingPalette']['frameLight']), width=1)
            opening_drawing.line([frame[1], frame[2], frame[3]], fill=tuple(observations['drawingPalette']['frameShade']), width=1)
            for pane_index, pane in enumerate(opening['glassPolygons']):
                colour = opening.get('glassRgb', [observations['drawingPalette']['glass']] * len(opening['glassPolygons']))[pane_index]
                opening_drawing.polygon([tuple(point) for point in pane], fill=tuple(colour))
        for patch in facade['sourcePatches']:
            patch_drawing.polygon([tuple(point) for point in patch['polygon']], fill=1)
    facade_labels = np.asarray(facade_labels)
    source_patch_mask = np.asarray(source_patch_mask)
    opening_colours = np.asarray(opening_colours)
    opening_mask = np.asarray(opening_mask)
    wall_colours = np.array([[0, 0, 0]] + wall_colours[1:], np.uint8)
    facade_bag_ids = np.array(facade_bag_ids)
    images = []
    for leaf in source.sources:
        for index in range(len(leaf.images)):
            images.append(np.array(Image.open(arguments.handoff / leaf.path.stem / f'painted-atlas-{index}.png').convert('RGB')))
    replacement_points = np.array([point for facade in observations['facades'] for point in facade['replacementPolygon']])
    replacement_minimum = replacement_points.min(axis=0)
    replacement_maximum = replacement_points.max(axis=0)
    for index, triangle in enumerate(source.triangles):
        if abs(source.normals[index, 1]) > .6 or source.normals[index] @ toward < .6:
            continue
        _, triangle_pixels = painter.project(triangle['positions'], camera)
        if np.any(triangle_pixels.max(axis=0) < replacement_minimum) or np.any(triangle_pixels.min(axis=0) > replacement_maximum):
            continue
        image = images[triangle['image']]
        original_image = source.images[triangle['image']]
        height, width = image.shape[:2]
        assert image.shape == original_image.shape
        for x0, y0, x1, y1, weights, inside in painter.m.raster_triangle(triangle['uv'] * [width, height], width, height):
            projected, xy = painter.project(weights @ triangle['positions'], camera)
            pixel = np.floor(xy).astype(int)
            valid = inside & (pixel[:, :, 0] >= 0) & (pixel[:, :, 0] < size) & (pixel[:, :, 1] >= 0) & (pixel[:, :, 1] < size)
            pixel = pixel.clip(0, size - 1)
            view_normal = source.normals[index] @ np.array(camera['basis'])
            sample_delta = (pixel + .5 - xy) / camera['scale']
            plane_depth = projected[:, :, 2] - (view_normal[0] * sample_delta[:, :, 0] - view_normal[1] * sample_delta[:, :, 1]) / view_normal[2]
            valid &= abs(plane_depth - depth[pixel[:, :, 1], pixel[:, :, 0]]) < .12
            labels = facade_labels[pixel[:, :, 1], pixel[:, :, 0]]
            valid &= (labels > 0) & (facade_bag_ids[labels] == triangle['identity'])
            patch = valid & source_patch_mask[pixel[:, :, 1], pixel[:, :, 0]]
            destination = image[y0:y1 + 1, x0:x1 + 1]
            if not arguments.openings_only:
                destination[valid] = wall_colours[labels[valid]]
            destination[patch] = original_image[y0:y1 + 1, x0:x1 + 1][patch]
            drawn = valid & opening_mask[pixel[:, :, 1], pixel[:, :, 0]]
            destination[drawn] = opening_colours[pixel[:, :, 1][drawn], pixel[:, :, 0][drawn]]
    arguments.output.mkdir(parents=True, exist_ok=True)
    for leaf, (first, last) in zip(source.sources, source.source_image_ranges):
        destination = arguments.output / leaf.path.stem
        shutil.copytree(arguments.handoff / leaf.path.stem, destination, dirs_exist_ok=True)
        metadata = read_json(destination / 'georeference-and-identities.json')
        for image_index, image in enumerate(images[first:last]):
            image_path = destination / f'painted-atlas-{image_index}.png'
            Image.fromarray(image).save(image_path)
            for item in metadata['external_images']:
                if item['uri'] == image_path.name:
                    item['sha256'] = digest(image_path)
        metadata['sourceOpeningAssembly'] = {'observationsSha256': digest(arguments.observations), 'baseCollectionSha256': digest(arguments.handoff / 'collection.json'), 'openingOnly': arguments.openings_only, 'meaning': 'Explicit observed frame/glass polygons over source-supported drawn wall regions; uncertain opening patches retain original source pixels. No extra emission or inferred inventory.'}
        (destination / 'georeference-and-identities.json').write_text(json.dumps(metadata, indent=2) + '\n')
    collection = read_json(arguments.handoff / 'collection.json')
    selected_children = {leaf.path.stem for leaf in source.sources}
    collection['tiles'] = [tile for tile in collection['tiles'] if tile['directory'] in selected_children]
    (arguments.output / 'collection.json').write_text(json.dumps(collection, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['source', 'observations', 'handoff', 'output', 'painter-scripts']:
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--openings-only', action='store_true', help='Preserve registered complete facade artwork; apply only observed openings and uncertain source patches.')
    assemble(parser.parse_args())
