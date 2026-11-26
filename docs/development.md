# Installation and development

[Español de México](development.es.md)

Build the ZIP with Blender 4.5 LTS or a tested 5.x version. In Blender, open Preferences → Get Extensions → menu → Install from Disk and select the ZIP. In the 3D Viewport, press N and open TNTMesh.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.3.0-alpha.4.zip
```

The package entry point owns class registration. The sidebar uses Blender layouts and the translation catalog follows Blender's language preferences. Runtime operations run locally inside Blender.

## Geometry

The engine evaluates the source mesh and its transforms into a centered millimeter space. It intersects that mesh with two closed volumes using Blender's Exact solver. This closes seams with multiple contours while preserving solid walls. The source receives no mesh writes. Successful results are transformed back into scene units and tagged with persistent IDs only after both sides pass validation.

The connector search uses a bounded grid on the seam. It checks solid material around candidates on both sides with Boolean difference probes, applies the pin union and socket difference, and validates closure, connected shell counts and expected volume changes. Clearances are measured perpendicular to the polygon edges. A 64-sided cylinder approximates a circular pin. A hexagonal pin specifies diameter across corners. The search can miss valid positions between grid points.

Straight cuts take a world axis or an Euler rotation. Drawing a line sets the cutting plane through the corresponding screen rays. Bézier cuts approximate a cubic surface using a configurable number of strips. Rectangular, elliptical and custom contours extrude a finite cutter. In Contour mode, click points or Shift-drag, then press Enter to close the outline. The drawn outline is projected to the view plane and its points remain editable in the cut settings. A separate mesh can supply the cutter in assembly coordinates. Each volumetric cut uses the difference and intersection of that closed cutter and checks the sum of the resulting volumes.

Custom connectors take two closed mesh templates with matching object origins at the seam. Each template crosses its origin's XY plane. Positive Z is the pin's insertion direction and negative Z anchors the pin on the first piece or opens the socket cutter past the seam. Template translation is ignored. Rotation and scale are carried through. The socket template supplies the intended clearance. TNTMesh checks that it contains the protruding pin by volume. Custom templates currently require straight cuts with zero kerf.

Basic repair welds nearby vertices, dissolves short degenerate edges and optionally caps simple boundary loops on a copy. The repaired copy must pass the mesh checks before it appears. Review filled regions because caps add geometry.

Printer profiles are saved with the scene and can be moved between projects as schema-versioned JSON. The fit check uses world-space dimensions and subtracts the configured margin on each side of each axis. Alternative orientations permute the three axes. Split to Fit applies successive straight cuts and validates the remaining dimensions before publishing the resulting pieces.

**Calibrate Connectors** uses the same round and hexagonal profiles as straight cuts. The default kit sweeps 0.05 to 0.40 mm of lateral clearance per side in 0.05 mm increments. You can instead choose a sample count. Export the selected kit, print it with the intended material and settings, then turn the reusable test pin over to fit it into each socket. Select the best socket object and click **Save Clearance to Profile**. The sample retains its material label and clearance in the Blender file. Apply the profile's tolerances to transfer them to subsequent cuts.

**Surface Region** matches faces by material slot, saved face selection, a Boolean face attribute, vertex group or linear RGB color. Color and group matches require all samples or vertices of each face to qualify. Grow and shrink work in edge-adjacent rings. The cutter closes the selected surface along its boundary, offsets it into the model, checks for nonadjacent triangle intersections, and validates both Boolean outputs for topology and volume. Choose a smaller depth or patch on sharp folds. A draft reads the input's current matching attributes when it rebuilds.

Use **Boundary smoothing** in Cut Settings to relax the contour over the original surface before cutting. Zero preserves the original boundary. The overlay shows the face selection in cyan and the proposed smoothed contour in violet. Each moved vertex stays within 45% of its shortest original boundary edge and must project onto a triangle incident to that vertex. The cutter and both results pass the usual geometry checks.

**Mesh Diagnostics → Scan Mesh** checks evaluated geometry in millimeters. It reports open edges, non-manifold elements, inconsistent winding, zero-length edges, degenerate triangles, near-duplicate vertices and duplicate faces. The intersection option checks crossing triangles without shared vertices and tests coplanar triangles for a shared area. Edge contact alone is allowed. For disjoint closed shells, the scan compares enclosure depth with winding and identifies closed cavities, incorrectly oriented internal surfaces and inverted exteriors. Ambiguous ray results and intersecting shells are excluded from nesting classification. Click a finding to isolate its markers, or the zoom icon to frame them. Markers clear after edits, undo or reload. Up to 256 locations per category are drawn. Wall thickness and continuous collision checks require separate analysis.

In Easy mode, choose **Surface Region → By Material Slot → Separate by Material** to split several material slots in a single operation. Pick the slot for the main body and set the depth for the extracted slots. Cuts proceed in slot order, so the first slot receives any interior volume shared by adjacent cuts. The main body retains the remaining solid volume. The operation publishes all results together after each cut passes the surface and volume checks. It retains the source mesh and sets the parts' preview colors from the materials.

Choose a **Cylindrical** or **Hexagonal** connector for a surface region. TNTMesh ranks planar inner faces by available area and checks the footprint, wall and insertion depth on both sides before carving the matching features. The cut can use built-in pins or separate printable pins. **Connect to the main body** fits each material insert against the retained body after all material cuts have run. If any interface has insufficient space, the operation leaves the source and previous results intact. The current search considers up to twelve candidate planes. Highly curved seams may have no suitable planar face.

**Symmetric Cuts** reflects a straight plane around the chosen world axis and center. Move the first cut away from that center to create a middle piece and two outer pieces. The secondary offset can move the reflected plane along its normal. Round and hexagonal connector positions are reflected and must fit both cuts before results are published. Draft mode exposes the three bodies as separate targets for subsequent cuts.

**Separate Base** looks for closed support loops below the search height in world Z. Set the model upright and try **Find Base Contacts** to review the suggested outlines. A height of zero searches the lowest 22% of the model. The detected loops drive local cutters at their own heights and slopes, so a stepped base can separate at different heights under different feet. Contact settings can shift an individual cut and set whether to add a pin and its diameter. Increase the search height only enough to include the base and inspect the resulting separation, especially if feet broaden between the contact and the search ceiling. Draft copies keep the detected contact overrides for their source mesh.

The **Assembly** panel groups generated pieces by their persistent project ID. It shows dimensions and provides measurement, selection, framing, project visibility and duplication controls. The explosion slider draws offset geometry in the viewport. It keeps model and export transforms at the assembled positions. Straight-cut pieces use their cut direction, and other pieces use their position relative to the project center. Dense pieces use bounding-box previews. **Check Assembly** tests for volume overlap in the current assembled pose.

**Check Insertion Path** samples a straight translation of the selected piece toward its assembled position. Choose a starting direction, distance and number of intervals. The check includes both endpoints, tests against other parts in the project and reports the first obstruction it finds. It evaluates temporary copies in millimeters and leaves the scene geometry and transforms intact. A small obstacle can fall between samples. Continuous collision detection and paths with rotation remain pending.

The 3MF writer uses Core 3MF with millimeter units and independent build items. It retains assembly positions and writes geometry without slicer profiles, supports, materials or toolpaths. [3MF Core Specification](https://github.com/3MFConsortium/spec_core)

The Windows round-trip check exported a 24 mm cube split into two halves as one 3MF, opened and re-exported it using OrcaSlicer and Bambu Studio, then inspected the resulting build items and model geometry. Both preserved two objects measuring 24 × 24 × 12 mm. [Bambu Studio CLI](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage)

## Draft projects

The scene stores draft plans and references the original mesh object. Each cut consumes the source or one of the pieces from an earlier cut. The resulting piece IDs derive from the plan and cut identifiers, so moving or renaming an operation keeps its identity. An operation whose upstream input is missing or already consumed blocks the rebuild and identifies the affected cut.

Rebuild runs all enabled operations in memory before replacing the previous generated parts. It retains the original, and a failed rebuild keeps the prior output. Rebuilds currently recalculate all enabled cuts. The scene stores a draft schema version, and a newer unsupported schema returns an error.

## Verification

The core integration suite ran on Windows x64 and Linux x64 with Blender 4.5.17 LTS, 5.1.2 and 5.2.4 LTS, and on macOS arm64 with Blender 4.5.17 LTS. It covers STL round trips, connector dimensions, closure, volume, kerf, transformed meshes, repeated operations, scale copies, torus and hollow cross sections, and rejection of an oversized connector and damaged input. The source also passed on Windows with 4.2.23 LTS. The extension manifest still requires 4.5 because packaged and viewport coverage targets 4.5 and newer.

The graphical smoke test uses a separate Blender profile and runs `tests/viewport_smoke.py` with `TNTMESH_SMOKE_OUTPUT` set to a writable destination. It captures the viewport and checks the Spanish catalog and the undo stack. Set `TNTMESH_TEST_EVENTS=1` and launch with Blender's `--enable-event-simulate` to test viewport actions and export dialog cancellation. Set `TNTMESH_TEST_CONTOUR=1` to include the freehand drawing test, and `TNTMESH_TEST_PRINTER=1` to capture the printer panel and volume preview.

Set `TNTMESH_TEST_PHASE3=1` to capture the calibration dialog, region highlight, symmetric planes and assembly preview in the 1024 × 745 graphical test window.

Set `TNTMESH_TEST_BASE=1` to capture the detected supports on the two-height base fixture.

GitHub Actions validates the source and installed ZIP on Linux, and the installed ZIP on macOS arm64. Release tags must match the manifest version. Release automation adds a SHA-256 checksum and flags alpha, beta and release candidates as prereleases.

## Native extension repository

In Blender Preferences, open Get Extensions → Repositories → Add Remote Repository. Add one index for the channel you want. The [experimental index](https://tntstudiosn.github.io/TNTMesh/experimental/index.json) serves prereleases. The [stable index](https://tntstudiosn.github.io/TNTMesh/stable/index.json) populates after the first stable release.

Use Blender's Refresh Remote and Update options or its optional startup check. Blender controls online access, compatibility and installation. Packages come directly from GitHub Releases. The Pages build verifies the release SHA-256 and uses Blender's official index generator. If installing from the remote channel after testing a ZIP, disable the local copy to avoid enabling two TNTMesh instances.
