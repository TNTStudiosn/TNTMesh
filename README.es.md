# TNTMesh

TNTMesh es una extensión gratuita y de código abierto de TNTStudios para preparar modelos para impresión 3D en Blender.

[English](README.md) · [Instalación y desarrollo](docs/development.md) · [Hoja de ruta](ROADMAP.md) · [Licencia](LICENSE)

TNTMesh 0.1 es una versión experimental. Importa STL, crea copias a escala, divide mallas cerradas con un plano, añade un pin cilíndrico o hexagonal con su cavidad y exporta un STL por pieza.

1. Instala el ZIP desde [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) o constrúyelo con las herramientas de extensiones de Blender.
2. Pulsa **N** en la Vista 3D, abre **TNTMesh** e importa un STL o selecciona una malla.
3. Define el eje y el desplazamiento del plano, elige un conector y pulsa **Dividir modelo**. TNTMesh conserva la malla original y la oculta de forma predeterminada.
4. Usa **Revisar malla** para comprobar la topología y el volumen, y luego **Exportar piezas STL** para guardar las piezas seleccionadas en una carpeta existente.

STL es un formato sin unidades. La importación usa milímetros por defecto y permite elegir centímetros o pulgadas. La exportación usa milímetros y conserva la posición de ensamblaje. Para los objetos existentes se usa la escala de la escena. Si la escena tiene las unidades desactivadas, 1 BU equivale a 1 mm.

La validación comprueba el cierre, la orientación de las caras, las caras degeneradas y el volumen interior. Revisa la orientación, los soportes y la preparación final en tu slicer. Imprime una muestra para comprobar el ajuste con tu material y equipo.
