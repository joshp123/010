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

// Frozen, source-reviewed motor corridor interpretation. Validate the complete
// group before changing anything: a lone shifted edge would disconnect a node.
export function applyReviewedRoadGeometry(network,data) {
  if(data.version!==1||data.mode!=='motorcar'||!Array.isArray(data.patches))throw new Error('Unsupported road geometry review');
  const replacements=new Map();
  for(const patch of data.patches) {
    const matches=network.roads.filter(road=>road.id===patch.roadId);
    if(matches.length!==1||replacements.has(patch.roadId))throw new Error('Ambiguous road geometry match');
    const road=matches[0];
    // One 1e-7-degree unit tolerates the existing source/protobuf rounding.
    if(road.start!==patch.start||road.end!==patch.end||road.coordinates.length!==patch.expectedCoordinates.length||
      road.coordinates.some((point,i)=>point.some((v,j)=>Math.abs(v-patch.expectedCoordinates[i][j])>1.01e-7)))throw new Error('Road geometry source changed');
    if(!Array.isArray(patch.coordinates)||patch.coordinates.length<2||patch.coordinates.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v))))throw new Error('Invalid reviewed coordinates');
    replacements.set(road.id,{...road,originalCoordinates:road.coordinates,coordinates:patch.coordinates,geometryEvidence:data.sourceSurface});
  }
  let endpoint=null;
  for(const road of network.roads.filter(road=>road.start===data.sharedJunction||road.end===data.sharedJunction)) {
    const replacement=replacements.get(road.id);
    if(!replacement)throw new Error('Incomplete shared junction correction');
    const point=road.start===data.sharedJunction?replacement.coordinates[0]:replacement.coordinates.at(-1);
    if(endpoint&&point.some((v,i)=>Math.abs(v-endpoint[i])>1e-10))throw new Error('Inconsistent reviewed junction');
    endpoint=point;
  }
  if(!endpoint)throw new Error('Missing reviewed junction');
  network.roads=network.roads.map(road=>replacements.get(road.id)||road);
  return replacements.size;
}

// Additional height samples lie on the original NWB segments. They do not
// authorise a new route, change lane access or move a plan junction.
export function applySurfaceProfiles(network,data) {
  if(data.version!==1||!Array.isArray(data.roads))throw new Error('Unsupported surface profile');
  let count=0;
  for(const profile of data.roads) {
    const matches=network.roads.filter(road=>road.id===profile.roadId);
    if(!matches.length)continue;
    if(matches.length!==1)throw new Error('Ambiguous surface profile road');
    const road=matches[0];
    if(road.coordinates.length!==profile.expectedCoordinates.length||road.coordinates.some((p,i)=>p.some((v,j)=>Math.abs(v-profile.expectedCoordinates[i][j])>1.01e-7)))throw new Error('Surface profile source changed');
    if(!Array.isArray(profile.coordinates)||profile.coordinates.length<2||profile.coordinates.some(p=>p.length!==2||p.some(v=>!Number.isFinite(v))))throw new Error('Invalid surface profile');
    road.originalCoordinates=road.originalCoordinates||road.coordinates;
    road.coordinates=profile.coordinates;road.surfaceProfileEvidence=data.source;count++;
  }
  return count;
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

// Reservations belong to queue heads, never whichever vehicle happens to be
// first in the instance array. Keep the winner until its rear clears the node.
// This is illustrative unsignalled yielding, not a sourced traffic-light model.
export function createJunctionArbitrator() {
  const reservations=new Map(), waiting=new Map();
  return {
    clear() { reservations.clear(); waiting.clear(); },
    update(cars,occupants,delta) {
      const active=new Set(cars), heads=new Map();
      for(const [junction,claim] of reservations) {
        const car=claim.car;
        let travelled=(car.direction===1?car.distance:car.road.length-car.distance)-claim.progress;
        for(let i=claim.step;i<car.journeyIndex;i++)travelled+=car.journey.path[i].road.length;
        if(!active.has(car)||travelled>=claim.clearance)reservations.delete(junction);
      }
      for(const car of waiting.keys())if(!active.has(car))waiting.delete(car);
      for(const car of cars) {
        const remaining=car.direction===1?car.road.length-car.distance:car.distance;
        if(car.ending||!car.next||remaining>=10) { waiting.delete(car); continue; }
        // Every same-lane vehicle ahead counts, even if it is too far away for
        // normal braking. A follower cannot reserve on its leader's behalf.
        const leader=(occupants.get(car.road)||[]).some(other=>other.vehicle!==car&&other!==car&&other.direction===car.direction&&
          (other.distance-car.distance)*car.direction>0);
        if(leader) { waiting.delete(car); continue; }
        const junction=car.direction===1?car.road.end:car.road.start;
        if(!junction)continue;
        waiting.set(car,(waiting.get(car)||0)+delta);
        // Leave enough downstream room to clear the crossing. A blocked exit
        // cannot monopolise the junction against another usable exit.
        if(routeFollowingGap(car,occupants,remaining+5.5)<remaining+5.5)continue;
        if(!heads.has(junction))heads.set(junction,[]);
        heads.get(junction).push({car,remaining});
      }
      for(const [junction,candidates] of heads) {
        if(reservations.has(junction))continue;
        candidates.sort((a,b)=>(a.remaining<3?0:1)-(b.remaining<3?0:1)||
          waiting.get(b.car)-waiting.get(a.car)||a.remaining-b.remaining||a.car.vehicleId-b.car.vehicleId);
        const {car,remaining}=candidates[0];
        reservations.set(junction,{car,step:car.journeyIndex,progress:car.road.length-remaining,clearance:remaining+5.5});
        waiting.delete(car);
      }
      return new Map([...reservations].map(([junction,claim])=>[junction,claim.car]));
    },
  };
}
