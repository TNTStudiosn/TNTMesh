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
    "Axis": "Eje",
    "World axis perpendicular to the cutting plane": "Eje global perpendicular al plano de corte",
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
    "Export STL Pieces": "Exportar piezas STL",
    "Write one validated, millimeter-based STL per generated piece":
        "Escribe un STL validado en milímetros por pieza generada",
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
    "Created two pieces. The input mesh was kept.": "Se crearon dos piezas. Se conservó la malla de entrada.",
    "Closed mesh · {volume:.2f} mm³ · {shells} shell(s)":
        "Malla cerrada · {volume:.2f} mm³ · {shells} superficie(s)",
    "Select generated pieces to export.": "Selecciona piezas generadas para exportarlas.",
    "Choose an existing destination folder.": "Elige una carpeta de destino que ya exista.",
    "Exported {count} STL file(s).": "Se exportaron {count} archivo(s) STL.",
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
    "The connector could not be joined or the socket could not be cut.":
        "No se pudo unir el pin o recortar la cavidad.",
    "Check the cut offset and separation.": "Revisa el desplazamiento y la separación del corte.",
    "Move the cut inside the model or reduce the separation.":
        "Mueve el corte hacia el interior del modelo o reduce la separación.",
    "The split did not preserve the expected volume.": "El corte no conservó el volumen esperado.",
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
