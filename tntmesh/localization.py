# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

SPANISH = {
    "Import STL": "Importar STL",
    "Import": "Importar",
    "Import an STL using explicit length units": "Importa un STL en las unidades indicadas",
    "STL units": "Unidades del STL",
    "Millimeters": "Milímetros",
    "Centimeters": "Centímetros",
    "Inches": "Pulgadas",
    "Treat a unit in the file as one millimeter": "Cada unidad del archivo equivale a un milímetro",
    "Treat a unit in the file as one centimeter": "Cada unidad del archivo equivale a un centímetro",
    "Treat a unit in the file as one inch": "Cada unidad del archivo equivale a una pulgada",
    "Select a mesh or import an STL.": "Selecciona una malla o importa un STL.",
    "Switch to Object Mode to use TNTMesh.": "Cambia a Modo Objeto para usar TNTMesh.",
    "Prepare": "Preparar",
    "Scale": "Escala",
    "Repair": "Reparar",
    "Weld distance (mm)": "Distancia de unión (mm)",
    "Merge vertices within this distance on the copy": "Une los vértices cercanos en la copia",
    "Fill small holes": "Cerrar agujeros pequeños",
    "Attempt to cap simple boundary loops on the copy":
        "Intenta cerrar los contornos abiertos simples en la copia",
    "Max. hole edges": "Aristas máx. por agujero",
    "Correct face orientation": "Corregir orientación de caras",
    "Orient closed shells and preserve enclosed cavities on the copy":
        "Orienta las superficies cerradas y conserva las cavidades en la copia",
    "Close the mesh before correcting its face orientation.":
        "Cierra la malla antes de corregir la orientación de sus caras.",
    "Fix intersecting surfaces before correcting face orientation.":
        "Corrige las superficies que se cruzan antes de orientar las caras.",
    "The mesh has ambiguous shell nesting.": "El anidamiento de las superficies es ambiguo.",
    "Create Repaired Copy": "Crear copia reparada",
    "Apply the selected mesh repairs to a new copy": "Aplica las correcciones seleccionadas a una copia",
    "Check the repair limits.": "Revisa los límites de reparación.",
    "{name} · Repaired": "{name} · Reparado",
    "Created a closed repaired copy. The input mesh was kept.":
        "Se creó una copia cerrada y se conservó la malla de entrada.",
    "Axis": "Eje",
    "World axis perpendicular to the cutting plane": "Eje global perpendicular al plano de corte",
    "Free": "Libre",
    "Rotate the cutting plane": "Gira el plano de corte",
    "Plane rotation": "Rotación del plano",
    "World rotation of the plane from its default Z orientation":
        "Rotación global del plano a partir de su orientación predeterminada en Z",
    "Check the rotation of the cut.": "Revisa la rotación del plano de corte.",
    "Cut type": "Tipo de corte",
    "Straight": "Recto",
    "Split along a plane": "Divide con un plano",
    "Bézier Curve": "Curva Bézier",
    "Split along a cubic Bézier profile": "Divide con un perfil Bézier cúbico",
    "Rectangle": "Rectángulo",
    "Extract a rectangular region": "Extrae una región rectangular",
    "Ellipse": "Elipse",
    "Extract an elliptical region": "Extrae una región elíptica",
    "Cutter Object": "Objeto cortador",
    "Extract the region inside a closed mesh": "Extrae la región dentro de una malla cerrada",
    "Cutter": "Cortador",
    "Show cutter": "Mostrar cortador",
    "Size (mm)": "Tamaño (mm)",
    "Width, height and depth of the extraction volume":
        "Ancho, altura y profundidad del volumen de extracción",
    "In-plane shift (mm)": "Desplazamiento en el plano (mm)",
    "Control heights (mm)": "Altura de controles (mm)",
    "Curve samples": "Muestras de la curva",
    "Choose a separate closed mesh as the cutter.": "Elige otra malla cerrada como cortador.",
    "The cutter is not in this view layer.": "El cortador no está en esta capa de vista.",
    "Check the position and dimensions of the cutter.": "Revisa la posición y medidas del cortador.",
    "Check the control heights and curve resolution.": "Revisa las alturas y resolución de la curva.",
    "The cutter must leave material on both sides of the cut.":
        "El cortador debe dejar material en ambos lados del corte.",
    "Draw Cut Line": "Dibujar línea de corte",
    "Draw on Model": "Dibujar sobre el modelo",
    "Draw a line or contour in the 3D Viewport": "Dibuja una línea o un contorno en la Vista 3D",
    "Contour": "Contorno",
    "Draw Contour": "Dibujar contorno",
    "Manual Path": "Trazo manual",
    "Split along an open path drawn in the viewport": "Divide el modelo con un trazo abierto en la Vista 3D",
    "Draw Path": "Dibujar trazo",
    "Align to Face": "Alinear con cara",
    "Orient the cut using a face normal and keep the current offset":
        "Orienta el corte con la normal de una cara y conserva el desplazamiento actual",
    "Click a face to align the cut · Esc to cancel":
        "Haz clic en una cara para alinear el corte · Esc para cancelar",
    "Choose a face on the active mesh.": "Elige una cara de la malla activa.",
    "Path smoothing": "Suavizado del trazo",
    "Snap": "Ajuste",
    "View Plane": "Plano de la vista",
    "Project onto a plane through the model": "Proyecta sobre un plano que atraviesa el modelo",
    "Surface": "Superficie",
    "Vertex": "Vértice",
    "Edge": "Arista",
    "Use the point where the cursor ray hits the model": "Usa el punto de la malla bajo el cursor",
    "Snap to a nearby vertex of the surface under the cursor":
        "Ajusta a un vértice cercano de la superficie bajo el cursor",
    "Snap to a nearby edge of the surface under the cursor":
        "Ajusta a una arista cercana de la superficie bajo el cursor",
    "Soften the interior points of the manual path": "Suaviza los puntos interiores del trazo manual",
    "Draw a path with at least two valid points.": "Dibuja un trazo con al menos dos puntos válidos.",
    "Choose up to 12 path smoothing passes.": "Elige hasta 12 pasos de suavizado.",
    "The path has adjacent points that are too close.": "El trazo contiene puntos consecutivos muy cerca.",
    "Remove Point": "Quitar punto",
    "Click points or Shift-drag · Enter to finish · Esc to cancel":
        "Haz clic o arrastra con Mayús · Enter para terminar · Esc para cancelar",
    "Extract a drawn or freehand contour": "Extrae una región dibujada punto a punto o a mano alzada",
    "Click points or Shift-drag · Enter to close · Esc to cancel":
        "Haz clic o arrastra con Mayús · Enter cierra · Esc cancela",
    "The contour has reached 1024 points.": "El contorno llegó al límite de 1024 puntos.",
    "Draw a contour with at least three valid points.": "Dibuja un contorno con al menos tres puntos válidos.",
    "The contour has adjacent points that are too close.": "El contorno contiene puntos consecutivos muy cerca.",
    "The contour crosses or folds over itself.": "El contorno se cruza o se dobla sobre sí mismo.",
    "The contour does not enclose an area.": "El contorno no encierra un área.",
    "Position (mm)": "Posición (mm)",
    "Depth (mm)": "Profundidad (mm)",
    "Surface Region": "Región de superficie",
    "Extract a solid piece from matching faces": "Extrae un sólido a partir de las caras elegidas",
    "Region source": "Origen de la región",
    "By Material Slot": "Por ranura de material",
    "Source material slot": "Ranura de origen",
    "Empty material slot": "Ranura sin material",
    "Use faces assigned to a material slot": "Usa las caras asignadas a una ranura",
    "Selected Faces": "Caras seleccionadas",
    "Use the face selection saved on the mesh": "Usa la selección de caras guardada en la malla",
    "Uses saved face selection.": "Usa la selección de caras.",
    "Face Mask": "Máscara de caras",
    "Use a Boolean attribute on the face domain": "Usa un atributo booleano de las caras",
    "Vertex Group": "Grupo de vértices",
    "Use faces whose vertices reach the group weight":
        "Usa las caras cuyos vértices alcanzan el peso indicado",
    "Color Attribute": "Atributo de color",
    "Match all face colors within the given RGB tolerance":
        "Exige que los colores de cada cara estén dentro de la tolerancia RGB",
    "Target color": "Color objetivo",
    "RGB tolerance": "Tolerancia RGB",
    "Minimum weight": "Peso mínimo",
    "Grow / shrink": "Ampliar o reducir",
    "Add or remove rings of edge-adjacent faces": "Agrega o quita anillos de caras vecinas",
    "Highlight region": "Resaltar región",
    "Extract Region": "Extraer región",
    "Extract the region without a connector": "Extrae la región sin conector",
    "Find a matching pin position inside the region seam": "Ubica un pin cilíndrico en la unión de la región",
    "Find a matching hexagonal pin position inside the region seam":
        "Ubica un pin hexagonal en la unión de la región",
    "No region seam can fit the requested connectors.":
        "Ninguna unión de la región tiene espacio para los conectores elegidos.",
    "Boundary smoothing": "Suavizar contorno",
    "Relax the cut contour along the original surface": "Suaviza el contorno sobre la superficie original",
    "Choose between zero and twelve smoothing passes.": "Elige entre cero y doce pasadas de suavizado.",
    "Mesh Diagnostics": "Diagnóstico de malla",
    "Scan Mesh": "Analizar malla",
    "Find mesh issues and highlight their locations in the viewport":
        "Detecta problemas de la malla y resalta sus ubicaciones en la Vista 3D",
    "Nearby vertex (mm)": "Vértices cercanos (mm)",
    "Flag vertices within this distance. Zero skips the proximity check":
        "Marca los vértices dentro de esta distancia. Cero omite esta comprobación",
    "Small shell (mm³)": "Componente pequeño (mm³)",
    "Check intersections": "Buscar intersecciones",
    "Minimum wall (mm)": "Grosor mínimo (mm)",
    "Flag walls thinner than this limit. Zero skips the thickness check":
        "Marca paredes por debajo de este grosor. Usa cero para omitir la revisión",
    "Thin wall faces": "Caras con pared delgada",
    "Wall check needs a closed solid.": "El grosor requiere un sólido cerrado.",
    "Thinnest sample · {size:.3f} mm": "Menor grosor medido · {size:.3f} mm",
    "No samples below {size:.3f} mm": "Sin muestras por debajo de {size:.3f} mm",
    "Choose nonnegative mesh tolerances.": "Usa tolerancias de malla de cero o mayores.",
    "No faces": "Sin caras",
    "Invalid coordinates": "Coordenadas inválidas",
    "Open edges": "Aristas abiertas",
    "Non-manifold geometry": "Geometría no manifold",
    "Inconsistent winding": "Orientación inconsistente",
    "Zero-length edges": "Aristas de longitud cero",
    "Degenerate triangles": "Triángulos degenerados",
    "Near-duplicate vertices": "Vértices casi duplicados",
    "Duplicate faces": "Caras duplicadas",
    "Nonpositive enclosed volume": "Volumen interior no positivo",
    "Disconnected surface shells": "Superficies desconectadas",
    "Small closed shells": "Componentes cerrados pequeños",
    "Faces with intersections": "Caras con intersecciones",
    "Closed cavities": "Cavidades cerradas",
    "Miswound internal shells": "Superficies internas mal orientadas",
    "Inverted shells": "Superficies invertidas",
    "Overlapping coplanar faces": "Caras coplanares traslapadas",
    "Review the shells and cavities in Mesh Diagnostics.": "Revisa las superficies y cavidades en el diagnóstico.",
    "Mesh scan found {count} issue categories.": "Categorías con hallazgos · {count}",
    "No issues found in the enabled checks.": "Sin problemas en las comprobaciones activas.",
    "Mesh Findings": "Resultados del análisis",
    "Intersection check skipped": "Intersecciones sin comprobar",
    "All Findings": "Todos los hallazgos",
    "View Mesh Finding": "Ver hallazgo de malla",
    "Scan Again": "Analizar de nuevo",
    "Clear Findings": "Limpiar hallazgos",
    "Separate by Material": "Separar por material",
    "Extract a closed piece per material slot and keep a solid remainder":
        "Extrae una pieza cerrada por ranura de material y conserva un cuerpo sólido",
    "Retained material slot": "Ranura del cuerpo principal",
    "Connect to the main body": "Conectar al cuerpo principal",
    "Fit each extracted piece to the retained material using the region connector settings":
        "Conecta cada pieza extraída al cuerpo principal con los ajustes de conector de la región",
    "Choose a region connector before separating by material.":
        "Elige un conector para la región antes de separar por material.",
    "Assign faces to the retained slot and at least one other material slot.":
        "Asigna caras tanto a la ranura principal como a otra ranura de material.",
    "A material cut consumed all remaining geometry or produced no piece.":
        "Un corte consumió toda la geometría restante o no produjo una pieza.",
    "Slot {number}": "Ranura {number}",
    "Created {count} material pieces.": "Se crearon {count} piezas por material.",
    "Symmetric Cuts": "Cortes simétricos",
    "Reflect a straight cut across a symmetry plane": "Refleja un corte recto con un plano de simetría",
    "Symmetry axis": "Eje de simetría",
    "Center shift (mm)": "Desplazamiento del centro (mm)",
    "Shift the symmetry plane from the model center":
        "Desplaza el plano de simetría respecto al centro del modelo",
    "Second cut shift (mm)": "Desplazamiento del segundo corte (mm)",
    "Shift the reflected cut along its own normal": "Desplaza el corte reflejado sobre su normal",
    "Show both planes": "Mostrar ambos planos",
    "Second cut rotation": "Rotación del segundo corte",
    "Rotate the reflected cut in its local axes": "Gira el corte reflejado sobre sus ejes locales",
    "Check the symmetry center, shift and rotation.": "Revisa el centro, el desplazamiento y la rotación de simetría.",
    "Move the cut to one side of the symmetry center.": "Mueve el corte a un lado del centro de simetría.",
    "The two cuts cross within the model. Adjust the angle or offset.":
        "Los dos cortes se cruzan dentro del modelo. Ajusta el ángulo o el desplazamiento.",
    "The mirrored connector does not fit at its reflected position.":
        "El conector reflejado no cabe en su posición.",
    "The requested connector positions do not fit.": "Los conectores no caben en las posiciones elegidas.",
    "Separate Base": "Separar base",
    "Find rising contacts and cut the figure from its base": "Detecta apoyos y separa la figura de su base",
    "Search height (mm)": "Altura de búsqueda (mm)",
    "Height above the model bottom to search, or zero for automatic":
        "Altura desde la parte inferior del modelo, o cero para detección automática",
    "Min. contact (mm²)": "Contacto mín. (mm²)",
    "Contact margin (mm)": "Margen del contacto (mm)",
    "Contact shift (mm)": "Ajuste vertical (mm)",
    "Connect the contacts": "Añadir conectores",
    "Add connector": "Añadir conector",
    "Pin diameter (mm)": "Diámetro del pin (mm)",
    "Enter zero to keep the common diameter": "Usa cero para conservar el diámetro general",
    "Find Base Contacts": "Detectar apoyos",
    "Detect and highlight where the figure rises out of its base": "Detecta y resalta los apoyos de la figura",
    "Highlight contacts": "Resaltar apoyos",
    "Contact at {height:.2f} mm": "Apoyo a {height:.2f} mm",
    "Found {count} base contact(s).": "Se detectaron {count} apoyos.",
    "Check the base scan height, minimum contact area and margin.":
        "Revisa la altura de búsqueda, el área mínima y el margen.",
    "Set the base search height below the top of the model.":
        "Define una altura de búsqueda por debajo de la parte superior del modelo.",
    "No closed base contacts were found. Adjust the search height.":
        "No se detectaron apoyos cerrados. Ajusta la altura de búsqueda.",
    "A contact is above the base search height after adjustment.":
        "Tras el ajuste, un apoyo quedó por encima de la altura de búsqueda.",
    "A contact is too irregular for a straight pin. Disable connectors.":
        "Un apoyo es demasiado irregular para un pin recto. Desactiva su conector.",
    "A base contact does not have room for a connector.": "Un apoyo no tiene espacio para un conector.",
    "Assembly": "Ensamblaje",
    "Use Selected Project": "Usar proyecto de la pieza",
    "Show the project that owns the selected generated piece":
        "Muestra el proyecto al que pertenece la pieza generada",
    "Select a generated piece to open its assembly.": "Selecciona una pieza generada.",
    "Select Piece": "Seleccionar pieza",
    "Focus Piece": "Encuadrar pieza",
    "Open the 3D Viewport to focus the piece.": "Abre la Vista 3D para encuadrar la pieza.",
    "Toggle Piece Visibility": "Cambiar visibilidad de la pieza",
    "Isolate in Project": "Aislar en el proyecto",
    "Show Project Pieces": "Mostrar piezas del proyecto",
    "Measure Piece": "Medir pieza",
    "Duplicate Piece": "Duplicar pieza",
    "Delete Generated Piece": "Eliminar pieza generada",
    "Back to Assembly": "Volver al ensamblaje",
    "This piece is shared with another scene or library.": "La pieza pertenece a otra escena o biblioteca.",
    "Check Assembly": "Revisar ensamblaje",
    "Check whether project pieces overlap in the assembled position":
        "Comprueba si las piezas del proyecto se traslapan en la posición de ensamblaje",
    "{count} overlap(s). {first} and {second}: {volume:.3f} mm³":
        "{count} traslape(s). {first} y {second}: {volume:.3f} mm³",
    "No volume overlaps at the assembled position.": "No hay traslapes de volumen en el ensamblaje.",
    "Check Insertion Path": "Revisar recorrido de inserción",
    "Test the selected piece for collisions along a straight insertion path":
        "Comprueba si la pieza elegida choca durante una inserción recta",
    "Start from": "Dirección de partida",
    "Assembly Direction": "Dirección del ensamblaje",
    "Use the piece's suggested separation direction": "Usa la dirección de separación sugerida",
    "Travel distance (mm)": "Recorrido (mm)",
    "Choose a valid insertion direction and travel distance.":
        "Elige una dirección y una distancia de recorrido válidas.",
    "Blocked by {name} at {distance:.2f} mm.": "Bloqueo con {name} a {distance:.2f} mm.",
    "No overlap found along the insertion path.": "No se detectaron traslapes durante la inserción.",
    "Piece settings": "Ajustes de pieza",
    "Preview color": "Color de vista previa",
    "Explosion (mm)": "Separación visual (mm)",
    "Move preview geometry away from the assembly": "Separa la vista previa del ensamblaje",
    "{name} · bounds": "{name} · caja envolvente",
    "Choose a material slot on the input mesh.": "Elige una ranura de material de la malla.",
    "Choose a Boolean attribute on the face domain.": "Elige un atributo booleano de caras.",
    "Choose a vertex group on the input object.": "Elige un grupo de vértices del objeto.",
    "Choose a color attribute on the input mesh.": "Elige un atributo de color de la malla.",
    "Choose a region source.": "Elige el origen de la región.",
    "Choose a positive extraction depth.": "Elige una profundidad de extracción positiva.",
    "The region has no matching faces.": "La región no tiene caras que coincidan.",
    "Choose a region smaller than the entire model.": "Elige una región menor que todo el modelo.",
    "The region has a sharp fold. Select a smaller patch.":
        "La región tiene un pliegue pronunciado. Selecciona una zona más pequeña.",
    "The region cutter folds into itself. Reduce the depth or change the region.":
        "El cortador se cruza consigo mismo. Reduce la profundidad o cambia la región.",
    "Printer": "Impresora",
    "Profile settings": "Ajustes del perfil",
    "Manufacturer": "Fabricante",
    "Model": "Modelo",
    "Technology": "Tecnología",
    "Resin": "Resina",
    "Filament printing": "Impresión con filamento",
    "Photopolymer resin printing": "Impresión con resina fotopolimérica",
    "Build volume (mm)": "Volumen (mm)",
    "Margin per side (mm)": "Margen por lado (mm)",
    "Material": "Material",
    "Compensation (%)": "Compensación (%)",
    "Density (g/cm³)": "Densidad (g/cm³)",
    "Price per kg": "Precio por kg",
    "Show print volume": "Mostrar volumen de impresión",
    "Add Printer": "Añadir impresora",
    "Add an editable profile from a factory preset or start from scratch":
        "Añade un perfil editable desde un modelo predefinido o desde cero",
    "Custom Printer": "Impresora personalizada",
    "Duplicate Printer": "Duplicar impresora",
    "Remove Printer": "Quitar impresora",
    "Use Profile Tolerances": "Usar holguras del perfil",
    "Import Printer Profile": "Importar perfil de impresora",
    "Export Printer Profile": "Exportar perfil de impresora",
    "The printer profile has an invalid name, material or technology.":
        "El nombre, material o tecnología del perfil es inválido.",
    "Check the printer dimensions, margins and material settings.":
        "Revisa las medidas, los márgenes y el material de la impresora.",
    "The printer profile file is too large.": "El archivo de perfil de impresora es demasiado grande.",
    "This printer profile schema is unsupported.": "El formato del perfil de impresora es incompatible.",
    "The printer profile JSON is invalid.": "El JSON del perfil de impresora es inválido.",
    "Choose a new file name for the printer profile.":
        "Elige un nombre de archivo nuevo para el perfil.",
    "Exceeds {axes}": "Supera {axes}",
    "Try axis order {axes}": "Prueba el orden de ejes {axes}",
    "Fits within the print volume": "Cabe en el volumen de impresión",
    "Calibrate Connectors": "Calibrar conectores",
    "Make a reusable test pin and labeled sockets with different clearances":
        "Genera un pin reutilizable y cavidades marcadas con distintas holguras",
    "Start clearance (mm)": "Holgura inicial (mm)",
    "End clearance (mm)": "Holgura final (mm)",
    "Spacing": "Muestreo",
    "Increment": "Incremento",
    "Sample count": "Cantidad de muestras",
    "Increment (mm)": "Incremento (mm)",
    "Engrave clearances": "Grabar holguras",
    "{count} sockets and one pin": "{count} cavidades y un pin",
    "Calibration clearances must be between 0 and 10 mm.":
        "Las holguras de calibración deben estar entre 0 y 10 mm.",
    "The end clearance must be at least the start clearance.":
        "La holgura final debe ser igual o mayor que la inicial.",
    "Set a positive clearance increment of at least 0.001 mm.":
        "Usa un incremento de holgura de al menos 0.001 mm.",
    "Choose up to 40 calibration samples.": "Elige hasta 40 muestras de calibración.",
    "Increase the clearance range or reduce the sample count.":
        "Amplía el rango de holguras o reduce la cantidad de muestras.",
    "The calibration coupon could not be built as a closed solid.":
        "No se pudo generar la muestra de calibración como un sólido cerrado.",
    "Test pin": "Pin de prueba",
    "Socket {clearance:.3f} mm": "Cavidad de {clearance:.3f} mm",
    "Created a calibration pin and {count} sockets.":
        "Se creó un pin de calibración y {count} cavidades.",
    "Save Clearance to Profile": "Guardar holgura en el perfil",
    "Set the selected printer profile's clearance to the active socket value":
        "Guarda el valor de la cavidad activa como holgura del perfil seleccionado",
    "Saved {clearance:.3f} mm per side to the printer profile.":
        "Se guardaron {clearance:.3f} mm por lado en el perfil de impresora.",
    "Split to Fit": "Dividir para que quepa",
    "Use straight cuts to fit every piece within the printer's useful dimensions":
        "Aplica cortes rectos para que cada pieza quepa en el volumen útil de impresión",
    "Split with straight cuts and no connectors.": "Aplica cortes rectos sin conectores.",
    "Piece limit": "Límite de piezas",
    "The split exceeds the configured piece limit.": "La división supera el límite de piezas elegido.",
    "The cut did not reduce the model size.": "El corte no redujo el tamaño del modelo.",
    "The model already fits in this orientation.": "El modelo ya cabe con esta orientación.",
    "Created {count} pieces that fit the profile.": "Se crearon {count} piezas que caben en el perfil.",
    "Click the first point of the cut · Esc to cancel":
        "Haz clic en el primer punto del corte · Esc para cancelar",
    "Click the second point of the cut · Esc to cancel":
        "Haz clic en el segundo punto del corte · Esc para cancelar",
    "Move the second point farther from the first.":
        "Separa más el segundo punto del primero.",
    "Reference axis": "Eje de referencia",
    "Target size (mm)": "Medida final (mm)",
    "Create scaled copy": "Crear copia a escala",
    "Resize a new copy to the target dimension and keep the input model":
        "Ajusta una copia a la medida indicada y conserva el modelo de entrada",
    "Without scene units, 1 BU = 1 mm.": "Sin unidades de escena, 1 BU = 1 mm.",
    "Split": "Dividir",
    "Connect": "Conectar",
    "Validate": "Validar",
    "Export": "Exportar",
    "Split Model": "Dividir modelo",
    "Split the active model into two pieces and keep the input mesh":
        "Divide el modelo activo en dos piezas y conserva la malla de entrada",
    "Offset (mm)": "Desplazamiento (mm)",
    "Distance from the center along the cut axis": "Distancia desde el centro sobre el eje de corte",
    "Show plane": "Mostrar plano",
    "Move Cut Plane": "Mover plano de corte",
    "Show drag handle": "Mostrar control de arrastre",
    "Move the cutting plane along its normal in the viewport":
        "Mueve el plano de corte sobre su normal desde la Vista 3D",
    "Kerf (mm)": "Separación (mm)",
    "Physical gap removed between the pieces": "Espacio físico que se retira entre las piezas",
    "Connector": "Conector",
    "None": "Ninguno",
    "Cylindrical": "Cilíndrico",
    "Hexagonal": "Hexagonal",
    "Create two pieces without a connector": "Crea dos piezas sin un conector",
    "Add a round pin and matching socket": "Añade un pin redondo y su cavidad",
    "Add a hexagonal pin and matching socket": "Añade un pin hexagonal y su cavidad",
    "Cut settings": "Ajustes de corte",
    "Hide input after split": "Ocultar entrada al dividir",
    "Diameter (mm)": "Diámetro (mm)",
    "Pin diameter measured across opposite vertices": "Diámetro del pin entre vértices opuestos",
    "Insertion (mm)": "Inserción (mm)",
    "Length of the pin inside the matching piece": "Longitud del pin dentro de la pieza receptora",
    "Per side (mm)": "Por lado (mm)",
    "Clearance from each side of the pin to the socket wall":
        "Holgura entre cada lado del pin y la pared de la cavidad",
    "Axial (mm)": "Axial (mm)",
    "Additional clearance at the bottom of the socket": "Holgura adicional al fondo de la cavidad",
    "Min. wall (mm)": "Pared mín. (mm)",
    "Minimum material around the socket and pin root":
        "Material mínimo en torno a la cavidad y la raíz del pin",
    "Check Mesh": "Revisar malla",
    "Check closure, face orientation and enclosed volume":
        "Comprueba el cierre, la orientación de caras y el volumen interior",
    "Export Pieces": "Exportar piezas",
    "Export generated pieces in STL, OBJ, FBX or 3MF": "Exporta piezas en STL, OBJ, FBX o 3MF",
    "One 3MF for all pieces": "Un 3MF para todas las piezas",
    "Keep multiple separate objects in one 3MF": "Guarda varios objetos separados en un solo 3MF",
    "Format": "Formato",
    "Choose STL, OBJ, FBX or 3MF for export.": "Elige STL, OBJ, FBX o 3MF para exportar.",
    "Enable Blender's FBX add-on to export FBX.": "Activa el complemento FBX de Blender para exportar.",
    "Blender could not export the FBX.": "Blender no pudo exportar el FBX.",
    "Pieces": "Piezas",
    "Selected": "Seleccionadas",
    "All": "Todas",
    "Export selected generated pieces": "Exporta las piezas generadas y seleccionadas",
    "Export all current TNTMesh pieces in this view layer":
        "Exporta todas las piezas vigentes de TNTMesh en esta capa de vista",
    "Blender could not import the STL.": "Blender no pudo importar el STL.",
    "The STL has no faces or contains invalid coordinates.":
        "El STL no tiene caras o contiene coordenadas inválidas.",
    "The operation failed. Details are available in Blender's console.":
        "La operación falló. Consulta los detalles en la consola de Blender.",
    "The selected axis has no measurable size.": "El eje seleccionado no tiene una medida válida.",
    "Created {count} pieces. The input mesh was kept.":
        "Se crearon {count} piezas. Se conservó la malla de entrada.",
    "Closed mesh · {volume:.2f} mm³ · {shells} shell(s)":
        "Malla cerrada · {volume:.2f} mm³ · {shells} superficie(s)",
    "Select generated pieces to export.": "Selecciona piezas generadas para exportarlas.",
    "Choose an existing destination folder.": "Elige una carpeta de destino que ya exista.",
    "Exported {count} {format} file(s).": "Se exportaron {count} archivo(s) {format}.",
    "The mesh is empty or has invalid coordinates.": "La malla está vacía o tiene coordenadas inválidas.",
    "The mesh has open edges or inconsistent face orientation.":
        "La malla tiene bordes abiertos o caras con una orientación inconsistente.",
    "The mesh has non-manifold vertices.": "La malla tiene vértices con topología no válida.",
    "The mesh has degenerate faces.": "La malla tiene caras degeneradas.",
    "The mesh has no positive enclosed volume.": "La malla no encierra un volumen positivo.",
    "The object transform is singular.": "La transformación del objeto no es invertible.",
    "Check the connector dimensions and clearances.": "Revisa las dimensiones y holguras del conector.",
    "No safe connector position. Reduce its size or move the cut.":
        "No se encontró una posición segura. Reduce el tamaño del conector o mueve el corte.",
    "Not enough safe positions. Reduce the connector count or size.":
        "Faltan posiciones seguras. Reduce la cantidad o el tamaño de los conectores.",
    "Connector count": "Cantidad de conectores",
    "Separate pins": "Pasadores independientes",
    "Cut two sockets and generate removable pins": "Recorta dos cavidades y genera pasadores sueltos",
    "Pin {number}": "Pasador {number}",
    "Custom Mesh": "Malla personalizada",
    "Use a shaped pin mesh and a matching socket cutter":
        "Usa una malla como pin y un cortador a juego para su cavidad",
    "Pin template": "Plantilla de pin",
    "Socket template": "Plantilla de cavidad",
    "Connector templates must be meshes in this view layer.":
        "Las plantillas de conector deben ser mallas de esta capa de vista.",
    "Each connector template must be one closed shell.":
        "Cada plantilla de conector debe ser una sola superficie cerrada.",
    "Choose separate pin and socket templates.": "Elige plantillas distintas para el pin y la cavidad.",
    "Custom templates require a cut with zero kerf.":
        "Las plantillas personalizadas requieren un corte sin separación.",
    "Both templates must cross the mating plane at their origin.":
        "Ambas plantillas deben cruzar el plano de unión en su origen.",
    "The custom pin protrudes outside its socket template.":
        "El pin personalizado sobresale de su plantilla de cavidad.",
    "Use connector templates separate from the input model.":
        "Usa plantillas distintas del modelo de entrada.",
    "The connector could not be joined or the socket could not be cut.":
        "No se pudo unir el pin o recortar la cavidad.",
    "Check the cut offset and separation.": "Revisa el desplazamiento y la separación del corte.",
    "Move the cut inside the model or reduce the separation.":
        "Mueve el corte hacia el interior del modelo o reduce la separación.",
    "The split did not preserve the expected volume.": "El corte no conservó el volumen esperado.",
    "Mode": "Modo",
    "Easy": "Fácil",
    "Draft": "Borrador",
    "Cut the selected model now": "Aplica el corte al modelo seleccionado",
    "Plan multiple cuts before generating pieces": "Planea varios cortes antes de generar piezas",
    "New Draft": "Nuevo borrador",
    "Create a non-destructive plan for the active mesh": "Crea un plan de corte para la malla activa",
    "Select a mesh and create a draft.": "Selecciona una malla y crea un borrador.",
    "Run this cut": "Aplicar este corte",
    "Add Cut": "Añadir corte",
    "Duplicate Cut": "Duplicar corte",
    "Remove Cut": "Quitar corte",
    "Move Cut Up": "Subir corte",
    "Move Cut Down": "Bajar corte",
    "Source model": "Modelo original",
    "Missing target": "Pieza faltante",
    "Cut “{name}” · {reason}": "Corte «{name}» · {reason}",
    "Cut {number}": "Corte {number}",
    "{name} · Copy": "{name} · Copia",
    "The draft contains invalid cut identifiers.": "El borrador contiene identificadores inválidos.",
    "Choose an available input piece from an earlier cut.":
        "Elige una pieza disponible de un corte anterior.",
    "Choose an available input piece.": "Elige una pieza disponible.",
    "Enable at least one cut in the draft.": "Activa al menos un corte del borrador.",
    "This draft uses an unsupported project schema.": "El formato de este borrador es incompatible.",
    "The draft source is missing from this view layer.":
        "El modelo original del borrador no está en esta capa de vista.",
    "Select the original model for a new draft.": "Selecciona el modelo original para un nuevo borrador.",
    "Input Piece": "Pieza de entrada",
    "Choose Input Piece": "Elegir pieza de entrada",
    "Build Draft": "Generar piezas",
    "Apply enabled cuts and replace this draft's previously generated pieces":
        "Aplica los cortes activos y reemplaza las piezas generadas por este borrador",
    "Built {count} draft pieces.": "Se generaron {count} piezas del borrador.",
}
CATALOG = {
    locale: {
        (context, source): target
        for context in ("*", bpy.app.translations.contexts.operator_default)
        for source, target in SPANISH.items()
    }
    for locale in ("es", "es_MX")
}


def register() -> None:
    bpy.app.translations.register(__package__, CATALOG)


def unregister() -> None:
    bpy.app.translations.unregister(__package__)


def tr(message: str) -> str:
    return bpy.app.translations.pgettext_iface(message)
