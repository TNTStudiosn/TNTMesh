# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

SPANISH = {
    "Import STL": "Importar STL",
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
    "Create Repaired Copy": "Crear copia reparada",
    "Weld close vertices and optionally fill simple holes on a new copy":
        "Une vértices cercanos y permite cerrar agujeros simples en una copia nueva",
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
    "Choose two points in the viewport to orient the cut plane":
        "Elige dos puntos en la Vista 3D para orientar el plano de corte",
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
    "Write one STL, OBJ or FBX per generated piece": "Escribe un STL, OBJ o FBX por pieza generada",
    "Format": "Formato",
    "Choose STL, OBJ or FBX for export.": "Elige STL, OBJ o FBX para exportar.",
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
