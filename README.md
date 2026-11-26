# TNTMesh

TNTMesh is a free, open-source Blender extension by TNTStudios for preparing models for 3D printing.

[Español de México](README.es.md) · [Installation and development](docs/development.md) · [Roadmap](ROADMAP.md) · [License](LICENSE)

TNTMesh 0.1 is an early preview. It imports STL files, creates scaled copies, splits closed meshes with a straight plane, adds a cylindrical or hexagonal pin and socket, and exports one STL per piece.

1. Install the ZIP from [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) or build it using Blender's extension tools.
2. Open the 3D Viewport sidebar with **N**, select **TNTMesh** and import an STL or select a mesh.
3. Set the cut axis and offset, choose a connector, and click **Split Model**. TNTMesh keeps the source mesh and hides it by default.
4. Use **Check Mesh** for the topology and volume checks, then **Export STL Pieces** to write the selected results to an existing folder.

STL is unitless. Import defaults to millimeters, with centimeters and inches available in the file browser. Export uses millimeters and preserves assembly positions. Existing Blender models use the scene's unit scale, with 1 Blender unit treated as 1 mm when units are disabled.

The current validation checks closure, winding, degenerate faces and enclosed volume. Check the final orientation, supports and print settings in your slicer. Print a sample to verify the fit for your material and printer.
