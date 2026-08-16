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
    PagePolicy,
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

    def get_with_revision(self, poster_id: str) -> tuple[PosterDocument, str]:
        """读文档并返回 (poster, revision)；用于前端 CAS 自动保存。"""
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        return snapshot.value, snapshot.revision

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

    # ── R4 退出条件 #2: 手动分页 ──

    def list_pages(self, poster_id: str) -> list[dict]:
        """返回 poster.page_policy.manual_pages 列表 + 总数。

        空 list 表示「未启用手动分页」（沿用 layout.analyze 自动）。
        """
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        return list(snapshot.value.page_policy.manual_pages)

    def add_page(self, poster_id: str) -> list[dict]:
        """追加一个空白页到 manual_pages 末尾；自动切到 mode=manual。"""
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        poster = snapshot.value
        new_pages = list(poster.page_policy.manual_pages) + [{}]
        updated_policy = PagePolicy(
            mode="manual", manual_pages=new_pages,
            min_pages=poster.page_policy.min_pages,
            max_pages=poster.page_policy.max_pages,
        )
        return self._save_with_page_policy(poster, updated_policy, snapshot.revision)

    def delete_page(self, poster_id: str, index: int) -> list[dict]:
        """删除指定 index 的页。剩余 < 1 时回退到 mode=auto。"""
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        poster = snapshot.value
        if not (0 <= index < len(poster.page_policy.manual_pages)):
            raise PosterValidationFailed(
                f"页索引越界：{index}（共 {len(poster.page_policy.manual_pages)} 页）"
            )
        new_pages = [p for i, p in enumerate(poster.page_policy.manual_pages) if i != index]
        if not new_pages:
            # 没有 manual 页了，回退到 auto
            updated_policy = PagePolicy(
                mode="auto", manual_pages=[],
                min_pages=poster.page_policy.min_pages,
                max_pages=poster.page_policy.max_pages,
            )
        else:
            updated_policy = PagePolicy(
                mode="manual", manual_pages=new_pages,
                min_pages=poster.page_policy.min_pages,
                max_pages=poster.page_policy.max_pages,
            )
        return self._save_with_page_policy(poster, updated_policy, snapshot.revision)

    def reorder_pages(self, poster_id: str, new_order: list[int]) -> list[dict]:
        """按 new_order 数组重排 manual_pages。

        new_order[i] = 原 index；必须为 0..N-1 的排列。
        """
        snapshot = self._posters.get(poster_id)
        if snapshot is None:
            raise PosterNotFound(f"海报不存在：{poster_id}")
        poster = snapshot.value
        pages = poster.page_policy.manual_pages
        if sorted(new_order) != list(range(len(pages))):
            raise PosterValidationFailed(
                f"reorder 顺序必须是 0..{len(pages)-1} 的排列：{new_order}"
            )
        reordered = [pages[i] for i in new_order]
        updated_policy = PagePolicy(
            mode="manual", manual_pages=reordered,
            min_pages=poster.page_policy.min_pages,
            max_pages=poster.page_policy.max_pages,
        )
        return self._save_with_page_policy(poster, updated_policy, snapshot.revision)

    def _save_with_page_policy(self, poster, page_policy, expected_revision: str) -> list[dict]:
        """把 poster 的 page_policy 替换后保存，返回新 manual_pages 列表。"""
        poster.page_policy = page_policy
        poster.updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            saved = self._posters.save(poster, expected_revision=expected_revision)
        except ValueError as error:
            raise PosterValidationFailed(str(error)) from error
        return list(saved.value.page_policy.manual_pages)

    # ── SongSource 解析 ──

    def resolve(self, poster_id: str) -> PosterResolveResult:
        """按已保存的 PosterDocument 解析 SongSource，返回不可变 SongSnapshot 列表。

        这是 RenderDocument（预览/导出）共享的同一解析路径。
        selected_song_ids 中含有不在 active 库里的 song_id → 列入 missing_song_ids，
        由调用方决定降级策略（前端显示警告 / 渲染前移除）。

        注意：本方法不返回完整 Song 对象；构建 RenderDocument 时请用 resolve_for_render
        拿到完整 Song 列表（直接从 SongRepository 读，避免再二次构造）。
        """
        poster = self.get(poster_id)
        if self._songs is None:
            raise PosterServiceError("SongRepository 未注入，无法解析 SongSource")
        active_songs = self._songs.load().value.active()
        merged = self._resolve_merged_ids(poster, active_songs)
        active_by_id = {s.id: s for s in active_songs}
        snapshots: List[SongSnapshot] = []
        missing: List[str] = []
        for sid in merged:
            song = active_by_id.get(sid)
            if song is None:
                missing.append(sid)
                continue
            snapshots.append(self._to_song_snapshot(song))
        return PosterResolveResult(tuple(snapshots), tuple(missing))

    def resolve_for_render(self, poster_id: str):
        """返回构建 RenderDocument 所需的全部输入。

        返回 (PosterDocument, SongLibrary-like, list[str])
        其中 SongLibrary-like 有 .songs 列表 / .mastered() / .active()，可直接传给
        build_render_document。
        """
        poster = self.get(poster_id)
        if self._songs is None:
            raise PosterServiceError("SongRepository 未注入")
        snapshot = self._songs.load()
        active_songs = snapshot.value.active()
        merged = self._resolve_merged_ids(poster, active_songs)
        active_by_id = {s.id: s for s in active_songs}
        # 按 merged 顺序构造 SongLibrary，缺失的 song_id 自动降级（不渲染）
        from core.data.songs import SongLibrary
        lib = SongLibrary([s for s in [active_by_id.get(sid) for sid in merged] if s is not None])
        missing = [sid for sid in merged if sid not in active_by_id]
        return poster, snapshot.value, lib, missing

    @staticmethod
    def _to_song_snapshot(song):
        return SongSnapshot(
            id=song.id,
            title=str(getattr(song, "title", "")),
            artists=tuple(getattr(song, "artists", []) or []),
            section=int(getattr(song, "section", 0) or 0),
        )

    @staticmethod
    def _resolve_merged_ids(poster, active_songs) -> List[str]:
        """解析 SongSource 与 selected_song_ids 的并集（去重保序）。"""
        if poster.song_source.type == SOURCE_ALL_ACTIVE:
            source_ids = resolve_all_active(active_songs)
        elif poster.song_source.type == SOURCE_ARTIST:
            source_ids = resolve_artist_source(list(poster.song_source.artists), active_songs)
        elif poster.song_source.type == "manual":
            source_ids = []
        else:
            raise PosterValidationFailed(f"未知 SongSource.type：{poster.song_source.type!r}")
        seen = set(source_ids)
        merged = list(source_ids)
        for sid in poster.selected_song_ids:
            if sid not in seen:
                merged.append(sid)
                seen.add(sid)
        return merged

    def _resolve_source(self, source: SongSource, active_songs) -> List[str]:
        """按 SongSource.type 解析为 song_id 列表（保序）。"""
        if source.type == SOURCE_ALL_ACTIVE:
            return resolve_all_active(active_songs)
        if source.type == SOURCE_ARTIST:
            return resolve_artist_source(list(source.artists), active_songs)
        if source.type == "manual":
            return []  # manual 模式下解析不由 source 提供；走 selected_song_ids
        raise PosterValidationFailed(f"未知 SongSource.type：{source.type!r}")

    # ── RenderDocument 集成 (P1 R1a.4) ──

    def resolve_with_library(self, poster_id: str):
        """resolve 但额外返回 active 全曲库（capability check 用）。

        返回 (PosterDocument, list[Song], list[str])（缺失 ID 列表）。
        caller 用 active_songs 做 check_overflow；用 snapshots 做 build_render_document。
        """
        if self._songs is None:
            raise PosterServiceError("SongRepository 未注入")
        poster = self.get(poster_id)
        active_songs = self._songs.load().value.active()
        snap = self.resolve(poster_id)
        return poster, active_songs, list(snap.missing_song_ids)
