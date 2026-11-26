# TNTMesh development

- Preserve the source model and its data. Publish generated objects only after validation.
- Keep Blender API calls on the main thread. Prefer evaluated geometry and release temporary data on every exit path.
- Express manufacturing dimensions in millimeters and document conversions at Blender and file boundaries.
- Add Blender integration coverage for geometry changes, including difficult cases and rollback.
- Use Blender's extension CLI to build and validate packages. Test both the source and packaged extension.
- Keep English and Mexican Spanish strings, end-user documentation and changelog in sync.
- Ship without telemetry, accounts or runtime package installs. Preserve GPL-3.0-or-later compatibility.
