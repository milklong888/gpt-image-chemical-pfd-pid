# Provenance and retired-engine boundary

This candidate does not migrate the old engine. The fixed non-commercial upstream is `Ahuaisnotficklehearted/chemical-autocad-drafting1.3`, commit `f660054c1b696bac845500816aabcd2dc745a901`.

The maintainer audit read that commit's tree and all 31 Python source blobs in memory, verified each Git blob identity, and compared the proposed independent modules. No upstream source is retained in this candidate. `audit/upstream-comparison.json` reports that the selected new modules have no same-basename upstream file and no exact forty-token overlap. This comparison alone is not treated as proof of copyright ownership.

There is separate local development evidence: the PFD-v2 installation record installs `pfd_guard.py` and its synthetic tests separately from `pfd_guard_legacy.py` and the `chemcad_*` adapters. Its frozen validation report identifies 34 independent Shapely cases separately from 27 legacy adapter cases. The retained `test_pfd_guard.py` still has SHA256 `3c8cdedb091157297514e26aec46011836b4ec6a856dbc09e1ff70063a7cd560`, identical to that new-module test record. The installation also records the independent router, native source-geometry helper and Node wrapper separately from the old generator. The later dependency audit confirms that the current copied router has no legacy-import closure.

The following files are retained independent project modules, with original headers and implementation unchanged:

- `python/pfd_guard.py`: explicit geometry contract and atomic validation.
- `python/pfd_router.py`: independent bounded libavoid candidate adapter and simplification checks; no old `route_pipes` adapter.
- `python/pfd_source_geometry.py`: numerical primitive snapshot helper.
- `python/audit_lineweight_continuity.py`: independently added effective-lineweight resolver/auditor.
- `python/pfd_runtime/route.mjs`: project directional API wrapper, not the libavoid implementation.
- `tests/test_pfd_guard.py`: the separate independent synthetic guard suite.

`pfd_primitives.py`, the portable CLI, new synthetic tests and optional native parameterization are new bounded implementations prepared for this public package. Native readback functionality is adapted from this project's independently authored large-drawing runner, not from the retired PFD engine. The exact prior `NativeWriteGuard.cs` source is retained; the reader removes private case IDs, object counts, plot windows and machine paths.

No implementation from the non-commercial engine's `chemcad_*`, `draw_pfd`, BKP converter, old symbol generator, locate/preview/catalog helpers or legacy adapters is included. Merely lacking an import dependency would not make one of those upstream-derived files eligible.

The candidate contains no standards text, source drawing, user geometry, font, commercial SDK/DLL, model weights, semantic index or private project receipt. Synthetic fixtures are explicitly marked. Runtime output and compilation products are excluded from the publication allowlist.

The main maintainer selects the first-party repository license under the user's publication authorization. No existing upstream restriction or dependency license is replaced by that choice. Detailed source hashes, evidence paths and exclusions are retained in the preparation report for review.
