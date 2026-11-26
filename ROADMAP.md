# Roadmap

| Phase | Status | Scope |
| --- | --- | --- |
| 0 · Infrastructure | Implemented | Extension package, sidebar, translation, Blender tests and CI |
| 1 · Core workflow | Experimental | STL, scale, straight cuts, cylindrical and hexagonal connectors, validation and per-part STL |
| 2 · Planning | In development | Draft, Bézier profiles, rectangular and elliptical extraction, cutter objects, multiple and loose connectors, OBJ/FBX export, basic repair and native updates |
| 3 · Print preparation | Planned | Printer profiles, fit checks, base and color separation, symmetry, regions, placement, calibrations, exploded view, 3MF |
| 4 · Professional tools | Planned | Magnets, dovetails, snap-fits, articulations, glue features, hollowing, drains, thickness, costs and assembly guides |
| 5 · Automation | Planned | Smart Split, seam suggestions, orientation, bed layout, segmentation and stress testing |

Straight cuts support axis selection, numeric offset, free rotation and drawing a line in the viewport. Gizmos, face alignment, snapping, the first-run assistant and manual language selection are pending.

Phase 2 still needs freehand contours, editable custom polygons, custom connector meshes and cache invalidation for dependent cuts. Connector placement currently supports planar seams. General self-intersection detection, assembly simulation and high-density profiling require further validation.
