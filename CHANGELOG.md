# Changelog

## Unreleased

## 0.3.0-alpha.17

- Added assembly guides with numbered assembled and exploded PNG views, cut relationships, loose connectors, recorded magnet sizes and a suggested build order in HTML and Markdown.

## 0.3.0-alpha.15

- Added editable starting tolerances for common filament and resin materials in printer profiles.
- Added PLY and ZIP export, loose connector filters, prefixes, optional numbering, and output subfolders.
- Added build plate placement with print rotation, spacing and printer profile limits for grouped 3MF.

## 0.3.0-alpha.14

- Added tapered cylindrical, square, rectangular, triangular, octagonal, oval, D-shaped, star, cross, and tongue-and-groove profiles.
- Added profile rotation, independent dimensions, true side offsets, and footprint-based checks for the new profiles.
- Extended cuts, drafts, connector layouts, and calibration kits to use the same profile geometry.
- Account for mesh-coordinate roundoff when measuring contact on assembled seams.

## 0.3.0-alpha.12

- Added sampled insertion checks for rotation with optional translation and a configurable pivot.
- Added sliding dovetails for straight and symmetric cuts, with measured wall and clearance checks and automatic or editable rail placement.
- Added dovetail settings to drafts and clipboard transfer, an exit arrow in the cut preview, and slide guidance for assembly checks.

## 0.3.0-alpha.11

- Added a viewport thickness map and thin-wall markers for areas around sockets and other printed features.
- Added resin trap analysis with closed-cavity counts, orientation-dependent suction estimates and viewport markers.

## 0.3.0-alpha.10

- Added resin hollowing on a copy, with adjustable wall thickness, voxel size and reinforced regions.
- Added manual and suggested circular drains, custom cutters and optional printable plugs.
- Verify that each drain connects a cavity to the exterior. Successive drains retain earlier openings across save and reopen.

## 0.3.0-alpha.9

- Added per-piece and assembly material, weight and cost estimates for FDM and resin.
- Added paired disc and block magnet pockets for straight and symmetric cuts, editable sizes and component lists.

## 0.3.0-alpha.8

- Removed near-coincident vertices around zero-area faces produced by surface-region extraction.
- Added validated connector suggestions with editable dimensions, positions and pin side for straight cuts and drafts.
- Added validated line, circle, grid and contour connector patterns and single-position placement in the viewport.
- Added mirrored layouts and validated copy and paste for connector setups.

## 0.3.0-alpha.7

- Added face alignment for straight and symmetric cut planes.
- Added a viewport handle to drag straight and symmetric cut planes along their normal.
- Reduced the spatial checks needed to find coplanar overlaps and added reproducible dense-mesh benchmarks.
- Extended region connector placement to curved seams that have room for a shared insertion axis.

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
