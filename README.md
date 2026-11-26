# TNTMesh

TNTMesh is a free, open-source Blender extension by TNTStudios for preparing models for 3D printing.

[Español de México](README.es.md) · [Installation and development](docs/development.md) · [Roadmap](ROADMAP.md) · [License](LICENSE)

TNTMesh is an early preview. It imports STL files, creates scaled or repaired copies, splits closed meshes, adds cylindrical or hexagonal connectors, and exports individual pieces.

1. Install the ZIP from [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) or build it using Blender's extension tools.
2. Open the 3D Viewport sidebar with **N**, select **TNTMesh** and import an STL or select a mesh.
3. Set the cut type and position, then click **Split Model**. For a straight cut, choose the axis, enter an exact rotation, or draw a line in the viewport. TNTMesh keeps the source mesh and hides it by default.
4. Use **Check Mesh** for topology and volume checks, then **Export Pieces** to write STL, OBJ, FBX or 3MF files to an existing folder.

For a straight cut, open **Cut settings** to change clearances, connector count or generate separate pins. **Draft** stores a chain of cuts in the `.blend` file. Add the cuts, select each target piece, then click **Build Draft**.

STL and OBJ store millimeter coordinates and preserve assembly positions. FBX writes explicit physical units. STL import defaults to millimeters, with centimeters and inches available in the file browser. Existing Blender models use the scene's unit scale, with 1 Blender unit treated as 1 mm when units are disabled.

Use the **Printer** panel to choose a profile, set safety margins and preview the usable volume. **Split to Fit** divides models that exceed the selected profile in their current orientation. [Printer presets and specifications](docs/printer-profiles.md)

**Calibrate Connectors** makes a reusable pin and engraved socket samples. After printing, select the socket that fits and save its clearance to the printer profile. **Surface Region** extracts a solid layer from faces matched by material, color or selection. **Symmetric Cuts** reflects a straight cut and its connector positions. Open **Assembly** to inspect project pieces and preview separation while retaining their export positions.

The current validation checks closure, winding, degenerate faces and enclosed volume. Check the final orientation, supports and print settings in your slicer. Print a sample to verify the fit for your material and printer.

For a resin print, open **Resin Preparation**, set the wall thickness and voxel size, then choose **Create Hollow Copy**. Use a separate closed mesh overlapping the model wall to keep a region solid or reinforce a joint. Choose **Place Drain** and click the exterior, or place a suggested circular drain along the configured print direction. A circular drain can produce a separate plug. For an irregular hole, position a closed cutter across the wall and select **Custom mesh** before placing the drain. **Mesh Diagnostics** can show any cavities that remain closed.
