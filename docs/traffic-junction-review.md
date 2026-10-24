# Blaak queue correction

Manager native capture of c38d61f at 51.918427, 4.484522, span 200m,
showed cars 2, 17, 20, 43 and 50 stopped at identical positions 27.73 seconds
apart. The exact JSON captures are retained as test fixtures from upstream
commit 75cf50d (Git blobs 6557b0811e292fb8fc12def754457ea452f12d95 and
7707ce071422ba0c0ebf4307d35aa79fd56a627d).

Car 2 was first in the instance array but behind car 17 on NWB 185274103.
The previous per-frame loop granted car 2 junction 185274094 before evaluating
car 17. Following logic correctly stopped car 2 behind car 17, while the
reservation incorrectly stopped car 17 for car 2. This was a permanent
circular wait, not a disconnected source route.

Reservations now select incoming lane heads before movement. Followers cannot
reserve; a head needs room beyond its chosen exit. Waiting heads take priority,
with vehicles already inside the three-metre stop approach clearing first.
The winner retains the crossing until its centre travels 5.5m beyond the node,
preventing a conflicting merge from being released as soon as the centre
crosses. Removed vehicles and projection replacement release their claims.

`node tests/traffic-junctions.test.mjs` loads actual retained multipart NWB
geometry/junctions and the native capture lengths and positions. It replays the
five-car queue for 60 seconds in both array orders, verifies all complete their
unchanged connected paths, and checks crossing clearance and stale claims.
The separate motion, following, restriction and model tests and production
build also pass. No route coordinates, bridge surfaces or legal rules changed.

This remains illustrative unsignalled yielding, without a sourced signal timing
or right-of-way model. The test verifies route progress, not visual acceptance
or a complete traffic microsimulation. Native visual review remains the manager's
responsibility; the cloud renderer cannot run WebGL and the GitHub connector
refused the native PNG as non-UTF-8. No acceptance claim follows from the build.
