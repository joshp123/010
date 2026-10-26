# Written by AI on 2026-10-27 by model Claude Opus 5.5.
# Direction of the nearest road from the OSM car graph (scene/v1/networks/
# cars.json), for register points that carry no rotation: markings, bike racks.
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")


class RoadDirections:
    def __init__(self):
        graph = json.load(open(DATA / "scene/v1/networks/cars.json"))
        nodes = np.array([n[:2] for n in graph["nodes"]])
        mids, dirs, twoway = [], [], []
        for index, (a, b, *_rest) in enumerate(graph["edges"]):
            pa, pb = nodes[a], nodes[b]
            length = np.hypot(*(pb - pa))
            if length < 0.5:
                continue
            way = graph["ways"][graph["edge_ways"][index]]
            for t in np.arange(0.5, length, 2.0):  # a sample every 2 m along each edge
                mids.append(pa + (pb - pa) * t / length)
                dirs.append((pb - pa) / length)
                twoway.append(bool(way["directions"][0] and way["directions"][1]))
        self.mids, self.dirs, self.twoway = np.array(mids), np.array(dirs), np.array(twoway)
        self.tree = cKDTree(self.mids)

    def at(self, x, y, reach=15):
        """Unit direction of the nearest road within reach metres, flipped so
        that traffic keeping right passes (x, y); None when no road is near."""
        distance, k = self.tree.query((x, y))
        if distance > reach:
            return None
        ux, uy = self.dirs[k]
        rx, ry = x - self.mids[k][0], y - self.mids[k][1]
        if self.twoway[k] and ux * ry - uy * rx > 0:  # left of this edge: the opposite lane
            ux, uy = -ux, -uy
        return float(ux), float(uy)
