"""Written by AI on 2026-10-25 by model GPT-6.1 Sol.

Local NSGI horizontal grids, with explicit municipal source-height handling.
"""
from pathlib import Path
import runpy
from pyproj import Transformer


class MunicipalTransformer:
    """Municipal exporter encodes NAP as Earth-centred geodetic height."""
    def __init__(self):
        self.standard = ecef_to_rdnap(preserve_source_height=False)
        self.geodetic = Transformer.from_crs(4936, 4937, always_xy=True)

    def transform(self, x, y, z, **kwargs):
        east, north, _ = self.standard.transform(x, y, z, **kwargs)
        _, _, height = self.geodetic.transform(x, y, z, **kwargs)
        return east, north, height


def ecef_to_rdnap(preserve_source_height=True):
    """Default preserves municipal NAP encoding; False is standard ETRS89."""
    if preserve_source_height:
        return MunicipalTransformer()
    return runpy.run_path(str(Path(__file__).with_name('transform-check.py')))[
        'make_ecef_to_rdnap_transformer'
    ]()


get_transformer = ecef_to_rdnap
