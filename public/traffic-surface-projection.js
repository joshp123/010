// Height samples follow the exact source polyline. They do not add route links.
// Sparse plan vertices otherwise interpolate beneath a curved surveyed deck.
export function projectSourceRoadSurface(source, project) {
  const context = { source: 'NWB', roadId: source.id, roadClass: source.roadClass };
  const sourcePoints = source.coordinates.map(([longitude, latitude]) => project(latitude, longitude, .2, context));
  const points = [sourcePoints[0]], coordinates = [source.coordinates[0]];
  for (let index = 1; index < sourcePoints.length; index++) {
    const start = sourcePoints[index - 1], end = sourcePoints[index];
    const surveyedDeck = [start, end].some(point => point.userData?.surfaceSource === 'surveyed bridge deck');
    const samples = surveyedDeck ? Math.max(1, Math.ceil(Math.hypot(end.x - start.x, end.z - start.z) / 3)) : 1;
    const before = source.coordinates[index - 1], after = source.coordinates[index];
    for (let sample = 1; sample <= samples; sample++) {
      const fraction = sample / samples;
      const coordinate = sample === samples ? after : [before[0] + (after[0] - before[0]) * fraction, before[1] + (after[1] - before[1]) * fraction];
      coordinates.push(coordinate);
      points.push(sample === samples ? end : project(coordinate[1], coordinate[0], .2, context));
    }
  }
  return { points, coordinates };
}
