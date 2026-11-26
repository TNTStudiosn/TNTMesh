# Installation and development

[Español de México](development.es.md)

Build the ZIP with Blender 4.5 LTS or a tested 5.x version. In Blender, open Preferences → Get Extensions → menu → Install from Disk and select the ZIP. In the 3D Viewport, press N and open TNTMesh.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.3.0-alpha.10.zip
```

The package entry point owns class registration. The sidebar uses Blender layouts and the translation catalog follows Blender's language preferences. Runtime operations run locally inside Blender.

## Geometry

The engine evaluates the source mesh and its transforms into a centered millimeter space. It intersects that mesh with two closed volumes using Blender's Exact solver. This closes seams with multiple contours while preserving solid walls. The source receives no mesh writes. Successful results are transformed back into scene units and tagged with persistent IDs only after both sides pass validation.

The connector search uses a bounded grid on the seam. It checks solid material around candidates on both sides with Boolean difference probes, applies the pin union and socket difference, and validates closure, connected shell counts and expected volume changes. Clearances are measured perpendicular to the polygon edges. A 64-sided cylinder approximates a circular pin. A hexagonal pin specifies diameter across corners. The search can miss valid positions between grid points.

Straight cuts take a world axis or an Euler rotation. Drawing a line sets the cutting plane through the corresponding screen rays. Bézier cuts approximate a cubic surface using a configurable number of strips. Rectangular, elliptical and custom contours extrude a finite cutter. In Contour mode, click points or Shift-drag, then press Enter to close the outline. The drawn outline is projected to the view plane and its points remain editable in the cut settings. A separate mesh can supply the cutter in assembly coordinates. Each volumetric cut uses the difference and intersection of that closed cutter and checks the sum of the resulting volumes.

Custom connectors take two closed mesh templates with matching object origins at the seam. Each template crosses its origin's XY plane. Positive Z is the pin's insertion direction and negative Z anchors the pin on the first piece or opens the socket cutter past the seam. Template translation is ignored. Rotation and scale are carried through. The socket template supplies the intended clearance. TNTMesh checks that it contains the protruding pin by volume. Custom templates currently require straight cuts with zero kerf.

**Manual Path** splits along an open stroke. Click points or hold Shift and drag, then press Enter to finish. TNTMesh extends both ends beyond the model. Adjust **Depth (mm)**, in-plane shift or smoothing in the cut settings. Edit or remove points from the list. Draw in Easy mode and add the current settings to a draft to reuse the stroke there.

Set **Snap** to use the view plane or the surface of the active mesh. **Vertex** and **Edge** take a nearby point on the face under the cursor and fall back to the surface when no feature is close enough. Outside the model, points use the view plane. These options also work when drawing straight and symmetric cuts or closed contours.

For **Straight** and **Symmetric Cuts**, click **Align to Face**, then click a face of the active mesh. The selected normal sets the plane orientation and the current offset still controls its distance from the model center.

Drag the cyan arrow to move the plane and update **Offset (mm)**. Press Esc during the drag to restore the previous offset. The handle follows the plane preview and can be hidden from **Cut settings**.

On a straight cut, **Suggest Connectors** uses the seam area and available material on both sides to propose pin count, diameter, insertion depth, shape and positions. The current diameter and insertion act as upper limits. The suggestion keeps the wall requirement, clearances and separate-pin setting. It uses the cut normal for insertion and picks the pin side with better socket depth. In **Cut settings**, edit the positions in millimeters along the cut plane or return to automatic placement. In a draft, the suggestion evaluates the selected cut's input, including cuts upstream of it. Generating pieces validates the current settings again.

Use **Connector Pattern** to lay out a line, circle or grid. Spacing is measured between adjacent connector centers. A pattern is centered on the current set of positions, or the input origin when the list is empty. In Easy mode, **Pick Connector Position** adds one connector at a point on the cut plane. These commands keep the previous positions if the new layout intersects a cavity, exceeds the available material or leaves too little wall.

The **Contour** pattern spaces positions by arc length along the largest outer seam and moves them into the solid by the specified edge setback. Adjust the pattern rotation to move the starting point around the contour if a position falls too close to a corner.

**Mirror X** and **Mirror Y** add reflected positions across the center of the cut frame. The copy and paste icons next to **Suggest Connectors** transfer the shape, dimensions, tolerances, pin side and positions between straight cuts. Paste checks the destination cut before applying the setup.

Choose **Magnets** on a straight or symmetric cut to make a pocket on each side for each magnet pair. **Stock Sizes** fills in a disc or block size. Save custom sizes to the scene library to edit and reuse them. The pocket depth is the magnet thickness plus the face inset and adhesive gap. Block magnets can be rotated within the seam. On straight cuts you can also use the connector patterns or pick a location in the viewport. **Export Magnet List** checks the current cut and writes a text file with the number of purchased magnets, their dimensions and installation distances.

Basic repair welds nearby vertices, dissolves short degenerate edges and optionally caps simple boundary loops on a copy. Enable **Correct face orientation** to make neighboring faces consistent and orient each closed shell according to its nesting depth. This preserves enclosed cavities and separate solids. The repair rejects crossing surfaces or ambiguous nesting. Review filled regions because caps add geometry.

Printer profiles are saved with the scene and can be moved between projects as schema-versioned JSON. The fit check uses world-space dimensions and subtracts the configured margin on each side of each axis. Alternative orientations permute the three axes. Split to Fit applies successive straight cuts and validates the remaining dimensions before publishing the resulting pieces.

**Calibrate Connectors** uses the same round and hexagonal profiles as straight cuts. The default kit sweeps 0.05 to 0.40 mm of lateral clearance per side in 0.05 mm increments. You can instead choose a sample count. Export the selected kit, print it with the intended material and settings, then turn the reusable test pin over to fit it into each socket. Select the best socket object and click **Save Clearance to Profile**. The sample retains its material label and clearance in the Blender file. Apply the profile's tolerances to transfer them to subsequent cuts.

**Surface Region** matches faces by material slot, saved face selection, a Boolean face attribute, vertex group or linear RGB color. Color and group matches require all samples or vertices of each face to qualify. Grow and shrink work in edge-adjacent rings. The cutter closes the selected surface along its boundary, offsets it into the model, checks for nonadjacent triangle intersections, and validates both Boolean outputs for topology and volume. Choose a smaller depth or patch on sharp folds. A draft reads the input's current matching attributes when it rebuilds.

Use **Boundary smoothing** in Cut Settings to relax the contour over the original surface before cutting. Zero preserves the original boundary. The overlay shows the face selection in cyan and the proposed smoothed contour in violet. Each moved vertex stays within 45% of its shortest original boundary edge and must project onto a triangle incident to that vertex. The cutter and both results pass the usual geometry checks.

**Mesh Diagnostics → Scan Mesh** checks evaluated geometry in millimeters. It reports open edges, non-manifold elements, inconsistent winding, zero-length edges, degenerate triangles, near-duplicate vertices and duplicate faces. The intersection option checks crossing triangles without shared vertices and tests coplanar triangles for a shared area. Edge contact alone is allowed. For disjoint closed shells, the scan compares enclosure depth with winding and identifies closed cavities, incorrectly oriented internal surfaces and inverted exteriors. Ambiguous ray results and intersecting shells are excluded from nesting classification. Click a finding to isolate its markers, or the zoom icon to frame them. Markers clear after edits, undo or reload. Up to 256 locations per category are drawn.

Set **Minimum wall (mm)** to flag thin walls in a closed solid. TNTMesh estimates thickness by casting rays inwards from triangle centers and measuring the distance to an opposing face. The results include the smallest flagged sample and markers at tested locations. Small thin spots between sample points can escape detection. Use zero to skip the check.

In Easy mode, choose **Surface Region → By Material Slot → Separate by Material** to split several material slots in a single operation. Pick the slot for the main body and set the depth for the extracted slots. Cuts proceed in slot order, so the first slot receives any interior volume shared by adjacent cuts. The main body retains the remaining solid volume. The operation publishes all results together after each cut passes the surface and volume checks. It retains the source mesh and sets the parts' preview colors from the materials.

Choose a **Cylindrical** or **Hexagonal** connector for a surface region. TNTMesh tries planar inner faces first. On a curved seam it looks for a common insertion axis, checks that the pin and socket fit across the footprint and verifies that both parts leave the selected wall thickness. The cut can use built-in pins or separate printable pins. **Connect to the main body** fits each material insert against the retained body after all material cuts have run. If the search finds no compatible placement, the operation keeps the source and previous results intact.

**Symmetric Cuts** reflects a straight plane around the chosen world axis and center. Move the first cut away from that center to create a middle piece and two outer pieces. Shift or rotate the second plane in its own axes from the cut details. Connector positions follow the adjusted plane and must fit both cuts before results are published. If you use custom templates, TNTMesh also reflects the shape of the pin and the socket. Draft mode exposes the three bodies as separate targets for subsequent cuts.

**Separate Base** looks for closed support loops below the search height in world Z. Set the model upright and try **Find Base Contacts** to review the suggested outlines. A height of zero searches the lowest 22% of the model. The detected loops drive local cutters at their own heights and slopes, so a stepped base can separate at different heights under different feet. Contact settings can shift an individual cut and set whether to add a pin and its diameter. Increase the search height only enough to include the base and inspect the resulting separation, especially if feet broaden between the contact and the search ceiling. Draft copies keep the detected contact overrides for their source mesh.

The **Assembly** panel groups generated pieces by their persistent project ID. It shows dimensions and provides measurement, selection, framing, project visibility and duplication controls. The explosion slider draws offset geometry in the viewport. It keeps model and export transforms at the assembled positions. Straight-cut pieces use their cut direction, and other pieces use their position relative to the project center. Dense pieces use bounding-box previews. **Check Assembly** tests for volume overlap in the current assembled pose.

**Check Insertion Path** checks a straight translation of the selected piece toward its assembled position. Choose a starting direction and distance. The check estimates contact intervals between triangles and verifies solid overlap at their boundaries and intermediate positions using temporary copies in millimeters. The result names the first blocking part found and gives a distance where the obstruction occurs. The scene geometry and transforms stay intact. The check uses the same numerical tolerances as the assembled-position overlap check. Paths with rotation are pending.

The 3MF writer uses Core 3MF with millimeter units and independent build items. It retains assembly positions and writes geometry without slicer profiles, supports, materials or toolpaths. [3MF Core Specification](https://github.com/3MFConsortium/spec_core)

The Windows round-trip check exported a 24 mm cube split into two halves as one 3MF, opened and re-exported it using OrcaSlicer and Bambu Studio, then inspected the resulting build items and model geometry. Both preserved two objects measuring 24 × 24 × 12 mm. [Bambu Studio CLI](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage)

## Material and cost

Open **Material & Cost** and choose the active mesh, selected meshes or current assembly. Enter density, price per kilogram and currency. Use **Use Printer Material** to copy density, price, technology and wall thickness from the selected printer profile. The report shows totals and the individual values for each piece, including any separate pins in the assembly. It uses the geometry at its evaluated scene scale and requires closed solids.

With FDM, the estimate multiplies surface area by wall thickness, caps that result at the model volume and applies the infill percentage to the remaining volume. With resin, the printed volume comes from the mesh. The optional cavity check compares closed shells with the enclosed volume of their exterior surfaces to estimate resin saved by cavities. Cavity savings can be unavailable for ambiguous or intersecting shells. The extra material percentage adds an allowance for consumables such as supports to the weight and cost. Check the final values in your slicer.

## Draft projects

The scene stores draft plans and references the original mesh object. Each cut consumes the source or one of the pieces from an earlier cut. The resulting piece IDs derive from the plan and cut identifiers, so moving or renaming an operation keeps its identity. An operation whose upstream input is missing or already consumed blocks the rebuild and identifies the affected cut.

Rebuild runs all enabled operations in memory before replacing the previous generated parts. It retains the original, and a failed rebuild keeps the prior output. Rebuilds currently recalculate all enabled cuts. The scene stores a draft schema version, and a newer unsupported schema returns an error.

## Verification

The core integration suite ran on Windows x64 and Linux x64 with Blender 4.5.17 LTS, 5.1.2, 5.2.4 LTS and 5.3.0, and on macOS arm64 with Blender 4.5.17 LTS. It covers STL round trips, connector dimensions, closure, volume, kerf, transformed meshes, repeated operations, scale copies, torus and hollow cross sections, and rejection of an oversized connector and damaged input. The source also passed on Windows with 4.2.23 LTS. The extension manifest still requires 4.5 because packaged and viewport coverage targets 4.5 and newer.

The graphical smoke test uses a separate Blender profile and runs `tests/viewport_smoke.py` with `TNTMESH_SMOKE_OUTPUT` set to a writable destination. It captures the viewport and checks the Spanish catalog and the undo stack. Set `TNTMESH_TEST_EVENTS=1` and launch with Blender's `--enable-event-simulate` to test viewport actions and export dialog cancellation. Set `TNTMESH_TEST_CONTOUR=1` to include the freehand drawing test, and `TNTMESH_TEST_PRINTER=1` to capture the printer panel and volume preview.

Set `TNTMESH_TEST_PHASE3=1` to capture the calibration dialog, region highlight, symmetric planes and assembly preview in the 1024 × 745 graphical test window.

Set `TNTMESH_TEST_BASE=1` to capture the detected supports on the two-height base fixture.

GitHub Actions validates the source and installed ZIP on Linux, and the installed ZIP on macOS arm64. Release tags must match the manifest version. Release automation adds a SHA-256 checksum and flags alpha, beta and release candidates as prereleases.

## Dense-mesh benchmarks

Run one operation per Blender process and record the CPU model, RAM, Blender version, operating system, wall time and process peak memory. The fixture is a closed quad torus with a major radius of 12 mm and a minor radius of 3 mm. It can generate each density from 10,000 to 10,000,000 faces listed in the specification.

```sh
blender --background --factory-startup --python-exit-code 1 --python tests/benchmark.py -- 100000 intersections
```

Use `inspect` for topology and volume, `diagnostics` for the basic mesh scan, `intersections` to include crossing and coplanar checks, or `split` for an exact straight cut without connectors. Results are written as JSON. Time starts after mesh construction. Peak memory includes Blender startup and fixture construction.

Reference runs used Blender 5.3.0 on Windows 11 build 26200 with a Ryzen 7 3700X, 16 logical CPUs and 31.9 GiB of RAM. Each row records one run.

| Faces | Operation | Seconds | Peak GiB |
| ---: | --- | ---: | ---: |
| 10,000 | Intersections | 1.18 | 0.20 |
| 100,000 | Intersections | 12.13 | 0.45 |
| 100,000 | Straight cut | 2.74 | 0.64 |
| 500,000 | Basic diagnosis | 8.57 | 0.99 |
| 1,000,000 | Topology and volume | 4.70 | 1.00 |
| 3,000,000 | Topology and volume | 16.53 | 2.69 |
| 5,000,000 | Topology and volume | 25.26 | 4.25 |
| 10,000,000 | Topology and volume | 56.49 | 8.34 |

These results cover the stated operations on this fixture. Cutting and full intersection diagnostics at the highest densities still need verification.

## Native extension repository

In Blender Preferences, open Get Extensions → Repositories → Add Remote Repository. Add one index for the channel you want. The [experimental index](https://tntstudiosn.github.io/TNTMesh/experimental/index.json) serves prereleases. The [stable index](https://tntstudiosn.github.io/TNTMesh/stable/index.json) populates after the first stable release.

Use Blender's Refresh Remote and Update options or its optional startup check. Blender controls online access, compatibility and installation. Packages come directly from GitHub Releases. The Pages build verifies the release SHA-256 and uses Blender's official index generator. If installing from the remote channel after testing a ZIP, disable the local copy to avoid enabling two TNTMesh instances.
