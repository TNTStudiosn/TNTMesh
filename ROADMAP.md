# Roadmap

| Phase | Status | Scope |
| --- | --- | --- |
| 0 · Infrastructure | Implemented | Extension package, sidebar, translation, Blender tests and CI |
| 1 · Core workflow | Experimental | STL, scale, straight cuts, cylindrical and hexagonal connectors, validation and per-part STL |
| 2 · Planning | Experimental | Draft, Bézier profiles, contour and primitive extraction, cutter objects, multiple and loose connectors, mesh connector templates, OBJ/FBX export, basic repair and native updates |
| 3 · Print preparation | In development | Printer profiles, volume fit, 3MF, tolerance kits, surface-region extraction and smoothing, automatic connectors on planar and shallow curved region interfaces, material-slot batch separation, symmetric cuts, base separation, mesh diagnostics, exploded preview and swept straight insertion checks. Straight cuts suggest connector dimensions and placements. Insertion with rotation and suggestions for other cut types still need work |
| 4 · Professional tools | Planned | Magnets, dovetails, snap-fits, articulations, glue features, hollowing, drains, a wall thickness heatmap, costs and assembly guides |
| 5 · Automation | Planned | Smart Split, seam suggestions, orientation, bed layout, segmentation and stress testing |

Straight cuts support axis selection, numeric offset, free rotation, face alignment, drawing a line and moving the plane with a viewport handle. The first-run assistant and manual language selection are pending.

Freehand drawing produces closed extraction contours and open paths. The drawing tools support view-plane placement, surface projection and vertex or edge snapping. Selective invalidation of draft operations is pending. Mesh diagnostics check crossings between triangles without shared vertices, positive-area coplanar overlaps, nesting of disjoint closed shells and wall thickness sampled from triangle centers. The development guides record measured dense-mesh results by operation.

Surface Region extracts one chosen region at a time. Face masks and vertex groups can come from Blender painting tools. Separate by Material processes multiple slots in one operation. Symmetric Cuts reflects the first plane, including custom connector templates, and offers independent shift and rotation for the second plane.

Base contact detection searches for closed loops where figures rise from upward-facing base surfaces. Open or ambiguous contact contours, organic transitions without a distinct rim, and merging footprints at very different heights need additional work.
