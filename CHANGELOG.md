# Changelog

## Unreleased

- Added one-operation separation of multiple material slots into closed pieces with a retained body.

## 0.3.0-alpha.3

- Added base-contact detection and solid base separation for models with one or more supports at distinct heights.
- Added contact previews and per-contact height, connector and pin diameter overrides.

## 0.3.0-alpha.2

- Added connector calibration kits with an engraved clearance sweep and a reusable pin. A selected socket can set a printer profile's per-side clearance.
- Added solid surface-region extraction by material slot, color, vertex group, face mask or face selection in Easy and Draft.
- Added symmetric two-plane cuts with an adjustable center and mirrored cylindrical or hexagonal connectors.
- Added a project piece panel, exploded preview, and static volume-overlap checks in the assembled position.

## 0.3.0-alpha.1

- Added eight editable FDM and resin printer profiles, JSON import and export, and tolerance transfer.
- Added printable volume previews, margin-aware fit checks, alternate axis suggestions and geometry splitting by available volume.
- Added 3MF export for one model per file or a multi-object package.

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
