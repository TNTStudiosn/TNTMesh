# Installation and development

Build the ZIP with Blender 4.5 LTS or a tested 5.x version. In Blender, open Preferences → Get Extensions → menu → Install from Disk and select the ZIP. In the 3D Viewport, press N and open TNTMesh.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.1.0-alpha.1.zip
```

The package entry point owns class registration. The sidebar uses Blender layouts and the translation catalog follows Blender's language preferences. Runtime operations run locally inside Blender.

## Geometry

The engine evaluates the source mesh and its transforms into a centered millimeter space. It intersects that mesh with two closed volumes using Blender's Exact solver. This closes seams with multiple contours while preserving solid walls. The source receives no mesh writes. Successful results are transformed back into scene units and tagged with persistent IDs only after both sides pass validation.

The connector search uses a bounded grid on the seam. It checks solid material around candidates on both sides with Boolean difference probes, applies the pin union and socket difference, and validates closure, connected shell counts and expected volume changes. Clearances are measured perpendicular to the polygon edges. A 64-sided cylinder approximates a circular pin. A hexagonal pin specifies diameter across corners. The search can miss valid positions between grid points.

## Verification

The core integration suite ran on Windows x64 with Blender 4.5.17 LTS, 5.1.2 and 5.2.4 LTS. It covers the STL round trip, connector dimensions, closure, volume, kerf, transformed meshes, repeated operations, scale copies, torus and hollow cross sections, and rejection of an oversized connector and damaged input. The source also passed on 4.2.23 LTS. The extension manifest still requires 4.5 because packaged and viewport coverage targets 4.5 and newer.

The graphical smoke test uses a separate Blender profile and runs `tests/viewport_smoke.py` with `TNTMESH_SMOKE_OUTPUT` set to a writable destination. It captures the viewport and checks the Spanish catalog and the undo stack. Use Blender's regular interface to verify keyboard navigation, different UI scales and native file dialogs.

GitHub Actions validates the source and the installed ZIP on Linux. Release tags must match the manifest version. Release automation adds a SHA-256 checksum and flags alpha, beta and release candidates as prereleases.
