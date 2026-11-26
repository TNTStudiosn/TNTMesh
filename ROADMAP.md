# Roadmap

| Phase | Status | Scope |
| --- | --- | --- |
| 0 · Infrastructure | Implemented | Extension package, sidebar, translation, Blender tests and CI |
| 1 · Core workflow | Experimental | STL, scale, straight cuts, cylindrical and hexagonal connectors, validation and per-part STL |
| 2 · Planning | Experimental | Draft, Bézier profiles, contour and primitive extraction, cutter objects, multiple and loose connectors, mesh connector templates, OBJ/FBX export, basic repair and native updates |
| 3 · Print preparation | In development | Printer profiles, volume fit, 3MF, tolerance kits, surface-region extraction, material-slot batch separation, symmetric cuts, base contact separation, exploded preview and sampled insertion checks. Region-boundary smoothing, automatic region connectors and continuous collision detection are pending |
| 4 · Professional tools | Planned | Magnets, dovetails, snap-fits, articulations, glue features, hollowing, drains, thickness, costs and assembly guides |
| 5 · Automation | Planned | Smart Split, seam suggestions, orientation, bed layout, segmentation and stress testing |

Straight cuts support axis selection, numeric offset, free rotation and drawing a line in the viewport. Gizmos, face alignment, snapping, the first-run assistant and manual language selection are pending.

Freehand drawing currently produces closed extraction contours. Open surface paths, vertex and edge snapping, and selective invalidation of draft operations are pending. Connector placement currently supports planar seams. General mesh self-intersection detection, assembly simulation and high-density profiling require further validation.

Surface Region extracts one chosen region at a time. Face masks and vertex groups can come from Blender painting tools. Separate by Material processes multiple slots in one operation. Symmetric Cuts reflects the first plane and offers a separate normal offset for the second plane. Custom template reflection and independent rotation of the second plane are pending.

Base contact detection searches for closed loops where figures rise from upward-facing base surfaces. Open or ambiguous contact contours, organic transitions without a distinct rim, and merging footprints at very different heights need additional work.
