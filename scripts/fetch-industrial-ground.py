#!/usr/bin/env python3
"""Build measured large yards and crane tracks from BGT. Requires Shapely and pyproj.

Written by AI, gpt-6-astra, 2026-10-24.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from pyproj import Transformer
from shapely import make_valid, set_precision
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

PROJECT = Path(__file__).resolve().parents[1]
API = "https://api.pdok.nl/kadaster/bgt/ogc/v1"
CACHE = PROJECT / "work" / "data-cache"
TO_RD = Transformer.from_crs(4326, 28992, always_xy=True).transform
TO_LONLAT = Transformer.from_crs(28992, 4326, always_xy=True).transform


def fetch_json(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if not cache_path.exists():
        with urlopen(url, timeout=90) as response:
            content = response.read()
        json.loads(content)
        cache_path.write_bytes(content)
    return json.loads(cache_path.read_bytes())


def read_collection(collection, bounds, snapshot):
    url = f"{API}/collections/{collection}/items?" + urlencode({
        "bbox": ",".join(str(value) for value in bounds), "datetime": snapshot,
        "limit": 1000, "f": "json",
    })
    features, requests = [], []
    while url:
        page = fetch_json(url)
        features.extend(page["features"])
        requests.append(url)
        print(f"{collection}: {len(features):,} snapshot features", flush=True)
        url = next((link["href"] for link in page.get("links", []) if link["rel"] == "next"), None)
    return features, requests


def pieces(geometry, geometry_type):
    if geometry.geom_type == geometry_type:
        yield geometry
    elif hasattr(geometry, "geoms"):
        for child in geometry.geoms:
            yield from pieces(child, geometry_type)


def encode_json(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def main(snapshot, rebuild):
    boundary = json.loads((PROJECT / "public/data/municipality.json").read_bytes())
    boundary_geometry = shape(boundary["features"][0]["geometry"])
    municipality = make_valid(transform(TO_RD, boundary_geometry))
    bounds = boundary_geometry.bounds
    collections = ["onbegroeidterreindeel", "spoor"]
    source_file = PROJECT / "source-data/industrial-ground.geojson.gz"
    if rebuild:
        source_bytes = gzip.decompress(source_file.read_bytes())
        retained_source = json.loads(source_bytes)
        provenance = {key: value for key, value in retained_source.items() if key not in ["type", "features"]}
        collected = [([feature for feature in retained_source["features"] if feature["sourceCollection"] == name],
                      provenance["sourceCollections"][name]["requests"]) for name in collections]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            collected = list(executor.map(lambda name: read_collection(name, bounds, snapshot), collections))
    selected_sources, features = [], []
    surface_kinds = {"open verharding": "open-paving", "gesloten verharding": "closed-paving", "erf": "yard"}
    for collection, (source_features, requests) in zip(collections, collected):
        for feature in source_features:
            properties = feature["properties"]
            if properties.get("status") != "bestaand" or properties.get("termination_date"):
                continue
            if properties.get("relatieve_hoogteligging", 0) != 0:
                continue
            kind = surface_kinds.get(properties.get("fysiek_voorkomen")) if collection == "onbegroeidterreindeel" else "crane-rail"
            if kind is None or (collection == "spoor" and properties.get("plus_functie") != "(haven)kraan"):
                continue
            geometry = make_valid(transform(TO_RD, shape(feature["geometry"])))
            if not geometry.intersects(municipality):
                continue
            clipped = geometry.intersection(municipality)
            if collection == "onbegroeidterreindeel" and clipped.area < 2000:
                continue
            geometry_type = "Polygon" if collection == "onbegroeidterreindeel" else "LineString"
            clipped = unary_union(list(pieces(clipped.simplify(1, preserve_topology=True), geometry_type)))
            if clipped.is_empty:
                continue
            geographic = set_precision(transform(TO_LONLAT, clipped), 0.000001)
            selected_sources.append({**feature, "sourceCollection": collection})
            retained = {name: properties[name] for name in [
                "lokaal_id", "version", "fysiek_voorkomen", "plus_fysiek_voorkomen",
                "functie", "plus_functie", "relatieve_hoogteligging", "tijdstip_registratie",
            ] if properties.get(name) is not None}
            features.append({"type": "Feature", "id": feature["id"],
                             "properties": {"kind": kind, **retained}, "geometry": mapping(geographic)})
    if not rebuild:
        provenance = {
            "source": API, "snapshot": snapshot, "bounds": bounds,
            "sourceCollections": {name: {"url": f"{API}/collections/{name}", "requests": requests,
                                          "featureCount": len(source_features),
                                          "firstResponseTime": fetch_json(requests[0]).get("timeStamp"),
                                          "lastResponseTime": fetch_json(requests[-1]).get("timeStamp")}
                                  for name, (source_features, requests) in zip(collections, collected)},
            "boundarySource": boundary.get("source"), "license": "CC0 1.0",
            "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
            "attribution": "Kadaster / PDOK — BGT; originating municipalities and other BGT source holders",
            "semantics": "Static surveyed ground and crane rails. Yard does not imply paved surface. Crane rails do not locate cranes or container stacks.",
        }
        source_bytes = encode_json({"type": "FeatureCollection", "features": selected_sources, **provenance})
        source_file.parent.mkdir(parents=True, exist_ok=True)
        source_file.write_bytes(gzip.compress(source_bytes, mtime=0))
    output = {"type": "FeatureCollection", "features": features, **provenance,
              "sourceSha256": hashlib.sha256(source_bytes).hexdigest(), "simplificationMetres": 1,
              "minimumYardAreaSquareMetres": 2000, "displayElevationMetres": -0.65}
    output_path = PROJECT / "work/source-quality/port/industrial-ground.geojson"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(encode_json(output))
    print(f"Selected {len(features):,} features; source {source_file.stat().st_size:,} bytes; display {output_path.stat().st_size:,} bytes", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="2026-10-24T00:00:00Z")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild from the retained source gzip without fetching any data")
    arguments = parser.parse_args()
    main(arguments.snapshot, arguments.rebuild)
