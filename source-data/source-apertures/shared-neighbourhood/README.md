Written by AI on 2026-10-25 by model GPT-6.

These observations identify conservative pane interiors across the four retained source elevations of the adjoining neighbourhood. They are model judgements made from the source photographs; there is no dark-pixel classifier, inferred window grid or household activity schedule. Ambiguous, shuttered and occluded regions are excluded. Coverage is deliberately partial, including buildings with no observed pane regions.

The existing northern observations are retained in their original source frame. New shared observations use the source collection anchor. `prepare-neighbourhood-aperture-emission.py` transforms those registered cameras into each original leaf frame, then the depth-tested pane assembler writes only the separate emission channel into the original UVs. The original source geometry, RTC, matrix, identities and current daytime artwork are retained. Roof triangles cannot receive this channel.

The current daytime input is the art handoff `shared-neighbourhood/model-fields/bound-shared-neighbourhood-composition-priority`. Source photographs and depth are in its parent model-fields directory. `source-view-registration.json` pins the observed cameras and raw image/depth hashes. `observations.json` pins the six-source fingerprint and pane vectors. The art checkout retains the original six B3DM inputs and photographs.

Warm emission illustrates glazing at night. It does not describe occupancy, household activity, opening hours or measured real-time lights. Unobserved areas remain dark. Common-city day/dusk/night and opposing phone inspection is required after any reassembly; successful compilation is not visual acceptance.

The same observations can be reassembled against corrected daytime fields without further window generation. Pack each output child with the existing prepare-bound-artwork.py and prepare-artwork-residency.py tools. Only the final spatial runtime assets are required by the browser.

For later daytime handoffs with identical original geometry and UVs, `rebind-source-aperture-emission.py PREVIOUS_BOUND CURRENT_DAY OUTPUT_BOUND` reuses the already projected original-atlas pane channel. It compares the actual geometry buffer, accessors, mesh/node structure and image correspondence before rebinding. This avoids reinterpreting windows when only daytime drawing changes. The contiguous 19-leaf handoff retains the existing six observed leaves this way; its other leaves have no new pane observations. Runtime Git retains the packed current collection.
