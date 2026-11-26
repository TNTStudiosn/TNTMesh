# SPDX-License-Identifier: GPL-3.0-or-later
from math import ceil

import bpy

from ..model import GeometryTransaction, MeshError
from ..printing import AXES, Size
from .mesh import bounds
from .planar import PlanarCut, split

FIT_EPS = .0001


def fit_grid(
    context: bpy.types.Context,
    transaction: GeometryTransaction,
    mesh: bpy.types.Mesh,
    limits: Size,
    max_pieces: int,
) -> list[bpy.types.Mesh]:
    stack = [mesh]
    finished = []
    total = 1
    while stack:
        current = stack.pop()
        lower, upper = bounds(vertex.co for vertex in current.vertices)
        size = upper - lower
        fractions = tuple(value / limit for value, limit in zip(size, limits, strict=True))
        oversized = [i for i in range(3) if size[i] > limits[i] + FIT_EPS]
        if not oversized:
            finished.append(current)
            continue
        axis = max(oversized, key=fractions.__getitem__)
        if total >= max_pieces:
            raise MeshError("The split exceeds the configured piece limit.")
        chunks = ceil(fractions[axis])
        step = size[axis] / chunks
        # Balance the hierarchy while preserving the evenly divided intervals.
        offset = step * (chunks // 2) - size[axis] / 2
        parts = split(context, transaction, current, PlanarCut(AXES[axis], offset))
        for part in parts:
            low, high = bounds(vertex.co for vertex in part.vertices)
            if high[axis] - low[axis] > size[axis] - FIT_EPS:
                raise MeshError("The cut did not reduce the model size.")
        transaction.remove_mesh(current)
        stack.extend(reversed(parts))
        total += 1
    return finished
