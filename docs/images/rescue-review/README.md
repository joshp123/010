# Actual browser transport review

Written by AI on 2026-10-24 by model GPT-6.

Native browser captures of unaccepted rescue candidates, not final product approval. Map-only views contain no private browser chrome.

- Bridge: 51.9109,4.4848,span280,bearing35,day. Full bridge-actual.jpg is1280×720; bridge-actual-detail.png is a native browser capture of CSS rectangle250,150,350,450 at scale2. The enlarged image resolves the manager's earlier false reading: cars are on grey carriageways and cyclists on orange outer paths. Source/runtime road600728317 also agrees. Do not move correct routes to match that earlier reading.
- Metro phone:390×844, actual reported D position focused through Find at51.9137001,4.481761,span220. Train readable, navigation works; capsule/fins/building intersection still reject the visual presentation.
- Blaak01/06/12: first/middle/last of12.79seconds at51.9184269,4.4845223,span240,bearing125,day,with7source-reviewed turn rules active. Cars traverse the junction; full spacing/conflict/journey quality remains under review.

## Newer source input in the actual runtime

The manager inspected these native browser captures using the newer municipal geometry and its own UVs. Desktop: Delfshaven at 200m span, bearing35; phone: Schiedamseweg at 200m span, bearing125, 390×844. Both settled without pending/refused tiles or loading errors. This is source-integration evidence, not art acceptance: photographic building islands, generic surrounding facades and dominant simple trees remain visibly inconsistent. The tower payload subsequently passed the production host and actual renderer after source-preserving external texture splitting.

![Newer municipal source among surrounding buildings](current-source-runtime-desktop.png)

![Actual phone view of source and fallback buildings](current-source-runtime-phone.png)

## Metro section without vehicle reports

A native desktop reproduction at51.92514,4.51261,span220,bearing35 shows the black section over apparent rooftops even with no vehicle reports. This interim static server has no API routes; it does not test transit freshness. All22 runtime terrain samples are measured, around−1.48 to−1.06m, with floor−13.48 to−13.06m. The recorded geometry is below ground. This rules out elevated sampled roofs as the cause in this view; clipping/composition remains rejected.

![Actual below-ground section still appears pasted over the city](metro-static-section.png)

[Actual section diagnostics](metro-static-section-diagnostics.json)

## Persistent junction queue after following-distance change

The manager reviewed17 native frames spanning27.73seconds, then repeated runtime position samples at84.90simulation seconds. Several leading motor vehicles remain at the same positions approaching185274103→600909887; white cars overlap near the queue head. Exact source/vehicle audits accompany the enlarged native capture. One car projects over a surveyed traffic-island polygon while another is over carriageway; do not generalise orange colour to cycle lanes. This is a new bounded failure, separate from the corrected bridge reading.

![Persistent queue and overlapping cars at the merge](blaak-stopped-queue-detail.png)

[First vehicle sample](blaak-following-audit-a.json), [repeated sample](blaak-following-audit-b.json), [actual underlying source surfaces](blaak-queue-surface-audit.json).


## Junction reservations and whole-feature metro opening

The newer junction reservation candidate clears the former stopped queue in actual native browser motion review. The retained first/last images span26.7seconds; four intermediate images were also inspected, followed by runtime sampling at78.6simulation seconds. The old car50 now travels a later road at7m/s. This supports queue progress, not full traffic acceptance. The traffic-island placement and broader journey legality remain open.

![Junction motion start](blaak-reservation-start.jpg)

![Junction motion end](blaak-reservation-end.jpg)

[Runtime vehicle and actual source-surface sample](blaak-reservation-audit.json).

The whole-feature metro candidate removes the worst roof fragments and makes the silver train readable at the same rejected51.92514,4.51261,220m,35degree view. The actual phone still shows an exposed strip with weak earth-boundary composition and distracting source-building outlines. Rotation to80degrees strengthens the floating-strip impression. The report changed during review, so the rotated frame has no observed train; this is not evidence of train movement. Surveyed ground/floor ranges remain correct. Visual acceptance remains open.

![Actual desktop whole-feature section](metro-whole-features-desktop.png)

![Actual phone whole-feature section](metro-whole-features-phone.png)

![Actual rotated section](metro-whole-features-rotated.png)

[Actual runtime section and report](metro-whole-features-runtime.json).
