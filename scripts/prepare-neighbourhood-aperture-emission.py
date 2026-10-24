#!/usr/bin/env python3
"""Keep shared source observations in each retained leaf's original UV frame.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

import numpy as np


def read_json(path):
    return json.loads(path.read_text())


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prepare(arguments):
    pane_assembler = load_module('pane_assembler', Path(__file__).with_name('prepare-source-aperture-emission.py'))
    painter = load_module('shared_source_painter', arguments.painter_scripts / 'source-view-painter.py')
    source = painter.load_source(arguments.source)
    shared_views = read_json(arguments.views)
    observations = read_json(arguments.observations)
    assert painter.m.digest(source.raw) == shared_views['sourceSha256'] == observations['sourceSha256']
    collection = read_json(arguments.handoff / 'collection.json')
    retained = {entry['tile']: entry for entry in observations.get('retainedObservations', [])}
    arguments.output.mkdir(parents=True, exist_ok=True)

    for leaf in source.sources:
        name = leaf.path.stem
        child_output = arguments.output / name
        child_output.mkdir(parents=True, exist_ok=True)
        if name in retained:
            entry = retained[name]
            views_path = (arguments.observations.parent / entry['views']).resolve()
            observations_path = (arguments.observations.parent / entry['observations']).resolve()
        else:
            rotation = np.array(leaf.doc['nodes'][0]['matrix']).reshape(4, 4, order='F')[:3, :3]
            relative_rotation = source.anchor_rotation.T @ rotation
            relative_centre = source.anchor_rotation.T @ (np.array(leaf.feature['RTC_CENTER']) - source.anchor_centre)
            leaf_views = copy.deepcopy(shared_views)
            leaf_views['sourceSha256'] = painter.m.digest(leaf.raw)
            leaf_views['sharedObservationFingerprint'] = shared_views['sourceSha256']
            for view in leaf_views['views']:
                camera = view['camera']
                camera['centre'] = ((np.array(camera['centre']) - relative_centre) @ relative_rotation).tolist()
                camera['basis'] = (relative_rotation.T @ np.array(camera['basis'])).tolist()
                for field in ['source', 'depth']:
                    view[field] = str((arguments.views.parent / view[field]).resolve())
            leaf_observations = copy.deepcopy(observations)
            leaf_observations['sourceSha256'] = leaf_views['sourceSha256']
            leaf_observations['sharedObservationFingerprint'] = shared_views['sourceSha256']
            views_path = child_output / 'source-views.json'
            observations_path = child_output / 'pane-observations.json'
            write_json(views_path, leaf_views)
            write_json(observations_path, leaf_observations)
        pane_assembler.prepare(leaf.path, views_path, observations_path,
                               arguments.handoff / name, child_output, arguments.painter_scripts)
    collection['observedApertures'] = {
        'sourceObservationFingerprint': observations['sourceSha256'],
        'meaning': observations['meaning'],
        'status': 'Assembly candidate; actual common city day/dusk/night review required',
    }
    write_json(arguments.output / 'collection.json', collection)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['source', 'views', 'observations', 'handoff', 'output', 'painter-scripts']:
        parser.add_argument('--' + name, type=Path, required=True)
    prepare(parser.parse_args())
