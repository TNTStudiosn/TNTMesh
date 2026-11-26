# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterable
from typing import BinaryIO
from xml.sax.saxutils import quoteattr
from zipfile import ZIP_DEFLATED, ZipFile

import bpy

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
MODEL_PATH = "3D/3dmodel.model"
_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
_TYPES = _DECLARATION + (
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
    '</Types>'
)
_RELATIONSHIPS = _DECLARATION + (
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Target="/{MODEL_PATH}" Id="rel0" '
    'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
    '</Relationships>'
)


def write_3mf(parts: Iterable[tuple[str, bpy.types.Mesh]], output: BinaryIO) -> None:
    with ZipFile(output, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _TYPES)
        archive.writestr("_rels/.rels", _RELATIONSHIPS)
        with archive.open(MODEL_PATH, "w") as xml:
            xml.write((_DECLARATION + f'<model xmlns="{CORE}" unit="millimeter" '
                       'xml:lang="en-US"><resources>\n').encode())

            count = 0
            for count, (name, mesh) in enumerate(parts, 1):
                xml.write(f'<object id="{count}" type="model" name={quoteattr(name)}>'
                          '<mesh><vertices>\n'.encode())
                for vertex in mesh.vertices:
                    x, y, z = vertex.co
                    xml.write(f'<vertex x="{x:.9g}" y="{y:.9g}" z="{z:.9g}"/>\n'.encode("ascii"))
                xml.write(b"</vertices><triangles>\n")
                mesh.calc_loop_triangles()
                for triangle in mesh.loop_triangles:
                    a, b, c = triangle.vertices
                    xml.write(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>\n'.encode("ascii"))
                xml.write(b"</triangles></mesh></object>\n")
            xml.write(b"</resources><build>\n")
            for index in range(1, count + 1):
                xml.write(f'<item objectid="{index}"/>\n'.encode("ascii"))
            xml.write(b"</build></model>\n")
