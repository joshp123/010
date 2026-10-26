"""Check exported geometry and rendered evidence. Written by AI on 2026-10-26 by model GPT-6."""
from collections import Counter
import hashlib
import json
import math
from PIL import Image
from shapely.geometry import LineString, Point
from .build import BOUNDS, OUTPUT, SOURCE
from .debug import RENDERS


def main():
    target = OUTPUT / 'transit.json'
    payload = target.read_bytes()
    lines = json.loads(payload)['lines']
    keys = {(g['mode'], g['line']) for g in lines}
    source_keys = {(g['mode'], g['line']) for g in json.loads((SOURCE / 'planar.json').read_text())}
    assert len(keys) == len(lines) and keys == source_keys
    assert len(payload) < 1_500_000
    vertices = [v for g in lines for p in g['paths'] for v in p]
    for g in lines:
        assert g['mode'] in ('tram', 'metro', 'train', 'ferry')
        for path in g['paths']:
            assert len(path) >= 2
            for vertex in path:
                assert len(vertex) == 4 and all(math.isfinite(n) for n in vertex)
                x, y, z, tunnel = vertex
                assert BOUNDS[0] <= x <= BOUNDS[2] and BOUNDS[1] <= y <= BOUNDS[3]
                assert tunnel in (0, 1) and (not tunnel or z == -12)
    matching = json.loads((SOURCE / 'matching-report.json').read_text())
    heights = json.loads((SOURCE / 'height-report.json').read_text())
    assert not matching['unmatchedLegsInsideOutput'] and not heights['missingAhn']
    assert heights['sha256'] == hashlib.sha256(payload).hexdigest()
    delfshaven = {}
    for line in ('A', 'B', 'C'):
        group = next(g for g in lines if g['mode'] == 'metro' and g['line'] == line)
        path = min(group['paths'], key=lambda p: LineString([v[:2] for v in p]).distance(Point(90200, 436150)))
        assert all(v[3] == 1 and v[2] == -12 for v in path)
        delfshaven[line] = {'tunnel': True, 'zNap': -12, 'distanceFromCropCentre': round(LineString([v[:2] for v in path]).distance(Point(90200, 436150)), 2)}
    images = []
    for name, dimensions in (('m1-plus-2km-2m.png', (5375, 3717)), ('delfshaven-0.5m.png', (2000, 892))):
        path = RENDERS / name
        with Image.open(path) as img:
            assert img.size == dimensions
        images.append({'file': name, 'dimensions': dimensions, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    report = {'writtenBy': 'AI, GPT-6, 2026-10-26', 'output': str(target), 'bytes': len(payload), 'sha256': heights['sha256'], 'lineCounts': dict(Counter(g['mode'] for g in lines)), 'vertices': len(vertices), 'unmatchedLegsInsideOutput': 0, 'missingHeights': 0, 'delfshavenMetro': delfshaven, 'images': images}
    (RENDERS / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
