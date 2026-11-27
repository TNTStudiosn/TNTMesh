# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

import bpy

from . import assembly_history, guide_images
from .assembly import world_box
from .exporters import file_stem, is_loose_connector, publish_files
from .localization import tr
from .model import millimeters_per_unit

ASSEMBLED = "assembled.png"
EXPLODED = "exploded.png"


@dataclass(frozen=True)
class Piece:
    number: int
    name: str
    size: str
    loose: bool

    @property
    def label(self) -> str:
        return f"{self.number:02d}"

    @property
    def kind(self) -> str:
        return tr("Loose connector") if self.loose else tr("Body piece")


@dataclass
class Joint:
    depth: int
    branches: list[list[Piece]]
    connectors: list[Piece] = field(default_factory=list)
    magnet: assembly_history.StockMagnet | None = None
    snap_fit: bool = False

    @property
    def incomplete(self) -> bool:
        return any(not group for group in self.branches)

    def directions(self) -> list[str]:
        notes = []
        groups = [", ".join(piece.label for piece in group) for group in self.branches if group]
        if self.magnet:
            notes.append(tr("Fit {count} × {magnet} before joining. Check polarity against the mating pocket.").format(
                count=self.magnet.count, magnet=self.magnet.label(),
            ))
        if self.connectors:
            notes.append(tr("Fit loose connectors {pieces} into their matching pockets.").format(
                pieces=", ".join(piece.label for piece in self.connectors),
            ))
        if len(groups) >= 2:
            wording = ("Press {groups} together along the cut normal until the hooks seat." if self.snap_fit
                       else "Join {groups} in the assembled positions shown.")
            notes.append(tr(wording).format(groups=" / ".join(groups)))
        if self.incomplete:
            notes.append(tr("Some bodies from this cut are absent from the guide."))
        return notes


@dataclass(frozen=True)
class Guide:
    title: str
    pieces: list[Piece]
    joints: list[Joint]
    stock: list[assembly_history.StockMagnet]
    has_legacy: bool


def collect(context: bpy.types.Context, title: str, objects: list[bpy.types.Object]) -> Guide:
    depsgraph = context.evaluated_depsgraph_get()
    unit = millimeters_per_unit(context.scene)
    pieces = []
    joints: dict[str, Joint] = {}
    legacy = False
    legacy_paths = assembly_history.legacy_paths(context.scene, objects, is_loose_connector)
    for number, obj in enumerate(objects, 1):
        lower, upper = world_box(obj, depsgraph)
        size = " × ".join(f"{axis * unit:.3g}" for axis in upper - lower) + " mm"
        piece = Piece(number, obj.name, size, is_loose_connector(obj))
        pieces.append(piece)
        inherited = legacy_paths.get(obj.name, ())
        trace = inherited + assembly_history.path(obj)
        legacy |= bool(inherited) or assembly_history.GUIDE_PATH not in obj
        for depth, branch in enumerate(trace):
            joint = joints.get(branch.cut)
            if joint is None:
                joint = Joint(depth, [[] for _ in range(branch.count)])
                joints[branch.cut] = joint
            if len(joint.branches) != branch.count:
                continue
            if branch.index and not piece.loose:
                joint.branches[branch.index - 1].append(piece)
            elif not branch.index:
                joint.connectors.append(piece)
            if branch.magnet:
                joint.magnet = branch.magnet
            joint.snap_fit |= branch.snap_fit

    stock: dict[tuple[str, tuple[float, ...]], int] = {}
    ordered = sorted(joints.values(), key=lambda joint: -joint.depth)
    for joint in ordered:
        magnet = joint.magnet
        if magnet:
            key = (magnet.shape, magnet.size)
            stock[key] = stock.get(key, 0) + magnet.count
    return Guide(title, pieces, ordered, [
        assembly_history.StockMagnet(shape, size, count) for (shape, size), count in stock.items()
    ], legacy)


def views() -> tuple[tuple[str, str], ...]:
    return ((ASSEMBLED, tr("Assembled view")), (EXPLODED, tr("Exploded view")))


def piece_columns() -> tuple[str, ...]:
    return tuple(tr(label) for label in ("No.", "Piece Name", "Type", "Size"))


def stock_labels(guide: Guide) -> list[str]:
    return [f"{magnet.count} × {magnet.label()}" for magnet in guide.stock]


def step_labels(guide: Guide) -> list[str]:
    return [" ".join(joint.directions()) for joint in guide.joints if any(joint.branches)]


def legacy_notice(guide: Guide) -> str:
    return tr("Some pieces lack recorded cut history. Use the numbered views to check their fit.") if guide.has_legacy else ""


def render_markdown(guide: Guide) -> str:
    def md(value: str) -> str:
        value = escape(" ".join(value.splitlines()), quote=False)
        for character in "\\|`*_{}[]()#!":
            value = value.replace(character, "\\" + character)
        return value

    columns = " | ".join(map(md, piece_columns()))
    lines = [f"# {md(guide.title)}", ""]
    for path, caption in views():
        lines.extend((f"## {md(caption)}", "", f"![{md(caption)}]({path})", ""))
    lines.extend((f"## {md(tr('Assembly Parts'))}", "", f"| {columns} |", "| --- | --- | --- | --- |"))
    for part in guide.pieces:
        lines.append("| " + " | ".join(map(md, (part.label, part.name, part.kind, part.size))) + " |")
    lines.extend(("", f"## {md(tr('External Components'))}", ""))
    lines.extend(f"- {md(label)}" for label in stock_labels(guide))
    if not guide.stock:
        lines.append(md(tr("No external components recorded.")))
    lines.extend(("", f"## {md(tr('Suggested Assembly Order'))}", ""))
    steps = step_labels(guide)
    lines.extend(f"{index}. {md(step)}" for index, step in enumerate(steps, 1))
    if not steps:
        lines.append(md(tr("Use the assembled view to match the pieces.")))
    if notice := legacy_notice(guide):
        lines.extend(("", md(notice)))
    return "\n".join(lines) + "\n"


