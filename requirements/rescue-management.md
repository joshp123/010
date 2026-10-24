# Rescue management

Written by AI on 2026-10-24 by model GPT-6.

Read [the rescue brief](rescue.md), [original steering](steering.md) and [product contract](README.md) before dispatching work. Latest steering requires a deep, holistic rescue and comparison with how the reference projects were actually made.

## Current judgement

The published scene has not met visual acceptance. No rescue candidate has been published.

The quieter mobile controls are useful supporting work. Flat generic facades, oversized simple trees, weak roof/street detail, noisy night lighting and lifeless ground/water still fail the references. Traffic motion, cyclists and the revised metro presentation need actual rendered review.

Both prior-art projects generate illustration offline from aligned textured source renders. NYC uses fine-tuning and neighbour-aware infill; London uses fine-tuning and overlapping shared-latent sampling. This differs fundamentally from recolouring live 3D geometry. See [NYC's process](https://cannoneyed.com/projects/isometric-nyc) and [London's process](https://tiny.london/how/).

The municipal source pilot restores useful facade/roof evidence. Palette filtering is rejected as an art solution. Native model-based atlas editing is available, but the independent pilot also failed production acceptance: invented detail, baked shadows and unverified UV alignment. Neither proves faithful citywide illustration or feasible throughput.

## Active work and next review

Cloud implementation owns the source/renderer correction, art pilot and supporting transport work. The manager independently reviews local rendered desktop/phone output because the cloud browser cannot create Rotterdam's WebGL context.

The source pilot currently renders its textured buildings but removes surrounding fallback buildings, leaving their shadows. This is a rejected integration regression. Restore a trustworthy source render before using it as an illustration input.

Then test adjacent source-rich neighbourhood views, ordinary residential streets and a port sample. Judge faithful structure, consistent adjoining artwork, separate night lighting and correct moving-actor occlusion. Establish accepted area, retries and generation time before scaling. Preserve sources and replaceable interpretation throughout. A polished landmark, build or feature count cannot close this rescue.

The scheduled manager check remains active. Reconcile every new result against the whole municipality and original weather, night, transit, metro, export, free-resource and privacy constraints. Disable it only when the result meets the brief or Josh stops the work.
