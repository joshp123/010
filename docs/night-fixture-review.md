# Night fixture response candidate

Reviewed actual manager captures from public main: `combined-night35.png`,
`ground-fixture-night-desktop.png`, and `ground-fixture-night-phone.png` under
`docs/images/rescue-review/`. The earlier phone lacks the later supported glazing;
the combined desktop is the relevant evidence for its successful separation.

The broad cream facade bands come from a response that allowed almost horizontal
light below each head: its downward gate tested only vertical distance, not angle.
The replacement in `fixture-surface-lighting.js` softly confines illumination to
a downward distribution and tightens distance decay. All retained head anchors,
reach fields and lookup selection stay unchanged. Distribution and brightness
are illustrated, not measured photometry. This does not supply occlusion: light
can still reach a surface through an intervening wall. Source direction and
operational state are not known.

`miniature-style.js` reduces only the night emission of its generic fallback
window grid from 0.72 to 0.25. Source-supported glazing is a separate material path
and is unchanged. No window placements, diffuse colours, sky, exposure or daytime
shader terms change. Both modified contributions are zero at night=0.

The field contains 126,632 prepared source head anchors. A representative pair
near the reviewed row has the same native base X/Z but different IDs and heads:

| Native ID | Base local XYZ (m) | Head local XYZ (m) |
|---|---|---|
| ovl_20282 | −2934.960, 2.434, 583.155 | −2934.914, 14.484, 583.140 |
| ovl_100912 | −2934.960, 2.432, 583.155 | −2934.822, 10.754, 582.012 |

These are retained in `public/data/lamps/-3_0.glb`. Their operational relationship
is unresolved; do not arbitrarily delete one as a duplicate or invent an active
state. The two-head field can compound this source ambiguity.

`python scripts/inspect-night-fixture-response.py` reads these actual anchors and
produces `docs/images/night-fixture-response.png`: a receiver-plane diagnostic,
not an actual street screenshot. The manager must inspect the real candidate at
night on phone/desktop, verify the supported glazing remains legible and dominant,
and check daylight remains unchanged. Neither this diagram nor a build establishes
visual acceptance. Generic facades and their invented grid remain a source/detail
limitation requiring the wider art work.
