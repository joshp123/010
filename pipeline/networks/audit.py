"""Audit source readiness without inventing routing data.
Written by AI on 2026-10-26 by model GPT-6 Astra.
"""
import json
from collections import Counter
from pathlib import Path
from acquire import ROOT, SOURCE


def main():
    pages = sorted(SOURCE.glob('page-*.json'))
    assert pages, 'Run acquire.py first'
    assert not any(link['rel'] == 'next' for link in json.loads(pages[-1].read_text())['links']), 'Incomplete archive'
    features = [feature for path in pages for feature in json.loads(path.read_text())['features']]
    tiles = [ROOT / f'scene/v1/tiles/x{x}_y{y}/ground.glb'
             for x in range(89750, 96500, 250) for y in range(434750, 438000, 250)]
    report = {
        'status': 'blocked; no runtime graphs published',
        'bounds_rd': [89750, 434750, 96500, 438000],
        'source_features_intersecting_bbox': len(features),
        'source_class_counts': dict(Counter(feature['properties']['bst_code'] for feature in features)),
        'coordinate_dimension_counts': dict(Counter(len(point) for feature in features
            for line in feature['geometry']['coordinates'] for point in line)),
        'ground_tiles_present': sum(path.exists() for path in tiles),
        'ground_tiles_expected': len(tiles),
        'missing_ground_tiles': [path.parent.name for path in tiles if not path.exists()],
        'blockers': [
            'NWB physical road class does not establish permitted vehicle types. WKD Verkeerstypen supplies AUTO_H/T and FIETS_H/T; its official download is outside the PDOK-only acquisition scope.',
            'Non-FP NWB driving directions apply to cars, not cycle contraflow permissions.',
            'NWB supplies only 2D coordinates. REL_HOOGTE gives relative ordering, not NAP metres. No verified per-coordinate Maastunnel roadway depth profile is available in inspected inputs.',
            'Current ground.glb coverage is incomplete for M1. AHN surface heights cannot supply underground roadway profiles.'
        ],
        'direction_semantics': {'H': 'source begin to end', 'T': 'source end to begin', 'B': 'both', 'O': 'unknown'},
        'direction_applicability': 'Cars except FP, where RIJRICHTNG describes cyclists.',
        'required_additional_source': {
            'name': 'RWS WKD Verkeerstypen', 'license': 'CC0 according to official government catalogue',
            'documentation': 'https://docs.ndw.nu/en/handleidingen/wkd/wkd_verkeerstypen/',
            'download': 'https://downloads.rijkswaterstaatdata.nl/wkd/geogegevens/CSV-bestand/Verkeerstypen/01-10-2026.zip'
        },
        'osm_turn_restrictions': 'Not used. Existing ODbL inputs remain untouched.',
        'outputs': {'cars.json': None, 'bikes.json': None, 'debug_images': []},
        'connectivity': 'Not measured: legal network selection is unresolved.',
        'source_archive': str(SOURCE),
        'documentation': [
            'https://docs.ndw.nu/handleidingen/nwb/nwb-basisstructuur/baansubsoort/',
            'https://docs.ndw.nu/handleidingen/nwb/nwb-basisstructuur/overige-attributen/',
            'https://docs.ndw.nu/en/handleidingen/nwb/nwb-producten/nwb-dagelijks/'
        ]
    }
    output = ROOT / 'scene/v1/networks'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'source-readiness.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['status', 'source_features_intersecting_bbox',
        'source_class_counts', 'ground_tiles_present', 'ground_tiles_expected', 'outputs']}, indent=2))


if __name__ == '__main__':
    main()
