# TNTMesh

TNTMesh es una extensión gratuita y de código abierto de TNTStudios para preparar modelos para impresión 3D en Blender.

[English](README.md) · [Instalación y desarrollo](docs/development.es.md) · [Hoja de ruta](ROADMAP.md) · [Licencia](LICENSE)

TNTMesh está en etapa experimental. Importa STL, crea copias a escala o reparadas, divide mallas cerradas, añade conectores cilíndricos o hexagonales y exporta piezas individuales.

1. Instala el ZIP desde [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) o constrúyelo con las herramientas de extensiones de Blender.
2. Pulsa **N** en la Vista 3D, abre **TNTMesh** e importa un STL o selecciona una malla.
3. Elige el tipo de corte, sitúa el cortador y pulsa **Dividir modelo**. Para un corte recto, selecciona un eje, introduce la rotación o dibuja una línea en la Vista 3D. TNTMesh conserva la malla original y la oculta de forma predeterminada.
4. Usa **Revisar malla** para comprobar la topología y el volumen, y luego **Exportar piezas** para guardar STL, OBJ, FBX o 3MF en una carpeta existente.

En un corte recto, abre **Ajustes de corte** para modificar las holguras, la cantidad de conectores o generar pasadores independientes. **Borrador** guarda una cadena de cortes en el archivo `.blend`. Añade los cortes, elige las piezas de entrada y pulsa **Generar piezas**.

STL y OBJ guardan coordenadas en milímetros y conservan la posición de ensamblaje. FBX guarda unidades físicas. La importación STL usa milímetros por defecto y permite elegir centímetros o pulgadas. Para los objetos existentes se usa la escala de la escena. Si la escena tiene las unidades desactivadas, 1 BU equivale a 1 mm.

En **Impresora**, selecciona un perfil, establece los márgenes y previsualiza el volumen útil. **Dividir para que quepa** corta modelos que superen el perfil con su orientación actual. [Perfiles y especificaciones](docs/printer-profiles.md)

**Calibrar conectores** genera un pin reutilizable y cavidades grabadas. Después de imprimir, selecciona la cavidad que ajustó mejor y guarda la holgura en el perfil. **Región de superficie** extrae una capa sólida por material, color o selección. **Cortes simétricos** refleja un corte recto junto con sus conectores. En **Ensamblaje** puedes revisar las piezas y separarlas visualmente conservando sus posiciones de exportación.

La validación comprueba el cierre, la orientación de las caras, las caras degeneradas y el volumen interior. Revisa la orientación, los soportes y la preparación final en tu slicer. Imprime una muestra para comprobar el ajuste con tu material y equipo.
