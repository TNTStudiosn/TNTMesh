# Instalación y desarrollo

[English](development.md)

Descarga el ZIP desde [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) o constrúyelo con Blender 4.5 LTS o una versión 5.x verificada. En Blender, abre Preferencias → Obtener extensiones → menú → Instalar desde disco y selecciona el ZIP. Pulsa **N** en la Vista 3D y abre **TNTMesh**.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.3.0-alpha.1.zip
```

## Geometría y borradores

El motor evalúa la malla y sus transformaciones en un espacio centrado medido en milímetros. Los cortes usan el método booleano Exacto de Blender. Las piezas se crean después de comprobar el cierre y el volumen, y el motor conserva la malla de entrada.

El corte recto se puede orientar con un eje, rotación numérica o una línea en la Vista 3D. Bézier usa un perfil cúbico con resolución configurable. Rectángulo, Elipse y Contorno extraen regiones con profundidad finita. En Contorno, coloca puntos con clic o arrastra con Mayús y pulsa Enter para cerrar. Los puntos se proyectan al plano de la vista y pueden editarse desde los ajustes de corte. También puedes usar como cortador otra malla cerrada.

Los conectores se colocan en cortes rectos. La búsqueda comprueba que exista material alrededor del pin y la cavidad. La holgura lateral se mide por lado y la axial al fondo de la cavidad. Si la búsqueda no encuentra espacio para la cantidad solicitada, el corte se cancela. La reparación básica suelda vértices cercanos y puede cerrar agujeros simples sobre una copia.

Un conector personalizado utiliza dos plantillas cerradas con el origen de cada objeto en el centro de la unión. Ambas cruzan el plano XY de su origen. Z positiva es la dirección de inserción y Z negativa ancla el pin o abre el cortador de la cavidad. TNTMesh conserva la escala y la rotación, ignora la posición en la escena y comprueba que la parte saliente quepa en la cavidad. Diseña la holgura en la propia plantilla de cavidad. Estas plantillas se usan con cortes rectos sin separación.

Cada borrador guarda la referencia a la fuente y los identificadores de las operaciones en el archivo `.blend`. Un corte puede consumir una pieza de un corte anterior. Si la cadena falla, la última generación de piezas se conserva. La reconstrucción actual recalcula todos los cortes activos.

Los perfiles de impresora se guardan en la escena y se pueden transferir entre proyectos por JSON. La comprobación de dimensiones descuenta el margen en ambos lados de cada eje. Las orientaciones alternativas prueban permutaciones de los tres ejes. **Dividir para que quepa** valida las medidas de cada pieza antes de mostrar los resultados.

La exportación 3MF guarda mallas en milímetros como objetos independientes en posición de ensamblaje. Incluye geometría y deja los ajustes de impresión, soportes y materiales al slicer. [Especificación 3MF Core](https://github.com/3MFConsortium/spec_core)

En Windows se exportó un cubo de 24 mm dividido en dos mitades dentro de un solo 3MF. OrcaSlicer y Bambu Studio abrieron y reexportaron el archivo. En ambos se comprobó que se conservaron dos objetos de 24 × 24 × 12 mm. [CLI de Bambu Studio](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage)

## Verificación y publicación

Las pruebas de integración se ejecutan en Blender e incluyen exportación y reimportación, dimensiones de conectores, mallas huecas, cambios de escala, restauración de borradores y limpieza ante fallos. Para comprobar la interfaz, ejecuta `tests/viewport_smoke.py` en una instancia gráfica con un perfil aislado y define `TNTMESH_SMOKE_OUTPUT` como carpeta de salida. Para probar el dibujo y la cancelación, define `TNTMESH_TEST_EVENTS=1` y utiliza `--enable-event-simulate`. Define `TNTMESH_TEST_CONTOUR=1` para probar el contorno a mano alzada y `TNTMESH_TEST_PRINTER=1` para capturar el panel de impresora y el volumen útil.

GitHub Actions compara el tag con el manifiesto, prueba el ZIP instalado y genera la suma SHA-256 antes de publicar. Las versiones alfa, beta y candidatas se marcan como experimentales.

Las pruebas pasaron en Windows y Linux con Blender 4.5.17 LTS, 5.1.2 y 5.2.4 LTS, y en macOS arm64 con 4.5.17 LTS. El código fuente también pasó con 4.2.23 LTS en Windows. El mínimo declarado para el ZIP es Blender 4.5.

## Actualizaciones

En Preferencias → Obtener extensiones → Repositorios → Añadir repositorio remoto, introduce la URL de un solo canal. El [índice experimental](https://tntstudiosn.github.io/TNTMesh/experimental/index.json) contiene las versiones preliminares. El [índice estable](https://tntstudiosn.github.io/TNTMesh/stable/index.json) se poblará tras la primera publicación estable.

Usa las opciones de sincronización y actualización de Blender. Puedes habilitar la consulta al iniciar desde las preferencias de repositorios. Blender gestiona el acceso en línea, la compatibilidad y la instalación. Si ya instalaste el ZIP, desactiva esa copia antes de activar la versión del canal remoto.
