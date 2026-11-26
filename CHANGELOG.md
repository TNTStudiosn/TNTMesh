# Changelog

## 0.2.0-alpha.2

- Added editable concave contours with point-by-point and freehand viewport drawing.
- Added pin and socket mesh templates with volumetric fit checks and preserved dimensions.

## 0.2.0-alpha.1

- Added a persistent Draft mode for dependent cuts, with stable part IDs and transactional rebuilding.
- Added exact rotation and viewport line drawing for plane positioning.
- Added cubic Bézier splits, rectangular and elliptical extraction, and splits using another mesh as a cutter.
- Added multiple connectors and separately printable pins for straight cuts.
- Added per-piece OBJ and FBX export and basic repair that preserves the original model.
- Added stable and experimental indices for Blender's native extension manager, served through GitHub Pages.

## 0.1.0-alpha.1

- Added the Blender Extensions package, viewport sidebar registration, translation catalog and build checks.
- Added explicit-unit STL import, non-destructive scaling, planar splitting with a viewport preview and optional kerf, and consecutive cuts.
- Added cylindrical and hexagonal connectors with independent lateral and axial clearance.
- Added topology and volume checks, per-piece STL export with collision-safe filenames, and package installation tests.
