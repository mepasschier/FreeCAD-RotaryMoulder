# Changelog

All notable changes to the Rotary Moulder Workbench are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

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
