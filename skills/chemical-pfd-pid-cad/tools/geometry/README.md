# Portable geometry and optional native readback

This is the independently scoped drawing core, not the retired full PFD engine. It accepts explicit geometry and caller-reviewed connections. It does not decide a process route, size equipment, infer control logic, supply licensed symbols, certify a standard, or substitute DXF checks for native DWG evidence.

The original non-commercial upstream engine, its entry points, case drawings, standard texts, user source archives, indexes, SHX fonts, SDKs and DLLs are excluded. See `PROVENANCE.md` and `THIRD_PARTY_NOTICES.md` for the exact boundary.

## Offline Python use

Python 3.10+ with Shapely 2.1+ and ezdxf 1.4.3+ is required. From this directory:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
pfd-geometry validate examples/synthetic-route.json --report validation-output/validation.json
```

`pfd_guard` checks explicit boundary ports and outward directions, minimum leads, complete filled equipment polygons, foreign-body contact, owner reentry, route self-crossing, overlaps and pipe clearance. Failed routes never enter a scene. Its contract is `pfd-guard/v1`; the example's three boxes are synthetic test obstacles, not chemical symbols or an engineering design.

`pfd_router` retains only the independent bounded libavoid adapter. Routing is optional and requires separately installing the LGPL dependency in the checked-out runtime directory:

```sh
cd python/pfd_runtime
npm install --ignore-scripts
cd ../..
pfd-geometry route examples/synthetic-route.json --runtime python/pfd_runtime --report validation-output/routed.json
```

Node must be on PATH or explicitly set by `PFD_NODE`. The wheel does not bundle Node, libavoid-js, wasm or the optional runtime directory; `--runtime` must always be explicit. Bounded connection-order search and local detour simplification do not prove a global routing optimum. Shared process junctions and automatic crossing topology are not implemented by this router.

### Reviewed layout checkpoints

Connections may include `"checkpoints": [[x1, y1], [x2, y2]]` in source-to-target world-coordinate order. Coordinates must be finite two-component numbers, without booleans, repeats or points coincident within the declared linear tolerance. The independent guard checks actual segment-interior hits and traversal order even for routes supplied without this router. Simplification may remove a collinear vertex but cannot remove its required geometric hit. No checkpoint is a collision or lead-direction exemption.

The adapter sends only middle-route checkpoints to libavoid: points already met on the fixed source/target leads remain in the full pipe contract and are independently checked on the final path. It rejects inconsistent fixed-lead order instead of revisiting a port inside the buffered equipment. An unreachable constraint stops the candidate without committing it. An omitted field preserves prior behavior; an explicit empty list adds no constraints.

For middle checkpoints, use the current packaged `route.mjs`, not an older wrapper with the same libavoid version. This adapter uses tiny internal pin-boundary anchors and a translated, axis-aligned candidate frame; both are candidate-generation details, not added drawing symbols or process connections. The full result returns to world coordinates and passes the unchanged independent guard. It tries the default checkpoint directions then at most 16 fixed direction-pair variants, without privileging one case's direction. A variant shares its direction pair across all checkpoints; this is not an exhaustive search of all per-point combinations. Empty or invalid candidates are rejected, and exhausted search stops without committing a failed route. Four right-angle source directions and long declared leads have bounded regression cases; arbitrary-angle ports remain unsupported by this orthogonal adapter.

The upstream [ShapeConnectionPin](https://www.adaptagrams.org/documentation/classAvoid_1_1ShapeConnectionPin.html), [Checkpoint](https://www.adaptagrams.org/documentation/classAvoid_1_1Checkpoint.html) and [ConnRef](https://www.adaptagrams.org/documentation/classAvoid_1_1ConnRef.html) describe the underlying pin/via-point API. These references do not replace checks on the actual bound JS version or guarantee that a generated path is free of self-intersection. The adapter's full-path independent guard remains authoritative.

Choose a few justified corridor points from the reviewed layout, not every image pixel. Recheck them after moving equipment or annotations. This interface does not accept arbitrary corridor polygons and does not automatically register all text/flag/leader obstacles. Those still require caller-owned annotation coverage and final native checks. The tests distinguish mocked transport from the separately enabled real libavoid cases.

`pfd_source_geometry` is a primitive snapshot/comparison helper. It performs numerical field comparison; it does not establish source completeness or handle all mathematically equivalent ellipse parameterizations. `audit_lineweight_continuity` resolves actual INSERT/ByLayer/ByBlock inheritance and refuses unresolved DEFAULT/hairline widths. It does not certify CTB/STB, viewport or printer overrides.

## Continuous jumps and selected-arrow draw order

`pfd_primitives.Jump` creates and checks a new bounded vertical LINE/three-tangent-ARC/LINE route. Radius is an explicit caller display choice, not a standard dimension. `audit_jump` requires explicit `paper_mm_per_unit` to convert physical lineweight to drawing-unit ink width; it never silently assumes that source units are millimeters. It supports a declared continuous horizontal under-line, left or right jump direction, full-curve checks, explicit body/label/arrow obstacles and protected branch/port points. It rejects a junction dot at the logical nonconnection. Caller-supplied context is not represented as a complete project audit.

`arrows_to_front` requires explicit unique arrow handles. Only straight tapered two-point LWPOLYLINE heads and explicitly selected triangular SOLIDs are supported. It preserves all entity geometry/style and non-arrow relative order, writes the persistent DXF SORTENTSTABLE, and enables plotting sort in the drawing. Other SOLIDs are not automatically selected. `audit_arrow_order` checks saved DXF order and label contact; it explicitly does not claim native draw order was verified.

The tests save and reopen synthetic DXFs before evaluating positive/negative bridge and arrow cases. They include missing arcs, broken endpoints, wrong side, mismatched width, protected T contacts, body/arrow/label collisions, false dots, interrupted under-lines, lowered arrows and disabled plotting order.

## Optional AutoCAD readback source

`native/NativeAudit.cs` and `NativeWriteGuard.cs` are a parameterized source adaptation of this project's separately executed native readback work. No binary or SDK is distributed. The public parameterization is compile-tested only; it has not been executed in AutoCAD as this package version.

Compile with explicit paths to a caller-owned .NET 8 runtime, Windows Desktop runtime, compiler and licensed AutoCAD 2026 installation:

```sh
python native/compile_native.py --csc PATH_TO_CSC --runtime-dir NET8_RUNTIME --desktop-runtime-dir NET8_DESKTOP_RUNTIME --autocad-dir AUTOCAD2026_DIRECTORY --out build/native
```

The `PFDAUDIT` command uses an explicit `PFD_NATIVE_AUDIT_JOB` JSON file, side-opens the exact SHA-bound DWG read-only, verifies unchanged input bytes, writes strict native DxfOut, and records actual fonts and hashes, TEXT/MTEXT extents, XDATA identities and complete `DrawOrderTable.GetFullDrawOrder(0)/(32)` results. Optional arrow handles must be the actual input DWG handles; DXF-import renumbering must be resolved by an external source-identity contract. Omitting expected arrow/font identities produces evidence, not an identity acceptance claim.

`emit_script.py` only emits a reviewable script. It verifies the explicit DLL hash, sets and reads REPORTERROR=0 before NETLOAD, reads security settings, and requires exact `findtrustedfile` matching. It does not deploy, launch CAD, change SECURELOAD/TRUSTEDPATHS, set a system CER registry switch, or grant trust. Before manual execution, deploy only reviewed bytes to an already trusted exact directory, use an isolated CoreConsole profile and monitor report/crash processes. Stop on any native abnormality; do not blindly repeat failures.

This optional package does not import DXF to DWG, generate layouts/PDFs, create a complete PFD or implement automated process design. Those are separate workflow stages. Successful compilation is not native runtime validation.

### Output preservation regression

The optional native reader requires an absolute output directory that does not yet exist; its parent must exist. It atomically owns that directory, reserves its receipt with CreateNew and publishes exact native DXF bytes without replacing an existing target. A rejected reused path writes only to the console. The pure Windows/.NET output helper has 13 actual filesystem tests, including a control reproducing the former finally-overwrite defect; this is not an AutoCAD execution test. Sources and a compiler runner are in native/OwnedNativeAuditOutputTest.cs and native/run_output_tests.py.
