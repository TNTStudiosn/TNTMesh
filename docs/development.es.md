# Instalación y desarrollo

[English](development.md)

Descarga el ZIP desde [Releases](https://github.com/TNTStudiosn/TNTMesh/releases) o constrúyelo con Blender 4.5 LTS o una versión 5.x verificada. En Blender, abre Preferencias → Obtener extensiones → menú → Instalar desde disco y selecciona el ZIP. Pulsa **N** en la Vista 3D y abre **TNTMesh**.

```sh
ruff check .
blender --background --factory-startup --python-exit-code 1 --python tests/integration.py
mkdir -p dist
blender --factory-startup --command extension build --source-dir tntmesh --output-dir dist
blender --factory-startup --command extension validate dist/tntmesh-0.3.0-alpha.9.zip
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

Elige un conector **Cilíndrico** o **Hexagonal** en Región de superficie. TNTMesh prueba primero las caras interiores planas. En una unión curva busca un eje común de inserción y comprueba que el pin y la cavidad encajen en todo su ancho con el grosor seleccionado en ambas piezas. Puedes generar pines integrados o pasadores independientes. **Conectar al cuerpo principal** ajusta cada inserto al cuerpo retenido después de separar todos los materiales. Si la búsqueda no encuentra espacio, se conservan el original y los resultados previos.

**Cortes simétricos** refleja un plano recto respecto al eje y centro elegidos. Separa el primer plano del centro para obtener dos piezas exteriores y una central. Desde los detalles del corte puedes desplazar o girar el segundo plano sobre sus propios ejes. Los conectores siguen ese ajuste y ambas uniones deben pasar la comprobación de espacio. Si usas plantillas personalizadas, TNTMesh refleja también la forma del pin y de su cavidad. En Borrador puedes usar cada una de las tres piezas como entrada de cortes posteriores.

**Separar base** busca contornos cerrados de apoyo cerca de la parte inferior del modelo sobre el eje Z global. Pon la figura de pie y usa **Detectar apoyos** para revisar los contornos. Una altura de búsqueda de cero analiza el 22% inferior. Cada apoyo conserva su altura e inclinación, incluso si los pies están sobre niveles distintos. En los ajustes puedes mover cada apoyo, activar su conector y cambiar el diámetro. Usa una altura suficiente para incluir la base y revisa el resultado si los pies se ensanchan por encima del contacto. Borrador copia los ajustes de los apoyos de la malla de origen.

**Ensamblaje** agrupa las piezas por proyecto y permite seleccionarlas, encuadrarlas, ocultarlas, duplicarlas y medirlas. El deslizador separa la geometría solo en la vista previa. Las posiciones de exportación se conservan. Las piezas densas se muestran con su caja envolvente. **Revisar ensamblaje** busca traslapes de volumen en la posición actual.

**Revisar recorrido de inserción** comprueba una trayectoria recta hacia la posición de ensamblaje. Elige la dirección de partida y el recorrido. La prueba estima cuándo pueden entrar en contacto los triángulos y verifica el traslape entre sólidos en los límites y puntos intermedios de esos intervalos. Informa cuál es la primera pieza que bloquea el recorrido y a qué distancia se comprobó el bloqueo. Usa copias temporales y conserva la geometría y las transformaciones de la escena. Aplica las mismas tolerancias numéricas que la revisión de la posición ensamblada. Los recorridos con rotación están pendientes.

La exportación 3MF guarda mallas en milímetros como objetos independientes en posición de ensamblaje. Incluye geometría y deja los ajustes de impresión, soportes y materiales al slicer. [Especificación 3MF Core](https://github.com/3MFConsortium/spec_core)

En Windows se exportó un cubo de 24 mm dividido en dos mitades dentro de un solo 3MF. OrcaSlicer y Bambu Studio abrieron y reexportaron el archivo. En ambos se comprobó que se conservaron dos objetos de 24 × 24 × 12 mm. [CLI de Bambu Studio](https://github.com/bambulab/BambuStudio/wiki/Command-Line-Usage)

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
