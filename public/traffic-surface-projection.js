// Height samples follow the exact source polyline. They do not add route links.
// Sparse plan vertices otherwise interpolate beneath a curved surveyed deck.
export function projectSourceRoadSurface(source, project) {
  const context = { source: 'NWB', roadId: source.id, roadClass: source.roadClass };
  const sourcePoints = source.coordinates.map(([longitude, latitude]) => project(latitude, longitude, .2, context));
  const roadTouchesDeck = sourcePoints.some(point => point.userData?.surfaceSource === 'surveyed bridge deck');
  const points = [sourcePoints[0]], coordinates = [source.coordinates[0]];
  for (let index = 1; index < sourcePoints.length; index++) {
    const start = sourcePoints[index - 1], end = sourcePoints[index];
    const samples = roadTouchesDeck ? Math.max(1, Math.ceil(Math.hypot(end.x - start.x, end.z - start.z) / 3)) : 1;
    const before = source.coordinates[index - 1], after = source.coordinates[index];
    for (let sample = 1; sample <= samples; sample++) {
      const fraction = sample / samples;
      const coordinate = sample === samples ? after : [before[0] + (after[0] - before[0]) * fraction, before[1] + (after[1] - before[1]) * fraction];
      coordinates.push(coordinate);
      points.push(sample === samples ? end : project(coordinate[1], coordinate[0], .2, context));
    }
  }
  const distances = [0];
  for (let index = 1; index < points.length; index++) distances.push(distances[index - 1] + Math.hypot(points[index].x - points[index - 1].x, points[index].z - points[index - 1].z));
  const deckSamples = points.map((point, index) => point.userData?.surfaceSource === 'surveyed bridge deck' ? index : -1).filter(index => index >= 0);
  for (let index = 0; index < points.length; index++) {
    if (points[index].userData?.surfaceSource === 'surveyed bridge deck') continue;
    const before = deckSamples.findLast(sample => sample < index), after = deckSamples.find(sample => sample > index);
    if (before === undefined || after === undefined) continue;
    const fraction = (distances[index] - distances[before]) / (distances[after] - distances[before]);
    const bridgeEdgeHeight = points[before].y - .2 + (points[after].y - points[before].y) * fraction;
    points[index] = project(coordinates[index][1], coordinates[index][0], .2, { ...context, bridgeEdgeHeight });
  }
  return { points, coordinates };
}
