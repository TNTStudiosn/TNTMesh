# Roadmap

| Phase | Status | Scope |
| --- | --- | --- |
| 0 · Infrastructure | Implemented | Extension package, sidebar, translation, Blender tests and CI |
| 1 · Core workflow | Experimental | STL, scale, straight cuts, cylindrical and hexagonal connectors, validation and per-part STL |
| 2 · Planning | Experimental | Draft, Bézier profiles, contour and primitive extraction, cutter objects, multiple and loose connectors, mesh connector templates, OBJ/FBX export, basic repair and native updates |
| 3 · Print preparation | In development | Printer profiles, volume preview and fit, automatic straight splits by usable volume, and basic 3MF export. Base and color separation, symmetry, region painting, calibration and exploded view are pending |
| 4 · Professional tools | Planned | Magnets, dovetails, snap-fits, articulations, glue features, hollowing, drains, thickness, costs and assembly guides |
| 5 · Automation | Planned | Smart Split, seam suggestions, orientation, bed layout, segmentation and stress testing |

Straight cuts support axis selection, numeric offset, free rotation and drawing a line in the viewport. Gizmos, face alignment, snapping, the first-run assistant and manual language selection are pending.

Freehand drawing currently produces closed extraction contours. Open surface paths, vertex and edge snapping, and selective invalidation of draft operations are pending. Connector placement currently supports planar seams. General mesh self-intersection detection, assembly simulation and high-density profiling require further validation.
