# Changelog

All notable changes to the Rotary Moulder Workbench are documented here.
This project adheres to [Semantic Versioning](https://semver.org/).

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
