#!/usr/bin/env python3
"""Paint model-observed material roles without moving their source-camera support.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def compose(mask_path, palette_path, output_path):
    palette = json.loads(palette_path.read_text())['roles']
    labels = np.array([role['labelRgb'] for role in palette], dtype=np.float32)
    colours = np.array([role['drawingRgba'] for role in palette], dtype=np.uint8)
    observed_roles = np.asarray(Image.open(mask_path).convert('RGB'), dtype=np.float32)
    # These colours encode explicit model judgements, not source-image thresholds.
    distance = np.sum((observed_roles[:, :, None] - labels) ** 2, axis=3)
    role = np.argmin(distance, axis=2)
    Image.fromarray(colours[role], 'RGBA').save(output_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mask', type=Path)
    parser.add_argument('palette', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    compose(args.mask, args.palette, args.output)
