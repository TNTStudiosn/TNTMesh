# SPDX-License-Identifier: GPL-3.0-or-later
import json
from dataclasses import asdict, dataclass
from itertools import permutations
from math import isfinite
from pathlib import Path
from typing import Literal

from .model import MeshError

Size = tuple[float, float, float]
Technology = Literal["FDM", "RESIN"]
AXES = "XYZ"


@dataclass(frozen=True)
class PrinterProfile:
    manufacturer: str
    model: str
    technology: Technology
    build_mm: Size
    margin_mm: Size = (0.0, 0.0, 0.0)
    material: str = ""
    lateral_mm: float = 0.15
    axial_mm: float = 0.2
    min_wall_mm: float = 0.8
    compensation_pct: Size = (0.0, 0.0, 0.0)
    density_g_cm3: float = 1.2
    price_per_kg: float = 0.0

    @property
    def limits(self) -> Size:
        return tuple(size - 2 * margin for size, margin in zip(self.build_mm, self.margin_mm, strict=True))

    @property
    def name(self) -> str:
        return f"{self.manufacturer} {self.model}".strip()

    def validate(self) -> None:
        if (self.technology not in {"FDM", "RESIN"} or not self.model.strip()
                or any(len(text.encode()) > 128 for text in (self.manufacturer, self.model, self.material))):
            raise MeshError("The printer profile has an invalid name, material or technology.")
        values = (*self.build_mm, *self.margin_mm, *self.compensation_pct,
                  self.lateral_mm, self.axial_mm, self.min_wall_mm, self.density_g_cm3,
                  self.price_per_kg)
        if (not all(map(isfinite, values)) or min(self.limits) <= 0 or min(self.build_mm) < .01
                or min(self.margin_mm) < 0 or min(self.lateral_mm, self.axial_mm, self.price_per_kg) < 0
                or min(self.min_wall_mm, self.density_g_cm3) < .01
                or min(self.compensation_pct) < -99.99):
            raise MeshError("Check the printer dimensions, margins and material settings.")


PRESETS = {
    "MARS5": PrinterProfile("Elegoo", "Mars 5 Ultra", "RESIN", (153.36, 77.76, 165)),
    "SATURN4": PrinterProfile("Elegoo", "Saturn 4 Ultra 12K", "RESIN", (218.88, 122.88, 220)),
    "ENDER3": PrinterProfile("Creality", "Ender-3 V3 SE", "FDM", (220, 220, 250)),
    "A1": PrinterProfile("Bambu Lab", "A1", "FDM", (256, 256, 256)),
    "A1_MINI": PrinterProfile("Bambu Lab", "A1 mini", "FDM", (180, 180, 180)),
    "P1S": PrinterProfile("Bambu Lab", "P1S", "FDM", (256, 256, 256)),
    "PHOTON_MONO": PrinterProfile("Anycubic", "Photon Mono", "RESIN", (130, 80, 165)),
    "MK4S": PrinterProfile("Prusa", "MK4S", "FDM", (250, 210, 220)),
}


@dataclass(frozen=True)
class FitPreset:
    material: str
    technology: Technology
    lateral_mm: float
    axial_mm: float
    min_wall_mm: float


# Editable starting values for separately printed connectors. Calibrate the actual material and printer.
FIT_PRESETS = {
    "PLA": FitPreset("PLA", "FDM", .15, .20, 1.2),
    "PETG": FitPreset("PETG", "FDM", .20, .25, 1.2),
    "ABS": FitPreset("ABS", "FDM", .25, .30, 1.2),
    "ASA": FitPreset("ASA", "FDM", .25, .30, 1.2),
    "TPU": FitPreset("TPU", "FDM", .25, .30, 1.6),
    "NYLON": FitPreset("Nylon", "FDM", .25, .30, 1.6),
    "STANDARD": FitPreset("Standard Resin", "RESIN", .15, .20, .8),
    "ABS_LIKE": FitPreset("ABS-like Resin", "RESIN", .20, .25, 1.0),
    "FLEXIBLE": FitPreset("Flexible Resin", "RESIN", .25, .30, 1.2),
}


@dataclass(frozen=True)
class Fit:
    exceeded: tuple[str, ...]
    alternative: str | None


def fit(size: Size, profile: PrinterProfile) -> Fit:
    profile.validate()
    limits = profile.limits
    exceeded = tuple(axis for axis, part, bound in zip(AXES, size, limits, strict=True)
                     if part > bound + 0.0001)
    if not exceeded:
        return Fit((), None)
    alternative = next(
        ("".join(AXES[axis] for axis in order) for order in permutations(range(3))
         if all(size[axis] <= limit + 0.0001 for axis, limit in zip(order, limits, strict=True))),
        None,
    )
    return Fit(exceeded, alternative)


def to_json(profile: PrinterProfile) -> str:
    profile.validate()
    return json.dumps({"schema": 1, "profile": asdict(profile)}, ensure_ascii=False, indent=2) + "\n"


def from_json(path: Path) -> PrinterProfile:
    def vector(raw: object) -> Size:
        if not isinstance(raw, list) or len(raw) != 3:
            raise ValueError("Invalid three-axis dimension")
        return tuple(number(value) for value in raw)

    def number(raw: object) -> float:
        if type(raw) not in (int, float):
            raise ValueError("Invalid numeric property")
        return float(raw)

    def string(raw: object) -> str:
        if not isinstance(raw, str):
            raise ValueError("Invalid text property")
        return raw.strip()

    try:
        with path.open("r", encoding="utf-8") as stream:
            content = stream.read(65537)
    except UnicodeError as error:
        raise MeshError("The printer profile JSON is invalid.") from error
    if len(content) > 65536:
        raise MeshError("The printer profile file is too large.")
    try:
        document = json.loads(content)
        if type(document.get("schema")) is not int or document["schema"] != 1:
            raise MeshError("This printer profile schema is unsupported.")
        raw = document["profile"]
        profile = PrinterProfile(
            string(raw["manufacturer"]), string(raw["model"]), string(raw["technology"]),
            vector(raw["build_mm"]), vector(raw["margin_mm"]), string(raw["material"]),
            number(raw["lateral_mm"]), number(raw["axial_mm"]), number(raw["min_wall_mm"]),
            vector(raw["compensation_pct"]), number(raw["density_g_cm3"]), number(raw["price_per_kg"]),
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise MeshError("The printer profile JSON is invalid.") from error
    profile.validate()
    return profile
