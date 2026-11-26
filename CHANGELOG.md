# Changelog

## Unreleased

- Added face alignment for straight and symmetric cut planes.

## 0.3.0-alpha.6

- Added an optional thin-wall diagnosis for closed solids with a minimum thickness in millimeters.
- Added optional face-orientation repair for closed solids and nested cavities.
- Added Blender 5.3.0 to the source and ZIP verification matrix.
- Added open manual paths with point editing, smoothing and adjustable cut depth.
- Added surface projection and vertex or edge snapping while drawing cuts.

## 0.3.0-alpha.5

- Added closed-cavity and shell-orientation classification for disjoint closed surfaces.
- Added positive-area coplanar overlap checks alongside crossing-surface checks.
- Improved straight insertion checks with swept triangle contacts to find obstructions between fixed positions.
- Added independent rotation for the second symmetric cut, including the live preview and saved drafts.
- Added reflection of custom pin and socket templates for symmetric cuts.
- Added a checksum-verified download fallback for macOS CI.

## 0.3.0-alpha.4

- Added one-operation separation of multiple material slots into closed pieces with a retained body.
- Added a sampled straight-line insertion check that reports the first blocking part and distance.
- Added mesh diagnostics with grouped viewport markers and a focus action for each finding.
- Added optional surface-projected smoothing for region cut boundaries.
- Added automatic pin and socket placement on planar region interfaces, including material-slot batches and loose pins.

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
