# Retained turn-restriction review input

Written by AI on 2026-10-24 by model GPT-6.

The manager acquired `osm-centre-turn-restrictions.json.gz` on 2026-10-24 from the public Overpass endpoint using the exact bounded query retained in `osm-turn-restriction-audit.json`. It contains 63 restriction relations, 113 member ways and 574 nodes around central Rotterdam and Erasmusbrug. Original public response bytes are gzip-retained, without contributor identity fields.

Source: [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/). This is source-review data, separate from MIT application code. Preserve source attribution and ODbL handling for derived databases. No runtime turn restriction has been activated by this acquisition.

The initial audit's zero candidates are rejected as a tool failure: every retained NWB feature is a MultiLineString, while the initial matcher accepts only LineString. It therefore skips all actual roads before attempting matches. Correct the matcher against actual retained input, review geographic/semantic alignment and then integrate supported turn rules. The initial audit remains evidence of that failure, not a claim of absent restrictions or legal completeness.
