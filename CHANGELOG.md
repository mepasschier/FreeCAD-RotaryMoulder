# Changelog

All notable changes to the Rotary Moulder Workbench are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

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
