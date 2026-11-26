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

En **Ensamblaje → Revisar recorrido de inserción**, indica el recorrido y, si hace falta, el ángulo inicial. El giro puede usar como pivote el centro de la pieza, el origen del objeto o el cursor 3D. El aviso muestra la distancia y el ángulo donde se encontró un choque. Reduce el paso de muestreo para comprobar detalles más pequeños durante el giro.

Elige **Cola de milano** en un corte recto o simétrico para crear un riel deslizante y una ranura abierta al borde. En **Ajustes de corte** puedes configurar el cuello, la cabeza, la altura, el largo, el ángulo de salida y las holguras. En cortes rectos, **Sugerir rieles** busca posiciones para las medidas actuales y muestra la flecha de salida. El corte comprueba el material alrededor del riel en su posición final y del tope. En **Ensamblaje**, usa **Dirección del ensamblaje** para revisar el deslizamiento. El cuadro propone una distancia de recorrido.

Los cortes rectos, simétricos, de región y de base admiten perfiles cilíndricos cónicos, cuadrados, rectangulares, triangulares, octagonales, ovalados, en D, en estrella, en cruz y de lengüeta y ranura. En **Ajustes de corte** puedes editar medidas, giro y holguras. En cortes rectos, **Sugerir conectores** busca posiciones para el perfil elegido. **Calibrar conectores** genera una muestra imprimible con la misma geometría.

En **Impresora → Ajustes del perfil**, selecciona **Holguras por material** para cargar valores iniciales de holgura lateral, axial y grosor mínimo. Usa **Usar holguras del perfil** para copiarlos al corte. Calibra con tu material e impresora para determinar el ajuste final.

La validación comprueba el cierre, la orientación de las caras, las caras degeneradas y el volumen interior. Revisa la orientación, los soportes y la preparación final en tu slicer. Imprime una muestra para comprobar el ajuste con tu material y equipo.

Para imprimir en resina, abre **Preparación para resina**, ajusta el grosor de pared y el tamaño de vóxel, y selecciona **Crear copia hueca**. Usa una malla cerrada que se superponga con la pared del modelo para conservar una región sólida o reforzar una unión. Con **Colocar drenaje** puedes hacer clic en el exterior. También puedes colocar un drenaje circular sugerido según la dirección de impresión y generar un tapón aparte. Para una abertura irregular, coloca una malla cerrada que atraviese la pared y elige **Malla personalizada**. **Diagnóstico de malla** puede señalar las cavidades que siguen cerradas.

En **Diagnóstico de malla → Revisar malla**, activa **Mapa de grosor** para examinar el grosor aproximado en las cavidades de conectores y otros detalles. Introduce un grosor mínimo para señalar las caras por debajo de ese valor. El gris indica que no se obtuvo una medición confiable.

En **Preparación para resina → Trampas de resina**, indica la dirección de impresión en los ejes globales, desde la primera capa hasta la última, y elige **Revisar trampas de resina**. Selecciona un resultado para localizar cavidades cerradas o posibles zonas de succión. La estimación geométrica usa el paso de muestreo mostrado y puede omitir aberturas más pequeñas. Confirma la secuencia de capas y la ventilación en tu slicer.