def render_html(guide: Guide, lang: str) -> str:
    name = escape(guide.title)
    photos = "".join(
        f'<figure><a href="{path}" aria-label="{escape(tr("Open full-size {view}").format(view=caption.lower()))}">'
        f'<img src="{path}" alt="{escape(caption)}" width="{guide_images.WIDTH}" '
        f'height="{guide_images.HEIGHT}"></a><figcaption>{escape(caption)}</figcaption></figure>'
        for path, caption in views()
    )
    headings = "".join(f'<th scope="col">{escape(label)}</th>' for label in piece_columns())
    rows = []
    for part in guide.pieces:
        rows.append(
            f'<tr><th scope="row">{part.label}</th><td>{escape(part.name)}</td>'
            f'<td>{escape(part.kind)}</td><td>{escape(part.size)}</td></tr>'
        )
    stock = "".join(f"<li>{escape(label)}</li>" for label in stock_labels(guide))
    stock = f"<ul>{stock}</ul>" if stock else f"<p>{escape(tr('No external components recorded.'))}</p>"
    steps = "".join(f"<li>{escape(step)}</li>" for step in step_labels(guide))
    steps = f"<ol>{steps}</ol>" if steps else f"<p>{escape(tr('Use the assembled view to match the pieces.'))}</p>"
    notice = legacy_notice(guide)
    notice = f'<p class="notice">{escape(notice)}</p>' if notice else ""
    return f"""<!doctype html>
<html lang="{lang}">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{name}</title>
<style>
  :root {{ color-scheme: light; --ink:#042035; --muted:#415465; --line:#c7d5dc; --accent:#4d2f98; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#eef3f5; color:var(--ink); font:1rem/1.55 "Segoe UI", sans-serif; }}
  main {{ max-width:72rem; margin:auto; padding:clamp(1rem,4vw,3rem); }}
  header {{ padding:1.3rem 0 1.5rem; border-top:.25rem solid var(--accent); }}
  h1,h2,figcaption {{ letter-spacing:-.02em; line-height:1.2; }}
  h1 {{ overflow-wrap:anywhere; font-size:clamp(2rem,5vw,3.8rem); margin:.25rem 0 0; }}
  h2 {{ font-size:1.45rem; margin:0 0 .8rem; }}
  .views {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }}
  figure {{ margin:0; background:#042035; color:white; }}
  figure a {{ display:block; }}
  figure a:focus-visible {{ outline:3px solid #00ffff; outline-offset:-5px; }}
  img {{ display:block; width:100%; height:auto; }}
  figcaption {{ padding:.8rem 1rem 1rem; font-weight:700; border-top:1px solid #315162; }}
  section {{ margin-top:2rem; border-top:1px solid var(--line); padding-top:1.2rem; }}
  table {{ width:100%; border-collapse:collapse; table-layout:fixed; }}
  th,td {{ padding:.65rem .55rem; text-align:left; vertical-align:top; overflow-wrap:anywhere; }}
  thead {{ background:#e1e9ed; }}
  th:first-child {{ width:3.7rem; white-space:nowrap; }}
  th:nth-child(3),th:nth-child(4) {{ width:24%; }}
  tbody tr {{ border-bottom:1px solid var(--line); }}
  tbody th {{ color:var(--accent); font-variant-numeric:tabular-nums; }}
  li {{ padding-bottom:.55rem; }}
  .notice {{ color:var(--muted); }}
  @media(max-width:42rem) {{ .views {{ grid-template-columns:1fr; }} th,td {{ padding:.5rem .3rem; }} }}
  @media print {{ body {{ background:white; }} main {{ padding:0; }} figure,tr,li {{ break-inside:avoid; }}
                  figure,figcaption {{ background:white; color:var(--ink); }} }}
</style>
<main>
  <header><h1>{name}</h1></header>
  <div class="views">{photos}</div>
  <section><h2>{escape(tr('Assembly Parts'))}</h2>
    <table><thead><tr>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table>
  </section>
  <section><h2>{escape(tr('External Components'))}</h2>{stock}</section>
  <section><h2>{escape(tr('Suggested Assembly Order'))}</h2>{steps}{notice}</section>
</main>
</html>
"""


def export(
    context: bpy.types.Context, objects: list[bpy.types.Object], directory: Path,
    title: str, format_id: str, distance_mm: float,
) -> Path:
    name = title.strip() or tr("TNTMesh Assembly Guide")
    folder = file_stem(name) or "TNTMesh_Assembly_Guide"
    guide = collect(context, name, objects)
    with TemporaryDirectory(prefix="tntmesh-guide-") as temporary:
        staging = Path(temporary)
        images = (staging / ASSEMBLED, staging / EXPLODED)
        guide_images.render(context, objects, images, distance_mm)
        outputs = list(images)
        if format_id in {"HTML", "ALL"}:
            path = staging / "guide.html"
            lang = "es-MX" if bpy.app.translations.locale.startswith("es") else "en"
            path.write_text(render_html(guide, lang), encoding="utf-8")
            outputs.append(path)
        if format_id in {"MARKDOWN", "ALL"}:
            path = staging / "guide.md"
            path.write_text(render_markdown(guide), encoding="utf-8")
            outputs.append(path)
        return publish_files(outputs, directory, folder)[0].parent
