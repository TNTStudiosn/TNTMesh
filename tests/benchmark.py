# SPDX-License-Identifier: GPL-3.0-or-later
"""Measure real Blender operations on a closed torus of a specified face count."""

import argparse
import ctypes
import importlib
import json
import os
import platform
import sys
from ctypes import wintypes
from math import cos, sin, tau
from pathlib import Path
from time import perf_counter

import bpy

GRID = {
    10_000: (100, 100),
    100_000: (400, 250),
    500_000: (1000, 500),
    1_000_000: (1250, 800),
    3_000_000: (2000, 1500),
    5_000_000: (2500, 2000),
    10_000_000: (4000, 2500),
}


def peak_bytes() -> int:
    if sys.platform != "win32":
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return peak if sys.platform == "darwin" else peak * 1024

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("page_faults", wintypes.DWORD),
            ("peak_working_set", ctypes.c_size_t),
            *[(name, ctypes.c_size_t) for name in (
                "working_set", "peak_paged_pool", "paged_pool", "peak_nonpaged_pool", "nonpaged_pool",
                "pagefile", "peak_pagefile",
            )],
        ]

    process = ctypes.windll.kernel32.GetCurrentProcess
    process.argtypes = []
    process.restype = wintypes.HANDLE
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    query.restype = wintypes.BOOL
    counters = ProcessMemoryCounters()
    counters.size = ctypes.sizeof(counters)
    if not query(process(), ctypes.byref(counters), counters.size):
        raise OSError("Could not read the Blender process working set")
    return counters.peak_working_set


def torus(faces: int) -> bpy.types.Mesh:
    rings, sides = GRID[faces]
    circle = [(cos(tau * j / sides), sin(tau * j / sides)) for j in range(sides)]
    vertices = []
    quads = []
    for i in range(rings):
        angle = tau * i / rings
        x, y = cos(angle), sin(angle)
        for j, (radius, height) in enumerate(circle):
            distance = 12 + 3 * radius
            vertices.append((x * distance, y * distance, 3 * height))
            next_i, next_j = (i + 1) % rings, (j + 1) % sides
            quads.append((i * sides + j, next_i * sides + j,
                          next_i * sides + next_j, i * sides + next_j))
    mesh = bpy.data.meshes.new("TNTMesh benchmark torus")
    mesh.from_pydata(vertices, [], quads)
    mesh.update()
    if len(mesh.polygons) != faces:
        raise RuntimeError("The benchmark mesh has the wrong face count")
    return mesh


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("faces", type=int, choices=GRID)
    parser.add_argument("operation", choices=("inspect", "diagnostics", "intersections", "split"))
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    geometry = importlib.import_module("tntmesh.geometry.mesh")
    diagnostics = importlib.import_module("tntmesh.geometry.diagnostics")
    planar = importlib.import_module("tntmesh.geometry.planar")
    model = importlib.import_module("tntmesh.model")
    mesh = torus(args.faces)
    input_peak = peak_bytes()
    started = perf_counter()
    if args.operation == "inspect":
        geometry.inspect(mesh)
    elif args.operation in {"diagnostics", "intersections"}:
        report = diagnostics.scan(mesh, 0, 0, intersections=args.operation == "intersections")
        if report.findings or report.volume_mm3 is None:
            raise RuntimeError("The benchmark torus did not pass diagnostics")
    else:
        with model.GeometryTransaction() as transaction:
            cut = planar.PlanarCut(axis="X", offset=.27)
            planar.split(bpy.context, transaction, mesh, cut)
    elapsed = perf_counter() - started
    print("TNTMESH_BENCHMARK " + json.dumps({
        "blender": bpy.app.version_string,
        "platform": platform.platform(),
        "logical_cpu_count": os.cpu_count(),
        "mesh": "torus (12 mm major radius, 3 mm minor radius)",
        "faces": args.faces,
        "operation": args.operation,
        "seconds": round(elapsed, 4),
        "input_peak_bytes": input_peak,
        "process_peak_bytes": peak_bytes(),
    }, sort_keys=True))


main()
