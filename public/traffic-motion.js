// Decorative motion rules, isolated from Three.js so they can be re-evaluated.
// x east, z south: the right-hand normal of (dx,dz) is (-dz,dx).
export function rightHandOffset(dx, dz, direction, distance, length, twoWay) {
  const magnitude = Math.hypot(dx, dz) || 1;
  // Meet at surveyed junctions, instead of jumping between differently offset edges.
  const taper = Math.min(1, Math.max(0, distance) / 8, Math.max(0, length - distance) / 8);
  const offset = twoWay ? 1.15 * direction * taper : 0;
  return [-dz / magnitude * offset, dx / magnitude * offset];
}

export function turnWeight(incoming, outgoing) {
  const dot = (incoming[0] * outgoing[0] + incoming[1] * outgoing[1]) /
    (Math.hypot(...incoming) * Math.hypot(...outgoing) || 1);
  // A different source edge can still double back along the same physical road.
  if (dot < -.5) return 0;
  return Math.max(.08, (dot + 1) ** 3);
}

export function safeStep(delta) {
  // Resume from a suspended/slow frame without travelling across the whole screen.
  return Math.min(.1, Math.max(0, delta));
}

export function followingDistance(speed) { return 5.5 + speed * 1.4; }
export function speedForRoadClass(roadClass) {
  // NWB HR is hoofdrijbaan, NOT a motorway designation. No speed-limit source here.
  return roadClass === 'ERF' ? 3.5 : 7;
}

// Distance to a same-direction leader along this vehicle's already chosen trip,
// including short source junction links. Seeing only the current road lets a
// queued vehicle disappear from following logic just as the follower enters it.
export function routeFollowingGap(car, occupants, range = followingDistance(car.speed)) {
  let nearest=Infinity;
  let offset=-(car.direction===1?car.distance:car.road.length-car.distance);
  const path=car.journey.path;
  for(let index=car.journeyIndex;index<path.length&&index<car.journeyIndex+16;index++) {
    const {road,direction}=path[index];
    for(const other of occupants.get(road)||[]) {
      if(other===car||other.vehicle===car||other.direction!==direction)continue;
      const gap=offset+(direction===1?other.distance:road.length-other.distance);
      if(gap>0&&gap<=range)nearest=Math.min(nearest,gap);
    }
    offset+=road.length;
    if(offset>range)break;
  }
  return nearest;
}
