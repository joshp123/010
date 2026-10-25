"""Written by AI on 2026-10-25 by model GPT-6.1 Sol.

Offline RDNAPTRANS2018 grid transformation and published NSGI coordinate check.
Municipal Earth-centred vertices are interpreted as ETRS89 (EPSG:4936): this
datum assumption must also be checked against aerial/source footprint evidence.
"""
from pathlib import Path
import json
import hashlib
from datetime import datetime, timezone
import numpy as np
from pyproj import Transformer

GRID_DIRECTORY = Path(__file__).resolve().parents[3] / "sources/coordinate-grids/2026-10-25"


def make_ecef_to_rdnap_transformer():
    horizontal_grid = GRID_DIRECTORY / "nl_nsgi_rdtrans2018.tif"
    vertical_grid = GRID_DIRECTORY / "nl_nsgi_nlgeo2018.tif"
    for grid in (horizontal_grid, vertical_grid):
        if not grid.is_file():
            raise FileNotFoundError(grid)
    # Quotes protect paths containing spaces in PROJ's pipeline parser.
    return Transformer.from_pipeline(
        "+proj=pipeline +step +inv +proj=cart +ellps=GRS80 "
        f'+step +inv +proj=vgridshift +grids="{vertical_grid}" +multiplier=1 '
        f'+step +inv +proj=hgridshift +grids="{horizontal_grid}" '
        "+step +proj=sterea +lat_0=52.1561605555556 "
        "+lon_0=5.38763888888889 +k=0.9999079 +x_0=155000 +y_0=463000 +ellps=bessel"
    )


def check():
    references = np.genfromtxt(GRID_DIRECTORY / "Z001_ETRS89andRDNAP.txt", missing_values="*", filling_values=np.nan)
    references = references[np.isfinite(references).all(axis=1)]
    # The model's operating area is inland Rotterdam. Published points outside
    # the correction grids exercise a separate offshore fallback, irrelevant here.
    references = references[(references[:, 1] > 51) & (references[:, 1] < 53.5) & (references[:, 2] > 3.5) & (references[:, 2] < 7)]
    geographical_to_ecef = Transformer.from_crs(4937, 4936, always_xy=True)
    ecef = geographical_to_ecef.transform(references[:, 2], references[:, 1], references[:, 3], errcheck=True)
    transformer = make_ecef_to_rdnap_transformer()
    rdnap = np.array(transformer.transform(*ecef, errcheck=True)).T
    residuals = rdnap - references[:, 4:7]
    horizontal_residuals = np.linalg.norm(residuals[:, :2], axis=1)
    result = {
        "source_datum_assumption": "ETRS89 geocentric EPSG:4936; source epoch not verified",
        "reference_url": "https://github.com/GeodetischeInfrastructuur/transformations/blob/main/validate/data/Z001_ETRS89andRDNAP.txt",
        "reference_count": len(references),
        "max_horizontal_error_m": float(horizontal_residuals.max()),
        "max_vertical_error_m": float(abs(residuals[:, 2]).max()),
        "first_reference_expected_rdnap": references[0, 4:7].tolist(),
        "first_reference_actual_rdnap": rdnap[0].tolist(),
        "pipeline": transformer.to_proj4(),
    }
    (Path(__file__).parent / "transform-check.json").write_text(json.dumps(result, indent=2) + "\n")
    urls = {
        "nl_nsgi_rdtrans2018.tif": "https://cdn.proj.org/nl_nsgi_rdtrans2018.tif",
        "nl_nsgi_nlgeo2018.tif": "https://cdn.proj.org/nl_nsgi_nlgeo2018.tif",
        "Z001_ETRS89andRDNAP.txt": "https://raw.githubusercontent.com/GeodetischeInfrastructuur/transformations/main/validate/data/Z001_ETRS89andRDNAP.txt",
    }
    manifest = {"dataset": "NSGI RDNAPTRANS2018 grids and reference coordinates", "licence": "CC BY 4.0", "credit": "NSGI; GeoTIFF conversion by OSGeo PROJ-data", "files": []}
    for name, url in urls.items():
        path = GRID_DIRECTORY / name
        manifest["files"].append({"path": name, "url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size, "fetched_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()})
    (GRID_DIRECTORY / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    check()
