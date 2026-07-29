"""深度不可变的渲染文档及 grid-wrap 兼容适配器。"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any

from core.data.songs import Song, SongLibrary
from core.engine import render_page
from core.layouts import get_layout
from core.spec import CanvasSpec
from core.style import Style
from core.themes.model import Theme


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return FrozenMapping((str(key), freeze(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(freeze(item) for item in value)
    return value


class FrozenMapping(Mapping[str, Any]):
    """保持插入顺序且递归冻结值的只读映射。"""

    __slots__ = ("_items", "_lookup")

    def __init__(self, items=()):
        self._items = tuple(items)
        self._lookup = MappingProxyType(dict(self._items))

    def __getitem__(self, key: str) -> Any:
        return self._lookup[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(self._items)

    def __eq__(self, other) -> bool:
        return isinstance(other, Mapping) and dict(self.items()) == dict(other.items())


@dataclass(frozen=True)
class SongSnapshot:
    values: FrozenMapping

    @classmethod
    def from_song(cls, song: Song) -> "SongSnapshot":
        return cls(freeze(asdict(song)))

    def materialize(self) -> Song:
        values = {key: list(value) if key in {"artists", "tags", "tab_files"} else value
                  for key, value in self.values.items()}
        return Song(**values)


@dataclass(frozen=True)
class ThemeSnapshot:
    name: str
    directory: str
    output_prefix: str
    backgrounds: FrozenMapping
    watermark_fix: bool
    styles: tuple[tuple[int, Style], ...]
    font: str | None
    notes: str

    @classmethod
    def from_theme(cls, theme: Theme) -> "ThemeSnapshot":
        return cls(theme.name, theme.dir, theme.output_prefix, freeze(theme.backgrounds),
                   theme.watermark_fix, tuple(sorted(theme.styles.items())),
                   theme.font, theme.notes)

    def materialize(self) -> Theme:
        return Theme(self.name, self.directory, self.output_prefix, dict(self.backgrounds),
                     self.watermark_fix, dict(self.styles), self.font, self.notes)


@dataclass(frozen=True)
class SourceRevisions:
    songs: str
    settings: str = ""
    preset: str = ""
    theme: str = ""


@dataclass(frozen=True)
class RenderDocument:
    document_id: str
    song_snapshots: tuple[SongSnapshot, ...]
    theme: ThemeSnapshot
    layout_id: str
    canvas: CanvasSpec
    page: int
    font_path: str
    title: str
    subtitle: str
    parameters: FrozenMapping
    page_policy: str
    engine_version: str
    source_revisions: SourceRevisions


def build_render_document(*, song_snapshot, theme: Theme, layout_id: str,
                          canvas: CanvasSpec, page: int, font_path: str,
                          settings_revision: str = "", preset_revision: str = "",
                          title: str = "", subtitle: str = "",
                          parameters: Mapping[str, Any] | None = None) -> RenderDocument:
    songs = tuple(SongSnapshot.from_song(song) for song in song_snapshot.value.songs)
    theme_snapshot = ThemeSnapshot.from_theme(theme)
    revisions = SourceRevisions(song_snapshot.revision, settings_revision,
                                preset_revision, _theme_revision(theme_snapshot))
    identity = {
        "songs": [dict(item.values) for item in songs], "theme": revisions.theme,
        "layout": layout_id, "canvas": asdict(canvas), "page": page,
        "font": font_path, "title": title, "subtitle": subtitle,
        "parameters": dict(parameters or {}), "revisions": asdict(revisions),
        "engine": "grid-wrap-compat-v1",
    }
    document_id = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    return RenderDocument(
        document_id=document_id, song_snapshots=songs, theme=theme_snapshot,
        layout_id=layout_id, canvas=canvas, page=page, font_path=str(font_path),
        title=title, subtitle=subtitle, parameters=freeze(parameters or {}),
        page_policy="fixed" if get_layout(layout_id).pages else "auto",
        engine_version="grid-wrap-compat-v1", source_revisions=revisions,
    )


def render_document(document: RenderDocument):
    library = SongLibrary([song.materialize() for song in document.song_snapshots])
    return render_page(document.theme.materialize(), get_layout(document.layout_id),
                       library, document.canvas, document.page, document.font_path)


def _theme_revision(theme: ThemeSnapshot) -> str:
    payload = {
        "name": theme.name, "dir": theme.directory, "prefix": theme.output_prefix,
        "backgrounds": dict(theme.backgrounds), "watermark_fix": theme.watermark_fix,
        "styles": [(page, asdict(style)) for page, style in theme.styles],
        "font": theme.font, "notes": theme.notes,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
