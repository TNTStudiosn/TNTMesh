# Instalación y desarrollo

[English](development.md)

Descarga el ZIP desde [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) o constrúyelo con Blender 4.5 LTS o una versión 5.x verificada. En Blender, abre Preferencias → Obtener extensiones → menú → Instalar desde disco y selecciona el ZIP. Pulsa **N** en la Vista 3D y abre **TNTMesh**.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.3.0-alpha.14.zip
```

## Geometría y borradores

El motor evalúa la malla y sus transformaciones en un espacio centrado medido en milímetros. Los cortes usan el método booleano Exacto de Blender. Las piezas se crean después de comprobar el cierre y el volumen, y el motor conserva la malla de entrada.

El corte recto se puede orientar con un eje, rotación numérica o una línea en la Vista 3D. Bézier usa un perfil cúbico con resolución configurable. Rectángulo, Elipse y Contorno extraen regiones con profundidad finita. En Contorno, coloca puntos con clic o arrastra con Mayús y pulsa Enter para cerrar. Los puntos se proyectan al plano de la vista y pueden editarse desde los ajustes de corte. También puedes usar como cortador otra malla cerrada.

**Trazo manual** divide la malla siguiendo un trazo abierto. Coloca puntos con clic o arrastra con Mayús y pulsa Enter para terminar. TNTMesh prolonga ambos extremos más allá del modelo. Ajusta el desplazamiento, la profundidad o el suavizado, y edita o quita puntos en los ajustes del corte. Dibuja el trazo en Fácil y añade el corte actual a un borrador para reutilizarlo.

En **Ajuste**, elige el plano de la vista o la superficie de la malla activa. **Vértice** y **Arista** buscan un punto cercano en la cara bajo el cursor. Cuando no hay ningún vértice o arista cerca, usan la superficie. Los puntos fuera de la malla usan el plano de la vista. El ajuste también está disponible al dibujar cortes rectos, simétricos y contornos cerrados.

En **Directo** y **Cortes simétricos**, pulsa **Alinear con cara** y elige una cara de la malla activa. La normal de la cara fija la orientación del plano y el desplazamiento sigue controlando la distancia al centro del modelo.

Arrastra la flecha cian para mover el plano y actualizar **Desplazamiento (mm)**. Pulsa Esc durante el arrastre para recuperar el desplazamiento anterior. Puedes ocultar la flecha desde **Ajustes de corte**.

En un corte directo, **Sugerir conectores** usa el área de unión y el material disponible en ambos lados para proponer cantidad, diámetro, profundidad, forma y posiciones. El diámetro y la profundidad actuales funcionan como límites superiores. La propuesta conserva el grosor mínimo, las holguras y la opción de pasadores independientes. Usa la normal al plano como eje de inserción y elige el lado del pin según la profundidad disponible para la cavidad. En **Ajustes de corte** puedes editar las posiciones en milímetros sobre el plano o volver al reparto automático. En Borrador, la sugerencia evalúa la pieza de entrada del corte seleccionado y sus cortes previos. Al generar las piezas, TNTMesh vuelve a validar los ajustes.

Usa **Patrón de conectores** para distribuir posiciones en línea, círculo o cuadrícula. La distancia se mide entre centros de conectores vecinos. El patrón se centra sobre las posiciones actuales o sobre el origen de entrada si la lista está vacía. En Fácil, **Colocar con clic** añade un conector sobre el plano de corte. Estos comandos conservan las posiciones anteriores si el nuevo reparto invade una cavidad, sale del material o deja una pared demasiado delgada.

El patrón **Contorno** reparte las posiciones por longitud de arco sobre el contorno exterior de mayor área y las desplaza hacia dentro según el retiro del borde. Ajusta la rotación del patrón para desplazar el punto de partida si alguna posición queda muy cerca de una esquina.

**Reflejar X** y **Reflejar Y** añaden posiciones simétricas respecto al centro del plano de corte. Los iconos de copiar y pegar junto a **Sugerir conectores** transfieren la forma, dimensiones, tolerancias, lado del pin y posiciones entre cortes rectos. Al pegar, TNTMesh valida el corte de destino antes de aplicar los ajustes.

Elige **Imanes** en un corte directo o simétrico para crear una cavidad a cada lado de cada par. **Medidas comerciales** carga las dimensiones de un disco o bloque. Puedes guardar medidas propias en la biblioteca de la escena para editarlas y reutilizarlas. La profundidad de cavidad suma el grosor del imán, el retiro de la cara y el espacio para adhesivo. Los imanes de bloque pueden girarse dentro del plano de corte. En un corte directo también puedes usar los patrones o colocar un imán con clic. **Exportar lista de imanes** valida el corte y guarda un archivo de texto con la cantidad, dimensiones y distancias de instalación.

Elige **Cierre a presión flexible** en un corte recto o simétrico para unir las piezas en la dirección normal al corte. El brazo integrado tiene una rampa y un hombro de retención. El alojamiento ciego deja espacio para que el gancho flexione al pasar por la entrada y recupere su forma al asentarse. Ajusta el alcance, las medidas del brazo, la altura del gancho, el ángulo de rampa y el giro. Las holguras lateral y axial controlan el ajuste y la retención. En cortes rectos puedes buscar posiciones, aplicar patrones, colocar ganchos en la vista o transferir su configuración.

Indica el material de impresión y su deformación admisible medida con la orientación elegida. El panel estima la deformación con un modelo de brazo de sección constante cargado en el hombro, usando la altura del gancho como desplazamiento. La generación comprueba el material alrededor del alojamiento, las mallas cerradas, las formas flexionada y asentada, y la retención ante un retiro corto y rígido. Usa una muestra impresa para comprobar el esfuerzo de inserción, la retención y la durabilidad con el material y los ajustes elegidos. [Guía de diseño de Covestro](https://solutions.covestro.com/-/media/covestro/solution-center/brands/downloads/imported/1556891135.pdf) [Material y orientación de impresión según Formlabs](https://formlabs.com/blog/designing-3d-printed-snap-fit-enclosures/)

El corte añade instrucciones de encaje a la guía de ensamblaje. **Revisar recorrido de inserción** usa mallas rígidas y puede identificar el contacto previsto al introducir el gancho.

Elige **Encastre para varillas** en un corte recto o simétrico. Configura el diámetro o ancho de la varilla, la inserción en cada lado y las holguras. Puedes girar las varillas cuadradas en el plano de corte. El largo indicado suma ambas inserciones y la separación del corte. La holgura lateral se aplica por pared. La holgura axial añade espacio al fondo y permite que la varilla siga entrando en ambas piezas al llegar al tope. TNTMesh comprueba la pared alrededor de cada alojamiento, la separación entre ellos y el recorrido axial. Los archivos de impresión contienen las piezas. La guía de ensamblaje indica las dimensiones y la cantidad de varillas externas.

Elige **Unión atornillada** para un tornillo totalmente roscado de cabeza cilíndrica y una tuerca hexagonal compatible. Introduce el diámetro del vástago, el largo sin cabeza, el paso, las medidas de la cabeza y el ancho entre caras y el grosor de la tuerca. La guía registra cada par como componente externo. Los valores iniciales corresponden a herrajes M3. Mide los herrajes que vas a usar y comprueba el ajuste en una probeta impresa. [Tornillo totalmente roscado](https://www.bossard.com/mx-es/eshop/tornillos-estandar-con-huella/tornillos-de-cabeza-cilindrica-con-hueco-hexagonal-totalmente-roscados/p/3/) [Tuerca hexagonal](https://www.bossard.com/global-en/eshop/hex-nuts/hex-nuts-type-1/p/1983/)

TNTMesh genera un agujero pasante y rebajes accesibles desde el exterior. La holgura lateral se aplica a cada pared. La axial hunde la cabeza y la tuerca. La generación comprueba las superficies de apoyo, la pared alrededor de los alojamientos y el acceso por el eje del corte. El tornillo debe sobresalir de la tuerca por lo menos una longitud igual al paso. La generación se detiene si el tornillo queda corto, si otra pieza bloquea el acceso en un corte simétrico o si la holgura deja girar la tuerca. En cortes rectos puedes cambiar de lado la cabeza y usar los controles de posición. Sujeta la tuerca en el alojamiento hasta que tome la rosca.

Elige **Encaje a presión** en un corte recto o simétrico para generar un pasador ranurado integrado y un alojamiento ciego con entrada biselada. La **Interferencia radial** es la distancia que sobresale cada brazo en reposo respecto al radio del alojamiento. La interferencia total entre ambos brazos es el doble. La holgura lateral controla el espacio alrededor de la raíz y los costados. La holgura axial controla el espacio al fondo. En cortes rectos puedes sugerir o editar posiciones, usar patrones y cambiar de lado el pasador.

Indica el material de impresión y su límite elástico verificado en la orientación elegida. TNTMesh estima la deformación con un modelo de brazo cargado en el extremo y aplica un factor de dos a la estimación nominal. Comprueba el espacio que queda en la ranura al comprimirla, la pared alrededor del alojamiento, la interferencia prevista y el recorrido axial libre con el perfil comprimido. Imprime una muestra para medir la fuerza de inserción, la retención y el desgaste con el mismo proceso y orientación. Las comprobaciones generales de montaje e inserción incluyen la interferencia de las piezas en reposo. [Referencia de flexión de vigas](https://courses.grainger.illinois.edu/tam251/fa2017/BeamDeflectionTables.pdf)

**Ayudas de pegado** está en **Ajustes de corte** para perfiles estándar de pasador en cortes rectos o simétricos. Puedes elegir canales de adhesivo, un depósito bajo el pasador, una salida de aire hacia el exterior, un chaflán de entrada o ranuras de textura interna. Cada opción empieza desactivada. Los pasadores independientes conservan sus medidas y se preparan ambos alojamientos. **Alivio** modifica el tamaño de los rebajes. **Giro del alivio** orienta la salida y gira los canales de pared. La flecha de la vista indica hacia dónde apunta la salida.

El corte comprueba el material alrededor de cada alojamiento y a lo largo de la salida. Bloquea rutas que se acercan a otro alojamiento o cruzan un hueco interno. Comprueba que tu proceso de impresión pueda reproducir el rebaje más estrecho. La salida es más estrecha que los canales internos. La guía identifica las uniones con alojamientos preparados.

Elige **Bisagra de pasador** en un corte recto para generar dos hojas y un pasador con cabeza como tres piezas. Gira el borde de montaje en el plano de corte y desplaza la bisagra a lo largo de ese borde. El eje se sitúa hacia el exterior. Ajusta la cantidad de casquillos, sus diámetros y el del pasador, la holgura lateral alrededor del pasador, la separación axial entre casquillos y el ángulo de apertura. TNTMesh comprueba que todos los casquillos estén anclados y valida el espesor, el ajuste del pasador y el recorrido antes de publicar las piezas.

En **Ensamblaje**, el deslizador **Apertura** muestra el recorrido comprobado y conserva la posición original de las piezas para la edición y exportación. Usa **Revisar apertura** después de añadir piezas o mover el ensamblaje. El control destaca en rojo la pieza que bloquea el giro en una de las poses evaluadas. La guía identifica el pasador y el paso para introducirlo. La prueba usa movimiento rígido con una separación estimada de hasta 1 mm de desplazamiento entre poses. El ajuste y la retención físicos dependen de la muestra impresa y sus holguras.

La búsqueda de conectores comprueba que exista material alrededor del pin y la cavidad. La holgura lateral se mide por lado y la axial al fondo de la cavidad. Si la búsqueda no encuentra espacio para la cantidad solicitada, el corte se cancela. La reparación básica suelda vértices cercanos y puede cerrar agujeros simples sobre una copia.

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

Elige un conector **Cilíndrico** o **Hexagonal** en Región de superficie. TNTMesh prueba primero las caras interiores planas. En una unión curva busca un eje común de inserción y comprueba que el pin y la cavidad encajen en todo su ancho con el grosor seleccionado en ambas piezas. Puedes generar pines integrados o pasadores independientes. **Conectar al cuerpo principal** ajusta cada inserto al cuerpo retenido después de separar todos los materiales. Si la búsqueda no encuentra espacio, se conservan el original y los resultados previos.

**Cortes simétricos** refleja un plano recto respecto al eje y centro elegidos. Separa el primer plano del centro para obtener dos piezas exteriores y una central. Desde los detalles del corte puedes desplazar o girar el segundo plano sobre sus propios ejes. Los conectores siguen ese ajuste y ambas uniones deben pasar la comprobación de espacio. Si usas plantillas personalizadas, TNTMesh refleja también la forma del pin y de su cavidad. En Borrador puedes usar cada una de las tres piezas como entrada de cortes posteriores.

**Separar base** busca contornos cerrados de apoyo cerca de la parte inferior del modelo sobre el eje Z global. Pon la figura de pie y usa **Detectar apoyos** para revisar los contornos. Una altura de búsqueda de cero analiza el 22% inferior. Cada apoyo conserva su altura e inclinación, incluso si los pies están sobre niveles distintos. En los ajustes puedes mover cada apoyo, activar su conector y cambiar el diámetro. Usa una altura suficiente para incluir la base y revisa el resultado si los pies se ensanchan por encima del contacto. Borrador copia los ajustes de los apoyos de la malla de origen.

**Ensamblaje** agrupa las piezas por proyecto y permite seleccionarlas, encuadrarlas, ocultarlas, duplicarlas y medirlas. El deslizador separa la geometría solo en la vista previa. Las posiciones de exportación se conservan. Las piezas densas se muestran con su caja envolvente. **Revisar ensamblaje** busca traslapes de volumen en la posición actual.

**Revisar recorrido de inserción** comprueba una trayectoria recta hacia la posición de ensamblaje. Elige la dirección de partida y el recorrido. La prueba estima cuándo pueden entrar en contacto los triángulos y verifica el traslape entre sólidos en los límites y puntos intermedios de esos intervalos. Informa cuál es la primera pieza que bloquea el recorrido y a qué distancia se comprobó el bloqueo. Usa copias temporales y conserva la geometría y las transformaciones de la escena. Aplica las mismas tolerancias numéricas que la revisión de la posición ensamblada. Los recorridos con rotación están pendientes.

**Exportar guía de ensamblaje** crea una carpeta para el proyecto actual. Guarda HTML para el navegador, Markdown para editar, ambos documentos o solo las imágenes PNG de las vistas ensamblada y explosionada. Los números corresponden a la lista de piezas. Los cortes directos y los borradores guardan qué piezas y pasadores proceden de cada corte. El orden sugerido agrupa primero los subconjuntos internos. Los cortes con imanes registran las medidas y cantidades que se necesitan comprar. En proyectos anteriores se pueden recuperar grupos de corte directo cuando todavía existen sus registros. Vuelve a generar las piezas de borradores antiguos para guardar todo el historial de la guía.

Usa el campo de separación para ajustar la vista explosionada. El valor cero calcula la separación según el tamaño del ensamblaje. Las imágenes usan las posiciones actuales de las piezas. Las piezas cubiertas por completo aparecen en la lista. Conserva los dos PNG junto al documento si lo mueves a otra carpeta.

## Exportación

**Exportar piezas** guarda mallas cerradas en milímetros. Elige las piezas seleccionadas, todas las vigentes o solo los conectores independientes. En proyectos guardados antes de registrar tipos de conectores, conserva los nombres generados de los pasadores para usar ese filtro. STL, OBJ, FBX y PLY guardan un archivo por pieza. 3MF también permite guardar todas las piezas como objetos independientes en un solo archivo. El slicer controla el perfil, los soportes, los materiales y las trayectorias. [Especificación 3MF Core](https://github.com/3MFConsortium/spec_core)

**Posiciones de ensamblaje** conserva las transformaciones de cada pieza en la escena. **Cama de impresión** aplica el giro para impresión y lleva la base a Z = 0. Los archivos individuales se centran en XY. Un 3MF agrupado coloca las piezas en filas con la separación indicada y usa el volumen y los márgenes de la impresora seleccionada, cuando hay un perfil disponible. Ajusta la separación, el giro o la selección si las piezas exceden el espacio de una cama.

Usa el prefijo y la numeración opcional para nombrar los archivos. **Usar una subcarpeta** crea una carpeta dentro del destino, o dentro del archivo comprimido si activas **Guardar como ZIP**. La exportación conserva los archivos y las carpetas existentes si su nombre coincide.

En Windows se exportó un cubo de 24 mm dividido en dos mitades dentro de un solo 3MF. OrcaSlicer y Bambu Studio abrieron y reexportaron el archivo. En ambos se comprobó que se conservaron dos objetos de 24 × 24 × 12 mm. [CLI de Bambu Studio](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage)

Para comprobar la colocación en cama, se extrajo un 3MF agrupado de un ZIP y se reexportó desde ambos slicers. Cada uno conservó tres objetos imprimibles independientes, sus dimensiones tras el giro, la separación de 6 mm y las bases en Z = 0.

## Material y costo

Abre **Material y costo** y elige la malla activa, las mallas seleccionadas o el ensamblaje actual. Puedes ingresar densidad, precio por kilogramo y moneda. **Usar material de impresora** copia la tecnología, densidad, precio y grosor desde el perfil seleccionado. El cálculo muestra los valores por pieza y el total, con los pasadores independientes incluidos cuando pertenecen al ensamblaje. Usa la escala evaluada de la escena y requiere sólidos cerrados.

Para FDM, TNTMesh multiplica el área superficial por el grosor de pared, limita el resultado al volumen del modelo y aplica al resto el porcentaje de relleno. Para resina, usa el volumen de la malla. La revisión opcional de cavidades estima el ahorro comparando el volumen real con el de las superficies exteriores macizas. Si las superficies se cruzan o el anidamiento es ambiguo, el ahorro puede quedar sin calcular. El porcentaje de material extra añade al peso y costo una reserva para consumos como los soportes. Comprueba los valores finales en tu laminador.

## Verificación y publicación

Las pruebas de integración se ejecutan en Blender e incluyen exportación y reimportación, dimensiones de conectores, mallas huecas, cambios de escala, restauración de borradores y limpieza ante fallos. Para comprobar la interfaz, ejecuta `tests/viewport_smoke.py` en una instancia gráfica con un perfil aislado y define `TNTMESH_SMOKE_OUTPUT` como carpeta de salida. Para probar el dibujo y la cancelación, define `TNTMESH_TEST_EVENTS=1` y utiliza `--enable-event-simulate`. Define `TNTMESH_TEST_CONTOUR=1` para probar el contorno a mano alzada y `TNTMESH_TEST_PRINTER=1` para capturar el panel de impresora y el volumen útil.

Define `TNTMESH_TEST_PHASE3=1` para capturar la calibración, el resaltado de regiones, los planos simétricos y la vista de ensamblaje en la ventana de prueba de 1024 × 745.

Define `TNTMESH_TEST_BASE=1` para capturar los apoyos detectados en la base de dos alturas.

GitHub Actions compara el tag con el manifiesto, prueba el ZIP instalado y genera la suma SHA-256 antes de publicar. Las versiones alfa, beta y candidatas se marcan como experimentales.

Las pruebas pasaron en Windows y Linux con Blender 4.5.17 LTS, 5.1.2, 5.2.4 LTS y 5.3.0, y en macOS arm64 con 4.5.17 LTS. El código fuente también pasó con 4.2.23 LTS en Windows. El mínimo declarado para el ZIP es Blender 4.5.

## Pruebas de mallas densas

Ejecuta una operación por proceso y registra el modelo de procesador, la RAM, la versión de Blender, el sistema operativo, el tiempo y el pico de memoria. El modelo de prueba es un toro cerrado de cuadriláteros con radio mayor de 12 mm y menor de 3 mm. Puede generar las densidades de la especificación, desde 10,000 hasta 10,000,000 de caras.

```sh
blender --background --factory-startup --python-exit-code 1 --python tests/benchmark.py -- 100000 intersections
```

Usa `inspect` para revisar topología y volumen, `diagnostics` para el análisis básico, `intersections` para añadir cruces y traslapes coplanares, o `split` para un corte recto exacto sin conectores. El resultado se imprime en JSON. El cronómetro arranca después de construir la malla. El pico de memoria incluye el arranque de Blender y la construcción del modelo.

Las mediciones usaron Blender 5.3.0 en Windows 11 compilación 26200, con un Ryzen 7 3700X, 16 procesadores lógicos y 31.9 GiB de RAM. Cada fila corresponde a una ejecución.

| Caras | Operación | Segundos | Pico en GiB |
| ---: | --- | ---: | ---: |
| 10,000 | Intersecciones | 1.18 | 0.20 |
| 100,000 | Intersecciones | 12.13 | 0.45 |
| 100,000 | Corte recto | 2.74 | 0.64 |
| 500,000 | Diagnóstico básico | 8.57 | 0.99 |
| 1,000,000 | Topología y volumen | 4.70 | 1.00 |
| 3,000,000 | Topología y volumen | 16.53 | 2.69 |
| 5,000,000 | Topología y volumen | 25.26 | 4.25 |
| 10,000,000 | Topología y volumen | 56.49 | 8.34 |

Estas cifras corresponden a las operaciones indicadas sobre el modelo de prueba. Falta verificar el corte y el diagnóstico completo de intersecciones en las densidades más altas.

## Actualizaciones

En Preferencias → Obtener extensiones → Repositorios → Añadir repositorio remoto, introduce la URL de un solo canal. El [índice experimental](https://tntstudiosn.github.io/TNTMesh/experimental/index.json) contiene las versiones preliminares. El [índice estable](https://tntstudiosn.github.io/TNTMesh/stable/index.json) se poblará tras la primera publicación estable.

Usa las opciones de sincronización y actualización de Blender. Puedes habilitar la consulta al iniciar desde las preferencias de repositorios. Blender gestiona el acceso en línea, la compatibilidad y la instalación. Si ya instalaste el ZIP, desactiva esa copia antes de activar la versión del canal remoto.
