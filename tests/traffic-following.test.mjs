import assert from 'node:assert/strict';
import {routeFollowingGap} from '../public/traffic-motion.js';
const a={length:100},junction={length:3},b={length:100},branch={length:100};
const car={road:a,direction:1,distance:97,speed:7,journeyIndex:0,journey:{path:[{road:a,direction:1},{road:junction,direction:1},{road:b,direction:1}]}};
const lead={road:b,direction:1,distance:2};
assert.equal(routeFollowingGap(car,new Map([[a,[car]],[b,[lead]]])),8,'queued vehicle remains visible across a three-metre source junction connector');
assert.equal(routeFollowingGap(car,new Map([[branch,[{road:branch,direction:1,distance:1}]]])),Infinity,'different outgoing branch is not a leader');
assert.equal(routeFollowingGap(car,new Map([[b,[{...lead,direction:-1}]]])),Infinity,'opposite lane is not a following leader');
assert.equal(routeFollowingGap(car,new Map([[a,[car,{...car,distance:95}]]])),Infinity,'vehicle behind does not stop the leader');
assert.equal(routeFollowingGap(car,new Map([[a,[car,{...car,distance:99}]],[b,[lead]]])),2,'closest leader wins');
const reverse={...car,road:b,direction:-1,distance:3,journeyIndex:0,journey:{path:[{road:b,direction:-1},{road:junction,direction:-1},{road:a,direction:-1}]}};
assert.equal(routeFollowingGap(reverse,new Map([[a,[{road:a,direction:-1,distance:98}]]])),8,'reverse source orientation uses distance from the correct entry');
assert.equal(routeFollowingGap(car,new Map([[b,[{...lead,distance:90}]]])),Infinity,'distant traffic does not brake this vehicle');
console.log('Planned-route following checks passed across short connectors, direction and branch changes.');

assert.equal(routeFollowingGap(car,new Map([[a,[{vehicle:car,direction:1,distance:98}]]])),Infinity,'snapshot identity must not turn the follower into its own leader');
