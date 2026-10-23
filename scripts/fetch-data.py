#!/usr/bin/env python3
"""Fetch public Rotterdam map data. Requires Shapely and pyproj; no API key.

Written by AI, gpt-6-astra, 2026-10-24.
"""

import concurrent.futures
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.request import urlopen

from pyproj import Transformer
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "dist" / "data"
CACHE = PROJECT / "work" / "data-cache"
BOUNDARY_URL = "https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/gemeentegebied/items?naam=Rotterdam&f=json"
TOPOGRAPHY_API = "https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1"
TO_RD = Transformer.from_crs(4326, 28992, always_xy=True).transform
TO_LONLAT = Transformer.from_crs(28992, 4326, always_xy=True).transform
GEOCODER = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free"

# Public landmarks and district names only. Exact result labels prevent broad search fallbacks.
DESTINATIONS = [
    ("erasmusbrug", "Erasmusbrug", "landmark", "Erasmusbrug", "weg", "Erasmusbrug, Rotterdam", 1500),
    ("kop-van-zuid", "Kop van Zuid", "neighborhood", "Kop van Zuid", "buurt", "Kop van Zuid Rotterdam", 1800),
    ("centraal", "Rotterdam Centraal", "landmark", "Stationsplein 1 Rotterdam", "adres", "Stationsplein 1, 3013AJ Rotterdam", 1600),
    ("markthal", "Markthal", "landmark", "Ds. Jan Scharpstraat 298 Rotterdam", "adres", "Ds. Jan Scharpstraat 298, 3011GZ Rotterdam", 1200),
    ("delfshaven", "Delfshaven", "neighborhood", "Delfshaven", "buurt", "Delfshaven Rotterdam", 2400),
    ("euromast", "Euromast", "landmark", "Parkhaven 20 Rotterdam", "adres", "Parkhaven 20, 3016GM Rotterdam", 1500),
    ("feijenoord", "Feijenoord", "neighborhood", "Feijenoord", "buurt", "Feijenoord Rotterdam", 2400),
    ("kralingen", "Kralingen", "neighborhood", "Kralingen Oost", "buurt", "Kralingen Oost Rotterdam", 3000),
    ("hoek-van-holland", "Hoek van Holland", "neighborhood", "Hoek van Holland", "woonplaats", "Hoek van Holland, Rotterdam, Zuid-Holland", 4500),
    ("maasvlakte", "Maasvlakte", "port", "Maasvlakte", "woonplaats", "Maasvlakte Rotterdam, Rotterdam, Zuid-Holland", 10000),
    ("rozenburg", "Rozenburg", "neighborhood", "Rozenburg", "buurt", "Rozenburg Rotterdam", 3500),
    ("pernis", "Pernis", "neighborhood", "Pernis", "buurt", "Pernis Rotterdam", 2800),
    ("hoogvliet", "Hoogvliet", "neighborhood", "Hoogvliet", "woonplaats", "Hoogvliet Rotterdam, Rotterdam, Zuid-Holland", 4200),
]


