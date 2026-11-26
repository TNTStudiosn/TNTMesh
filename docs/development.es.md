# Instalación y desarrollo

[English](development.md)

Descarga el ZIP desde [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) o constrúyelo con Blender 4.5 LTS o una versión 5.x verificada. En Blender, abre Preferencias → Obtener extensiones → menú → Instalar desde disco y selecciona el ZIP. Pulsa **N** en la Vista 3D y abre **TNTMesh**.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.3.0-alpha.5.zip
```

## Geometría y borradores

El motor evalúa la malla y sus transformaciones en un espacio centrado medido en milímetros. Los cortes usan el método booleano Exacto de Blender. Las piezas se crean después de comprobar el cierre y el volumen, y el motor conserva la malla de entrada.

El corte recto se puede orientar con un eje, rotación numérica o una línea en la Vista 3D. Bézier usa un perfil cúbico con resolución configurable. Rectángulo, Elipse y Contorno extraen regiones con profundidad finita. En Contorno, coloca puntos con clic o arrastra con Mayús y pulsa Enter para cerrar. Los puntos se proyectan al plano de la vista y pueden editarse desde los ajustes de corte. También puedes usar como cortador otra malla cerrada.

**Trazo manual** divide la malla siguiendo un trazo abierto proyectado al plano de la vista. Coloca puntos con clic o arrastra con Mayús y pulsa Enter para terminar. TNTMesh prolonga ambos extremos más allá del modelo. Ajusta el desplazamiento, la profundidad o el suavizado, y edita o quita puntos en los ajustes del corte. Dibuja el trazo en Fácil y añade el corte actual a un borrador para reutilizarlo.

Los conectores se colocan en cortes rectos. La búsqueda comprueba que exista material alrededor del pin y la cavidad. La holgura lateral se mide por lado y la axial al fondo de la cavidad. Si la búsqueda no encuentra espacio para la cantidad solicitada, el corte se cancela. La reparación básica suelda vértices cercanos y puede cerrar agujeros simples sobre una copia.

En **Reparar**, activa **Corregir orientación de caras** para corregir la orientación de caras vecinas y de las superficies cerradas según su profundidad de anidamiento. La copia conserva las cavidades y los sólidos separados. La reparación se detiene si las superficies se cruzan o si el anidamiento es ambiguo.

Un conector personalizado utiliza dos plantillas cerradas con el origen de cada objeto en el centro de la unión. Ambas cruzan el plano XY de su origen. Z positiva es la dirección de inserción y Z negativa ancla el pin o abre el cortador de la cavidad. TNTMesh conserva la escala y la rotación, ignora la posición en la escena y comprueba que la parte saliente quepa en la cavidad. Diseña la holgura en la propia plantilla de cavidad. Estas plantillas se usan con cortes rectos sin separación.

Cada borrador guarda la referencia a la fuente y los identificadores de las operaciones en el archivo `.blend`. Un corte puede consumir una pieza de un corte anterior. Si la cadena falla, la última generación de piezas se conserva. La reconstrucción actual recalcula todos los cortes activos.

Los perfiles de impresora se guardan en la escena y se pueden transferir entre proyectos por JSON. La comprobación de dimensiones descuenta el margen en ambos lados de cada eje. Las orientaciones alternativas prueban permutaciones de los tres ejes. **Dividir para que quepa** valida las medidas de cada pieza antes de mostrar los resultados.

**Calibrar conectores** usa los mismos perfiles cilíndricos y hexagonales de los cortes rectos. La muestra predeterminada va de 0.05 a 0.40 mm de holgura por lado en pasos de 0.05 mm. También puedes elegir la cantidad de muestras. Exporta el kit e imprímelo con el material y los ajustes que quieres calibrar. Voltea el pin de prueba para probar las cavidades y selecciona en Blender la que mejor ajustó. **Guardar holgura en el perfil** registra ese valor en la impresora seleccionada. Usa los ajustes del perfil para transferir la holgura a cortes futuros.

**Región de superficie** admite ranuras de material, caras seleccionadas, atributos booleanos de caras, grupos de vértices y color RGB lineal. En grupos y colores deben coincidir todos los vértices o muestras de la cara. Puedes ampliar o reducir la selección por anillos de caras vecinas. El cortador se cierra por los bordes y penetra la malla a la profundidad elegida. El motor comprueba cruces en el cortador y valida el cierre y volumen de las dos piezas. Los borradores leen los atributos del modelo al reconstruirse.

**Suavizar contorno**, en Ajustes de corte, ajusta el borde sobre la superficie original antes de cortar. Cero conserva el borde de la selección. La vista superpuesta muestra las caras elegidas en cian y el contorno propuesto en violeta. Cada vértice puede desplazarse hasta el 45% de su arista de borde más corta y debe proyectarse sobre uno de sus triángulos. El cortador y las piezas pasan la validación geométrica habitual.

**Diagnóstico de malla → Analizar malla** revisa la geometría evaluada en milímetros. Detecta aristas abiertas, geometría no manifold, orientación inconsistente, aristas de longitud cero, triángulos degenerados, vértices cercanos y caras duplicadas. La opción de intersecciones revisa triángulos cruzados sin vértices en común y traslapes con área entre triángulos coplanares. El contacto por arista está permitido. Al revisar superficies cerradas que no se cruzan, compara la profundidad de anidamiento con la orientación para distinguir cavidades, superficies internas mal orientadas y exteriores invertidos. Omite la clasificación si el resultado es ambiguo. Selecciona un hallazgo para aislar sus marcas o pulsa la lupa para encuadrarlas. El visor muestra hasta 256 ubicaciones por categoría y borra las marcas al editar, deshacer o recargar.

Configura **Grosor mínimo (mm)** para marcar paredes delgadas en un sólido cerrado. TNTMesh lanza rayos hacia dentro desde el centro de cada triángulo y estima el grosor al encontrar una cara opuesta. El resultado muestra la menor medida por debajo del límite y las ubicaciones marcadas. Las zonas delgadas que quedan entre muestras pueden pasar inadvertidas. Usa cero para omitir la revisión.

En modo Fácil, usa **Región de superficie → Por ranura de material → Separar por material** para procesar varias ranuras en una operación. Elige la ranura del cuerpo principal y la profundidad de las zonas a extraer. Los cortes avanzan en el orden de las ranuras. Si dos zonas contiguas comparten volumen interior, ese volumen queda con la que se procesa primero. El cuerpo principal conserva el resto. La operación publica todas las piezas juntas después de comprobar su cierre y volumen. Conserva la malla original y usa el color de cada material para la vista previa.

Elige un conector **Cilíndrico** o **Hexagonal** en Región de superficie. TNTMesh ordena las caras interiores planas por área y comprueba el espacio, la pared y la profundidad a ambos lados antes de generar el pin y la cavidad. Puedes generar pines integrados o pasadores independientes. **Conectar al cuerpo principal** ajusta cada inserto al cuerpo retenido después de separar todos los materiales. Si una unión carece de espacio, se conservan el original y los resultados previos. La búsqueda considera hasta doce planos. Las uniones muy curvas pueden carecer de caras planas aptas.

**Cortes simétricos** refleja un plano recto respecto al eje y centro elegidos. Separa el primer plano del centro para obtener dos piezas exteriores y una central. Desde los detalles del corte puedes desplazar o girar el segundo plano sobre sus propios ejes. Los conectores siguen ese ajuste y ambas uniones deben pasar la comprobación de espacio. Si usas plantillas personalizadas, TNTMesh refleja también la forma del pin y de su cavidad. En Borrador puedes usar cada una de las tres piezas como entrada de cortes posteriores.

**Separar base** busca contornos cerrados de apoyo cerca de la parte inferior del modelo sobre el eje Z global. Pon la figura de pie y usa **Detectar apoyos** para revisar los contornos. Una altura de búsqueda de cero analiza el 22% inferior. Cada apoyo conserva su altura e inclinación, incluso si los pies están sobre niveles distintos. En los ajustes puedes mover cada apoyo, activar su conector y cambiar el diámetro. Usa una altura suficiente para incluir la base y revisa el resultado si los pies se ensanchan por encima del contacto. Borrador copia los ajustes de los apoyos de la malla de origen.

**Ensamblaje** agrupa las piezas por proyecto y permite seleccionarlas, encuadrarlas, ocultarlas, duplicarlas y medirlas. El deslizador separa la geometría solo en la vista previa. Las posiciones de exportación se conservan. Las piezas densas se muestran con su caja envolvente. **Revisar ensamblaje** busca traslapes de volumen en la posición actual.

**Revisar recorrido de inserción** comprueba una trayectoria recta hacia la posición de ensamblaje. Elige la dirección de partida y el recorrido. La prueba estima cuándo pueden entrar en contacto los triángulos y verifica el traslape entre sólidos en los límites y puntos intermedios de esos intervalos. Informa cuál es la primera pieza que bloquea el recorrido y a qué distancia se comprobó el bloqueo. Usa copias temporales y conserva la geometría y las transformaciones de la escena. Aplica las mismas tolerancias numéricas que la revisión de la posición ensamblada. Los recorridos con rotación están pendientes.

La exportación 3MF guarda mallas en milímetros como objetos independientes en posición de ensamblaje. Incluye geometría y deja los ajustes de impresión, soportes y materiales al slicer. [Especificación 3MF Core](https://github.com/3MFConsortium/spec_core)

En Windows se exportó un cubo de 24 mm dividido en dos mitades dentro de un solo 3MF. OrcaSlicer y Bambu Studio abrieron y reexportaron el archivo. En ambos se comprobó que se conservaron dos objetos de 24 × 24 × 12 mm. [CLI de Bambu Studio](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage)

## Verificación y publicación

Las pruebas de integración se ejecutan en Blender e incluyen exportación y reimportación, dimensiones de conectores, mallas huecas, cambios de escala, restauración de borradores y limpieza ante fallos. Para comprobar la interfaz, ejecuta `tests/viewport_smoke.py` en una instancia gráfica con un perfil aislado y define `TNTMESH_SMOKE_OUTPUT` como carpeta de salida. Para probar el dibujo y la cancelación, define `TNTMESH_TEST_EVENTS=1` y utiliza `--enable-event-simulate`. Define `TNTMESH_TEST_CONTOUR=1` para probar el contorno a mano alzada y `TNTMESH_TEST_PRINTER=1` para capturar el panel de impresora y el volumen útil.

Define `TNTMESH_TEST_PHASE3=1` para capturar la calibración, el resaltado de regiones, los planos simétricos y la vista de ensamblaje en la ventana de prueba de 1024 × 745.

Define `TNTMESH_TEST_BASE=1` para capturar los apoyos detectados en la base de dos alturas.

GitHub Actions compara el tag con el manifiesto, prueba el ZIP instalado y genera la suma SHA-256 antes de publicar. Las versiones alfa, beta y candidatas se marcan como experimentales.

Las pruebas pasaron en Windows y Linux con Blender 4.5.17 LTS, 5.1.2, 5.2.4 LTS y 5.3.0, y en macOS arm64 con 4.5.17 LTS. El código fuente también pasó con 4.2.23 LTS en Windows. El mínimo declarado para el ZIP es Blender 4.5.

## Actualizaciones

En Preferencias → Obtener extensiones → Repositorios → Añadir repositorio remoto, introduce la URL de un solo canal. El [índice experimental](https://tntstudiosn.github.io/TNTMesh/experimental/index.json) contiene las versiones preliminares. El [índice estable](https://tntstudiosn.github.io/TNTMesh/stable/index.json) se poblará tras la primera publicación estable.

Usa las opciones de sincronización y actualización de Blender. Puedes habilitar la consulta al iniciar desde las preferencias de repositorios. Blender gestiona el acceso en línea, la compatibilidad y la instalación. Si ya instalaste el ZIP, desactiva esa copia antes de activar la versión del canal remoto.
