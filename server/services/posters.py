"""Poster 应用服务——统一 PosterDocument 业务规则与 Repository CAS + SongSource 解析。

P1 R1a.1：CRUD + 已保存文档列表 + SongSource → song_id 解析（resolve）。
不持有 SongService 之外的状态；解析时通过 song_repository 取得 active 列表。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Mapping

from core.data.posters import (
    CURRENT_SCHEMA_VERSION,
    PosterDocument,
    SOURCE_ALL_ACTIVE,
    SOURCE_ARTIST,
    SongSource,
    new_poster_id,
    resolve_all_active,
    resolve_artist_source,
)
from server.ports.repositories import MISSING_REVISION


class PosterServiceError(Exception):
    """可由 HTTP 适配层稳定映射的 Poster 业务错误。"""


class PosterValidationFailed(PosterServiceError):
    pass


class PosterNotFound(PosterServiceError):
    pass


@dataclass(frozen=True)
class PosterSaveResult:
    poster: PosterDocument
    revision: str


@dataclass(frozen=True)
class PosterDeleteResult:
    poster_id: str
    existed: bool


@dataclass(frozen=True)
class PosterResolveResult:
    """解析 SongSource 后的不可变歌曲快照列表。

    songs: List[SongSnapshot] —— SongService/RenderDocument 共享使用
    missing_song_ids: List[str] —— selected_song_ids 中不存在于 active 库的 song_id 列表
    """
    songs: tuple  # tuple of SongSnapshot dataclasses（避免循环依赖）
    missing_song_ids: tuple


@dataclass(frozen=True)
class SongSnapshot:
    """从 SongService 解析出来的不可变快照，供渲染层共享。"""
    id: str
    title: str
    artists: tuple
    section: int = 0


class PosterApplicationService:
    """PosterDocument 的应用服务边界。

    Args:
        poster_repository: PosterRepository port
        song_repository: 用于读取 active 歌曲以解析 SongSource（可选；
            resolve 在未传入时拒绝——保持依赖显式）
    """

    def __init__(self, *, poster_repository, song_repository=None):
        self._posters = poster_repository
        self._songs = song_repository

    # ── 列表与读取 ──

    def list(self):
        return self._posters.list().value

    def get(self, poster_id: str) -> PosterDocument:
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        return snapshot.value

    def get_revision(self, poster_id: str) -> str:
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        return snapshot.revision

    # ── 写入（身份、创建时间由服务端持有，完整更新不能重写） ──

    def save(self, payload: Mapping[str, Any]) -> PosterSaveResult:
        """保存或更新 Poster。

        新建：保留 created_at，写入 manifest
        更新：created_at 不被覆盖；expected_revision 来自当前仓储快照
        字段规范化：name strip、schema 必须为 v1、P1 R1a 范围保护 grid-wrap
        """
        # 兼容载荷：from_dict 的硬字段缺失直接抛；这里把字典补到 from_dict 能解析的最小集，
        # 然后再用 from_dict 构造。
        payload = dict(payload)
        if not str(payload.get("id", "")).strip():
            payload["id"] = new_poster_id()
        # 自动补齐关键缺省
        payload.setdefault("name", "未命名海报")
        payload.setdefault("song_source", {"type": SOURCE_ALL_ACTIVE, "artists": []})
        payload.setdefault("selected_song_ids", [])
        payload.setdefault("grouping", "none")
        payload.setdefault("sorting", "manual")
        payload.setdefault("layout_id", "grid-wrap")
        payload.setdefault("theme_id", "海洋柔光")
        payload.setdefault("canvas_id", "9:20")
        payload.setdefault("page_policy", {"mode": "legacy-fixed-2"})
        payload.setdefault("parameters", {})
        payload.setdefault("export_settings", {})
        try:
            poster = PosterDocument.from_dict(payload)
        except (TypeError, ValueError, AttributeError) as error:
            raise PosterValidationFailed(f"海报字段不合法：{error}") from error
        poster.name = str(poster.name or "").strip()
        if not poster.name:
            raise PosterValidationFailed("海报名称不能为空")
        if poster.schema_version != CURRENT_SCHEMA_VERSION:
            raise PosterValidationFailed(
                f"Poster 必须使用 Schema v{CURRENT_SCHEMA_VERSION}（当前：v{poster.schema_version}）"
            )
        try:
            poster.validate()
        except ValueError as error:
            raise PosterValidationFailed(str(error)) from error

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        current = self._posters.get(poster.id)
        if current is None:
            poster.created_at = now
            expected_revision = MISSING_REVISION
        else:
            poster.created_at = current.value.created_at
            expected_revision = current.revision

        # updated_at 总在 save 时刷新，便于 UI 排序
        poster.updated_at = now
        try:
            saved = self._posters.save(poster, expected_revision=expected_revision)
        except ValueError as error:
            raise PosterValidationFailed(str(error)) from error
        return PosterSaveResult(saved.value, saved.revision)

    # ── 删除 ──

    def delete(self, poster_id: str) -> PosterDeleteResult:
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        deleted = self._posters.delete(poster_id, expected_revision=snapshot.revision)
        return PosterDeleteResult(poster_id, deleted)

    # ── SongSource 解析 ──

    def resolve(self, poster_id: str) -> PosterResolveResult:
        """按已保存的 PosterDocument 解析 SongSource，返回不可变 SongSnapshot 列表。

        这是 RenderDocument（预览/导出）共享的同一解析路径。
        selected_song_ids 中含有不在 active 库里的 song_id → 列入 missing_song_ids，
        由调用方决定降级策略（前端显示警告 / 渲染前移除）。
        """
        poster = self.get(poster_id)
        if self._songs is None:
            raise PosterServiceError("SongRepository 未注入，无法解析 SongSource")
        active_songs = self._songs.load().value.active()
        resolved_ids = self._resolve_source(poster.song_source, active_songs)
        # 与持久化的 selected_song_ids 求并集去重保序：
        # - 当 SongSource 解析为空（如 SOURCE_ARTIST 暂时没匹配），
        #   仍返回 selected_song_ids（手动兜底，便于渐进入口）
        resolved_set = set(resolved_ids)
        merged = list(resolved_ids)
        for sid in poster.selected_song_ids:
            if sid not in resolved_set:
                merged.append(sid)
                resolved_set.add(sid)
        # 转成快照；同时收集 missing
        snapshots: List[SongSnapshot] = []
        active_by_id = {s.id: s for s in active_songs}
        missing: List[str] = []
        for sid in merged:
            song = active_by_id.get(sid)
            if song is None:
                missing.append(sid)
                continue
            snapshots.append(
                SongSnapshot(
                    id=song.id,
                    title=str(getattr(song, "title", "")),
                    artists=tuple(getattr(song, "artists", []) or []),
                    section=int(getattr(song, "section", 0) or 0),
                )
            )
        return PosterResolveResult(tuple(snapshots), tuple(missing))

    def _resolve_source(self, source: SongSource, active_songs) -> List[str]:
        """按 SongSource.type 解析为 song_id 列表（保序）。"""
        if source.type == SOURCE_ALL_ACTIVE:
            return resolve_all_active(active_songs)
        if source.type == SOURCE_ARTIST:
            return resolve_artist_source(list(source.artists), active_songs)
        if source.type == "manual":
            return []  # manual 模式下解析不由 source 提供；走 selected_song_ids
        raise PosterValidationFailed(f"未知 SongSource.type：{source.type!r}")