def fetch_json(url):
    """Cache the official responses locally so rebuilding need not repeat downloads."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if not cache_file.exists():
        with urlopen(url, timeout=45) as response:
            content = response.read()
        json.loads(content)
        cache_file.write_bytes(content)
    return json.loads(cache_file.read_bytes())


def write_json(name, value):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / name
    destination.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"{name}: {destination.stat().st_size:,} bytes", flush=True)


def build_destinations():
    destinations = []
    for identifier, name, category, query, result_type, expected_label, span in DESTINATIONS:
        url = GEOCODER + "?" + urlencode({
            "q": query, "fq": ["gemeentecode:0599", "type:" + result_type], "rows": 10
        }, doseq=True)
        response = fetch_json(url)
        matches = [result for result in response["response"]["docs"] if result["weergavenaam"] == expected_label]
        if len(matches) != 1:
            raise ValueError(f"Expected one exact public destination for {name}; got {len(matches)}")
        match = matches[0]
        longitude, latitude = map(float, re.fullmatch(r"POINT\(([^ ]+) ([^ ]+)\)", match["centroide_ll"]).groups())
        destinations.append({"id": identifier, "name": name, "category": category,
                             "longitude": longitude, "latitude": latitude, "span": span,
                             "sourceUrl": url, "sourceId": match["id"]})
    write_json("destinations.json", destinations)


def read_collection(collection, bounds):
    url = f"{TOPOGRAPHY_API}/collections/{collection}/items?" + urlencode({
        "bbox": ",".join(str(value) for value in bounds), "limit": 1000, "f": "json"
    })
    features = []
    while url:
        page = fetch_json(url)
        features.extend(page["features"])
        print(f"{collection}: {len(features):,} source features", flush=True)
        url = next((link["href"] for link in page.get("links", []) if link["rel"] == "next"), None)
    return features


def polygons(geometry):
    if geometry.geom_type == "Polygon":
        yield geometry
    elif geometry.geom_type in ("MultiPolygon", "GeometryCollection"):
        for child in geometry.geoms:
            yield from polygons(child)


def land_kind(properties):
    usage = (properties.get("typelandgebruik") or "").lower()
    if "bos" in usage:
        return "forest"
    if usage in ("grasland", "heide"):
        return "grass"
    if "akker" in usage or "fruit" in usage or "boomgaard" in usage:
        return "farmland"
    if "zand" in usage:
        return "sand"
    if "bebouwd" in usage or "spoor" in usage:
        return "urban"
    return "land"


def main():
    boundary_response = fetch_json(BOUNDARY_URL)
    boundary = boundary_response["features"][0]
    assert boundary["properties"]["identificatie"] == "GM0599"
    write_json("municipality.geojson", {
        "type": "FeatureCollection", "features": [boundary], "source": BOUNDARY_URL
    })
    municipality = make_valid(transform(TO_RD, shape(boundary["geometry"])))
    geographic_bounds = shape(boundary["geometry"]).bounds
    collections = ["waterdeel_vlak", "terrein_vlak"]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        collected = list(executor.map(lambda collection: read_collection(collection, geographic_bounds), collections))

    layers = defaultdict(list)
    source_counts = {}
    for collection, features in zip(collections, collected):
        source_counts[collection] = len(features)
        for feature in features:
            geometry = make_valid(transform(TO_RD, shape(feature["geometry"])))
            if not geometry.intersects(municipality):
                continue
            clipped = geometry.intersection(municipality)
            kind = "water" if collection == "waterdeel_vlak" else land_kind(feature["properties"])
            layers[kind].extend(polygon for polygon in polygons(clipped) if polygon.area >= 100)

    overview = []
    # Actual municipal land is the municipality minus recorded water, not a guessed coastline.
    water = unary_union(layers["water"])
    land = municipality.difference(water)
    overview.append({"type": "Feature", "properties": {"kind": "land"},
                     "geometry": mapping(transform(TO_LONLAT, land.simplify(6, preserve_topology=True)))})
    for kind in ["urban", "farmland", "grass", "forest", "sand", "water"]:
        merged = unary_union(layers[kind]).simplify(6, preserve_topology=True)
        for polygon in polygons(merged):
            overview.append({"type": "Feature", "properties": {"kind": kind},
                             "geometry": mapping(transform(TO_LONLAT, polygon))})
    # Six decimals retains decimetre precision, finer than the 6 m overview simplification.
    def rounded(value):
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, (list, tuple)):
            return [rounded(item) for item in value]
        if isinstance(value, dict):
            return {key: rounded(item) for key, item in value.items()}
        return value
    # Coordinate rounding can collapse thin rings. Repair the serialized geometry,
    # retaining only polygonal pieces so consumers never receive line fragments.
    serialized_overview = []
    for feature in overview:
        polygonal_geometry = unary_union(list(polygons(make_valid(shape(rounded(feature["geometry"]))))))
        if polygonal_geometry.is_empty:
            continue
        serialized_overview.append({**feature, "geometry": mapping(polygonal_geometry)})
    write_json("overview.geojson", {
        "type": "FeatureCollection", "features": serialized_overview,
        "source": TOPOGRAPHY_API, "sourceFeatureCounts": source_counts,
        "simplificationMetres": 6, "minimumPolygonAreaSquareMetres": 100,
        "license": "CC BY 4.0", "attribution": "Kadaster / PDOK, BRT TOP10NL"
    })
    print(f"Municipality area: {municipality.area / 1e6:.2f} km²; water: {water.area / 1e6:.2f} km²; overview features: {len(serialized_overview):,}", flush=True)


if __name__ == "__main__":
    if "--destinations-only" in sys.argv:
        build_destinations()
    else:
        main()
        build_destinations()
