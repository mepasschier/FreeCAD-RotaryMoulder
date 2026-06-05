# Changelog

All notable changes to the Rotary Moulder Workbench are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

## [1.3.1] - 2026-06-05

### Fixed
- `package.xml`: removed malformed elements (`<name>`/`<description>`
  inside `<workbench>`, the `<tags>` wrapper, and the non-schema
  `<dependencies>` block). Dependencies are now declared inside
  `<workbench>` with `<freecadmin>` and `<depend>`. Description
  collapsed to a single line; tags reduced to three. Required for
  Addon Index compliance (issue #50).

## [1.3.0] - 2026-05-27

### Added
- **Roster (lattice) detail.** A new `CavityRoster` object turns a
  centerline sketch into a lattice of bars on the cavity/cup floor - each
  line becomes one bar. Properties: `BarWidth`, `Depth`, `DraftAngle`,
  and `Mode` (emboss = raised bars, engrave = recessed grooves). Bars
  have a drafted trapezoidal cross-section and are built cylinder-
  conformally so they blend cleanly where they cross, with no twist.
  Draw the roster as simple centerlines (a closed boundary wire in the
  sketch, if present, is ignored - only the bar lines are used).
- **Add Roster command + toolbar button** (with icon). Select a cavity,
  cavity pattern, or cutting cup together with a centerline sketch, then
  run the command and set bar width / depth / draft / mode in the dialog.
- **Rosters work everywhere details do:** on regular cavities, cutting
  cups, and their patterns, in both emboss and engrave modes.
- **Engraved rosters are clipped to the flat floor.** An engraved groove
  that reached the edge of the floor used to tunnel underneath the
  drafted/chamfered wall, hollowing a cavity there. Engraved roster bars
  are now automatically clipped to the floor footprint (where the flat
  floor meets the wall), and the clipped end is itself drafted at the
  roster draft angle so the groove closes off cleanly for release.
  Embossed rosters are left unclipped (raised bars simply meet the wall).

### Fixed
- **Engraved letter/ShapeString details on regular cavities** could leave
  a thin floor film under a glyph and drop part of the cavity floor. The
  detail builder's fallback path was reverted to its proven behavior so
  text engraves cleanly again.

## [1.2.1] - 2026-05-26

### Fixed
- **Detail features now fuse reliably to the cavity/cup floor.** Embossed
  and engraved details were built exactly tangent to the floor surface,
  which made the boolean unreliable: an emboss bump could attach as a
  loose shell with a visible seam (and be dropped by a later docker-pin
  operation), and an engrave could leave a thin film instead of cutting
  through. Detail bases now embed a hair (0.02 mm) past the floor so the
  chunk overlaps cleanly. Visible feature depth is unchanged. This also
  improves regular moulder cavities, not just cutting cups.
- **A failed glyph no longer drops a whole word.** When fusing a
  multi-letter detail, if the combined (batched) fuse failed or produced
  a null shape, the entire detail was previously discarded. The fuse now
  falls back to fusing each letter individually, so one problematic glyph
  is skipped with a warning while the rest of the text is preserved.

## [1.2.0] - 2026-05-26

### Added
- **Cutting roll cutting cups.** A new `CuttingCup` object builds the
  whole cookie as a raised body sitting on the drum surface (instead of a
  cavity cut into the drum), for making cutting rolls. It has a solid
  floor band on the drum and a drafted cavity above it that rises to a
  sharp cutting edge following the cookie outline. Properties:
  `CookieThickness`, `FloorThickness`, `DraftAngle`, `ChamferDistance`
  (inner cavity-to-floor corner only — the outer cutting wall stays a
  clean straight draft to the drum), `CrownFlat` (cutting-edge flat width;
  the flat grows outward so the inner cavity opening always matches the
  sketch), and `FuseToDrum`.
- **Cutting cups support Details and Docker pins**, applied on the cup's
  cavity floor exactly like cavities (the same Add Detail / Add Docker
  Pins commands now accept a cutting cup as the parent).
- **`CuttingCupPattern`** replicates a cutting cup (with its details and
  dockers) around and along the drum, additively (cups are fused, not
  cut). Honors the source cup's `FuseToDrum` (one fused roll, or separate
  cup bodies).
- **Toolbar / menu**: new **Add Cutting Cup From Sketch** and **Pattern
  Cutting Cups Around Drum** commands, with icons. The existing **Add
  Detail** and **Add Docker Pins** commands now also work on cutting cups.
- Cutting cups reuse the chamfer offset machinery, so all supported cavity
  shapes work: scalloped, rectangular, circular, elliptical, and
  rounded-rectangle (filleted-corner) outlines.

### Notes
- No changes to existing cavity / pattern behavior or properties; cutting
  cups are an additive feature alongside the existing moulder cavities.

## [1.1.1] - 2026-05-25

### Fixed
- **Chamfer now works on elliptical cavity outlines.** An ellipse is a
  single non-circular curve; it was previously mis-handled (treated like
  a straight segment), distorting the cavity. It is now offset with a
  true uniform perpendicular offset (sampled along the curve's inward
  normal), giving a clean drafted wall and chamfer.
- **Chamfer now works on rounded-rectangle outlines** and any outline
  with tangent line↔arc junctions (e.g. filleted corners). At a tangent
  junction the offset wall and the offset fillet are joined at their
  exact tangent point instead of by intersecting the two offsets, which
  was numerically unstable and distorted the fillet. Filleted corners
  now chamfer cleanly, staying tangent to the drafted walls.

### Notes
- No API or property changes. Scalloped, rectangular (sharp-corner),
  and circular cavities are unaffected and use the same code paths as
  v1.1.0.

## [1.1.0] - 2026-05-24

### Added
- **Parametric wall-to-floor chamfer** on cavities. A new
  `ChamferDistance` property (mm) eases the inner wall-to-floor corner
  for cleaner dough release. Set to `0` for a plain drafted cavity
  (previous behavior). Editable live from the Data tab — changing it
  rebuilds the cavity while keeping the wall draft angle and the 45°
  chamfer constant.
- Chamfer works for scalloped, rectangular, and circular cavity
  outlines (analytic perpendicular offset on the unrolled drum surface,
  projected per-edge so sharp corners are preserved).

### Changed
- Cavity and Pattern property `FilletRadius` is renamed to
  `ChamferDistance`. Documents saved with the old property are migrated
  automatically on open (the old value is carried over).
- The "Add Cavity From Sketch" and "Pattern Cavities" dialogs now ask
  for a **Chamfer distance** instead of a fillet radius.

### Removed
- The old post-hoc `makeFillet` rounding of cavity floor edges (it
  failed on the BSpline floor geometry). The chamfer is now built
  directly into the cavity loft.

### Notes
- The chamfer falls back to a plain cavity automatically if it cannot
  be built for a given outline (e.g. freeform/B-spline edges), so
  existing models always still produce a valid cavity.

## [1.0.1] - 2026-05-22

- Docker-pin / mesh-export fix: pin bases embed slightly below the
  cavity floor so they punch cleanly through, eliminating degenerate
  open slivers that caused a missing floor face on `.3mf` export.

## [1.0.0]

- Initial release: drafted cavities, letter/shape details (engrave /
  emboss), docker pins, linear and alternating patterns, debug toggle.
