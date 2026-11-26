# Installation and development

[Español de México](development.es.md)

Build the ZIP with Blender 4.5 LTS or a tested 5.x version. In Blender, open Preferences → Get Extensions → menu → Install from Disk and select the ZIP. In the 3D Viewport, press N and open TNTMesh.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.2.0-alpha.1.zip
```

The package entry point owns class registration. The sidebar uses Blender layouts and the translation catalog follows Blender's language preferences. Runtime operations run locally inside Blender.

## Geometry

The engine evaluates the source mesh and its transforms into a centered millimeter space. It intersects that mesh with two closed volumes using Blender's Exact solver. This closes seams with multiple contours while preserving solid walls. The source receives no mesh writes. Successful results are transformed back into scene units and tagged with persistent IDs only after both sides pass validation.

The connector search uses a bounded grid on the seam. It checks solid material around candidates on both sides with Boolean difference probes, applies the pin union and socket difference, and validates closure, connected shell counts and expected volume changes. Clearances are measured perpendicular to the polygon edges. A 64-sided cylinder approximates a circular pin. A hexagonal pin specifies diameter across corners. The search can miss valid positions between grid points.

Straight cuts take a world axis or an Euler rotation. Drawing a line sets the cutting plane through the corresponding screen rays. Bézier cuts approximate a cubic surface using a configurable number of strips. Rectangular and elliptical profiles extrude a finite cutter. A separate mesh can supply the cutter in assembly coordinates. Each volumetric cut uses the difference and intersection of that closed cutter and checks the sum of the resulting volumes. Fitted connectors currently require a straight cut.

Basic repair welds nearby vertices, dissolves short degenerate edges and optionally caps simple boundary loops on a copy. The repaired copy must pass the mesh checks before it appears. Review filled regions because caps add geometry.

## Draft projects

The scene stores draft plans and references the original mesh object. Each cut consumes the source or one of the pieces from an earlier cut. The resulting piece IDs derive from the plan and cut identifiers, so moving or renaming an operation keeps its identity. An operation whose upstream input is missing or already consumed blocks the rebuild and identifies the affected cut.

Rebuild runs all enabled operations in memory before replacing the previous generated parts. It retains the original, and a failed rebuild keeps the prior output. Rebuilds currently recalculate all enabled cuts. The scene stores a draft schema version, and a newer unsupported schema returns an error.

## Verification

The core integration suite ran on Windows x64 with Blender 4.5.17 LTS, 5.1.2 and 5.2.4 LTS. It covers the STL round trip, connector dimensions, closure, volume, kerf, transformed meshes, repeated operations, scale copies, torus and hollow cross sections, and rejection of an oversized connector and damaged input. The source also passed on 4.2.23 LTS. The extension manifest still requires 4.5 because packaged and viewport coverage targets 4.5 and newer.

The graphical smoke test uses a separate Blender profile and runs `tests/viewport_smoke.py` with `TNTMESH_SMOKE_OUTPUT` set to a writable destination. It captures the viewport and checks the Spanish catalog and the undo stack. Set `TNTMESH_TEST_EVENTS=1` and launch with Blender's `--enable-event-simulate` to test clicks and Escape in the line tool. Use Blender's regular interface to verify keyboard navigation, different UI scales and native file dialogs.

GitHub Actions validates the source and the installed ZIP on Linux. Release tags must match the manifest version. Release automation adds a SHA-256 checksum and flags alpha, beta and release candidates as prereleases.

## Native extension repository

In Blender Preferences, open Get Extensions → Repositories → Add Remote Repository. Add one index for the channel you want. The [experimental index](https://tntstudiosn.github.io/TNTMesh/experimental/index.json) serves prereleases. The [stable index](https://tntstudiosn.github.io/TNTMesh/stable/index.json) populates after the first stable release.

Use Blender's Refresh Remote and Update options or its optional startup check. Blender controls online access, compatibility and installation. Packages come directly from GitHub Releases. The Pages build verifies the release SHA-256 and uses Blender's official index generator. If installing from the remote channel after testing a ZIP, disable the local copy to avoid enabling two TNTMesh instances.
