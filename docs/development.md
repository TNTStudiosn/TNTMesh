# Installation and development

Build the ZIP with Blender 4.5 LTS or a tested 5.x version. In Blender, open Preferences → Get Extensions → menu → Install from Disk and select the ZIP. In the 3D Viewport, press N and open TNTMesh.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.1.0.zip
```

The package entry point owns class registration, the UI uses Blender-native layouts, and localization uses Blender's translation catalog. Runtime operations run locally inside Blender.
