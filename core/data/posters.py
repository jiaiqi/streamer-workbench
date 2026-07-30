"""海报文档（PosterDocument）—— 可长期保存的独立作品。

P1 R1a.1 领域模型。契约详见 design/产品优化方案终版-0727/产品与技术规格-v3.md §5.1。

存储路径：data/posters/<id>/poster.json + data/posters/<id>/snapshots/ 备份。
P1 范围（P1 R1a 兼容闭环）只接受 grid-wrap + legacy-fixed-2 组合；
'auto' 与 'manual' 分页模式保留为 P2 R1b 的扩展面。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, List, Optional

# Song.id 格式（core/data/songs.py：song_<uuid hex 32>）。
SONG_ID_RE = re.compile(r"^song_[0-9a-f]{32}$")

# ── 当前 schema 版本 ──
# v1：初始版本。SongSource/Grouping/Sorting 完整字段；
#    selected_song_ids 永远使用 song_id（不可变 ID），不允许 title 主键。
CURRENT_SCHEMA_VERSION = 1


def new_poster_id() -> str:
    """生成无业务含义的 Poster ID。"""
    return f"poster_{uuid.uuid4().hex[:16]}"


def is_valid_poster_id(poster_id: str) -> bool:
    """Poster ID 必须是单个安全路径段。

    与 Preset ID 校验规则一致：拒绝 '.'/'..'、路径分隔符、控制字符、空串。
    """
    if not isinstance(poster_id, str) or not poster_id or len(poster_id) > 80:
        return False
    if poster_id != poster_id.strip() or poster_id in (".", ".."):
        return False
    if "/" in poster_id or "\\" in poster_id:
        return False
    return not any(ord(char) < 32 or ord(char) == 127 for char in poster_id)


# ── 分类与排序（v3 §5.3 口头列举，类型化） ──

GROUPING_NONE = "none"             # 不分类
GROUPING_ARTIST = "artist"         # 按歌手
GROUPING_CHARS = "chars"           # 按歌名字数区间（与 grid-wrap section 复用）
GROUPING_GENRE = "genre"           # 按歌曲类型
GROUPING_LANGUAGE = "language"     # 按语言
GROUPING_INITIAL = "initial"       # 按拼音首字母
GROUPING_STATUS = "status"         # 按掌握状态（active/draft —— draft 不上海报）
GROUPING_TAG = "tag"               # 按自定义标签
VALID_GROUPINGS = frozenset({
    GROUPING_NONE, GROUPING_ARTIST, GROUPING_CHARS, GROUPING_GENRE,
    GROUPING_LANGUAGE, GROUPING_INITIAL, GROUPING_STATUS, GROUPING_TAG,
})


SORTING_MANUAL = "manual"          # 手动顺序（按 selected_song_ids 顺序）
SORTING_TITLE = "title"            # 按歌名
SORTING_ARTIST = "artist"          # 按歌手
SORTING_UPDATED = "updated"        # 按最近更新
SORTING_REQUEST_HEAT = "request_heat"  # 按点歌热度（事件聚合）
VALID_SORTINGS = frozenset({
    SORTING_MANUAL, SORTING_TITLE, SORTING_ARTIST,
    SORTING_UPDATED, SORTING_REQUEST_HEAT,
})


# ── SongSource ──
# P1 R1a 范围只暴露三种最常用的查询源：
#   "all_active" —— 全部 status=active 歌曲
#   "manual" —— selected_song_ids 给定（调用方只填手选集合）
#   "artist" —— 指定歌手（支持多歌手，主播常合并主唱 + 合作）
# 其它（按学习状态、按最近常唱）属于 R3 学歌闭环后再扩展。

SOURCE_ALL_ACTIVE = "all_active"
SOURCE_MANUAL = "manual"
SOURCE_ARTIST = "artist"
VALID_SOURCES = frozenset({SOURCE_ALL_ACTIVE, SOURCE_MANUAL, SOURCE_ARTIST})


@dataclass
class SongSource:
    """歌曲来源描述。PostDoc 持久化字段，使用 stable JSON。"""
    type: str = SOURCE_MANUAL
    # 当 type=SOURCE_ARTIST 时：歌手名列表（精确匹配，大小写不敏感；多歌手取并集）。
    artists: List[str] = field(default_factory=list)

    def validate(self) -> None:
        if self.type not in VALID_SOURCES:
            raise ValueError(f"SongSource.type 非法：{self.type!r}")
        if self.type == SOURCE_ARTIST and not self.artists:
            raise ValueError("SongSource type='artist' 必须提供 artists 列表")

    def to_dict(self) -> dict:
        return {"type": self.type, "artists": list(self.artists)}

    @classmethod
    def from_dict(cls, d: dict) -> "SongSource":
        d = dict(d or {})
        return cls(
            type=d.get("type", SOURCE_MANUAL),
            artists=list(d.get("artists", []) or []),
        )


# ── PagePolicy（v3 §5.4 discriminated union） ──

@dataclass
class PagePolicy:
    """海报分页策略。
    
    P1 R1a 范围只允许 mode='legacy-fixed-2'，强制 grid-wrap 双页输出，
    与金标准 16/16 兼容。'auto' 与 'manual' 模式保留类型面，P2 R1b 接入。
    """
    mode: str = "legacy-fixed-2"
    min_pages: Optional[int] = None
    max_pages: Optional[int] = None
    manual_pages: List[dict] = field(default_factory=list)

    def validate(self) -> None:
        if self.mode not in ("legacy-fixed-2", "auto", "manual"):
            raise ValueError(f"PagePolicy.mode 非法：{self.mode!r}")
        if self.mode == "auto":
            if self.min_pages is not None and self.min_pages < 1:
                raise ValueError("PagePolicy.min_pages 必须 >= 1")
            if self.max_pages is not None and self.max_pages < 1:
                raise ValueError("PagePolicy.max_pages 必须 >= 1")
            if (self.min_pages is not None and self.max_pages is not None
                    and self.min_pages > self.max_pages):
                raise ValueError("PagePolicy.min_pages 不得大于 max_pages")
        if self.mode == "manual" and not self.manual_pages:
            raise ValueError("PagePolicy type='manual' 必须提供 pages 列表")


# ── ExportSettings ──

@dataclass
class ExportSettings:
    """导出参数。P1 范围：格式 + 单页/合并 + DPI。"""
    format: str = "png"                 # "png" | "jpeg"
    jpeg_quality: int = 92
    single_page: bool = False           # True 时按页拆多文件导出
    dpi: int = 144

    def validate(self) -> None:
        if self.format not in ("png", "jpeg"):
            raise ValueError(f"ExportSettings.format 非法：{self.format!r}")
        if not (1 <= self.jpeg_quality <= 100):
            raise ValueError("ExportSettings.jpeg_quality 必须在 1..100")
        if self.dpi < 72:
            raise ValueError("ExportSettings.dpi 不得低于 72")


# ── PosterDocument ──

@dataclass
class PosterDocument:
    """可长期保存的独立海报作品。

    selected_song_ids 永远是 song_id（不可变 ID）；注意：savedSongIds 字段
    对 manual SongSource 是显式覆盖；对 all_active / artist 是解析快照（持久化
    时记录当前解析结果，以便 offline 重放，无需重新查询 SongLibrary）。
    """
    schema_version: int = CURRENT_SCHEMA_VERSION
    id: str = field(default_factory=new_poster_id)
    name: str = "未命名海报"
    song_source: SongSource = field(default_factory=lambda: SongSource(type=SOURCE_MANUAL))
    selected_song_ids: List[str] = field(default_factory=list)
    grouping: str = GROUPING_NONE
    sorting: str = SORTING_MANUAL
    layout_id: str = "grid-wrap"
    theme_id: str = "海洋柔光"            # 默认与金标准首选一致
    canvas_id: str = "9:20"               # 9:20 全屏（与金标准对齐）
    page_policy: PagePolicy = field(default_factory=PagePolicy)
    parameters: dict = field(default_factory=dict)
    export_settings: ExportSettings = field(default_factory=ExportSettings)
    created_at: str = ""
    updated_at: str = ""
    optional_session_ref: Optional[str] = None  # 仅引用，不参与生命周期

    @staticmethod
    def default(name: str = "未命名海报") -> "PosterDocument":
        now = datetime.now().isoformat(timespec="seconds")
        return PosterDocument(
            name=name,
            created_at=now,
            updated_at=now,
        )

    # ── 持久层校验 ──

    def validate(self) -> None:
        """保存前全量校验：拒绝带病持久化（schema/身份/SongSource 完整性）。

        抛出 ValueError 时调用方必须立即丢弃，绝不写入仓储。
        """
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise ValueError("schema_version 必须为 >= 1 的整数")
        if not is_valid_poster_id(self.id):
            raise ValueError(f"非法 poster_id：{self.id!r}")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name 必须为非空字符串")
        self.song_source.validate()
        if self.grouping not in VALID_GROUPINGS:
            raise ValueError(f"grouping 非法：{self.grouping!r}")
        if self.sorting not in VALID_SORTINGS:
            raise ValueError(f"sorting 非法：{self.sorting!r}")
        self.page_policy.validate()
        self.export_settings.validate()
        # selected_song_ids 必须全部为合法 song_id（去重保序）
        seen = set()
        for item in self.selected_song_ids:
            if not isinstance(item, str) or not SONG_ID_RE.match(item):
                raise ValueError(f"selected_song_ids 包含非法 song_id：{item!r}")
            if item in seen:
                raise ValueError(f"selected_song_ids 存在重复 ID：{item}")
            seen.add(item)
        if self.layout_id not in ("grid-wrap", "magazine-flow"):
            # R1b 支持 grid-wrap (legacy-fixed-2) 与 magazine-flow (auto/manual)
            raise ValueError(
                f"R1b 支持 grid-wrap 与 magazine-flow 两种布局；当前 layout_id={self.layout_id!r}。"
            )
        if self.layout_id == "grid-wrap" and self.page_policy.mode != "legacy-fixed-2":
            raise ValueError(
                "grid-wrap 仅支持 legacy-fixed-2 分页（保护金标准 16/16）；"
                "如需自动分页请切换到 magazine-flow。"
            )
        if self.layout_id == "magazine-flow" and self.page_policy.mode == "legacy-fixed-2":
            # magazine-flow 的意义就是 pages=auto；该 mode 仅给 grid-wrap 保留。
            raise ValueError(
                "magazine-flow 不使用 legacy-fixed-2；请选择 mode='auto' 或 'manual'。"
            )
        # optional_session_ref 仅引用关系，必须存在但不用作级联
        if self.optional_session_ref is not None and not isinstance(self.optional_session_ref, str):
            raise ValueError("optional_session_ref 必须为字符串或 None")

    # ── JSON 编解码（容忍未知字段向前兼容） ──

    def to_dict(self) -> dict:
        d = asdict(self)
        # song_source 与 page_policy 与 export_settings 已是 dict；强规范化
        d["song_source"] = self.song_source.to_dict()
        d["page_policy"] = {
            "mode": self.page_policy.mode,
            "min_pages": self.page_policy.min_pages,
            "max_pages": self.page_policy.max_pages,
            "manual_pages": list(self.page_policy.manual_pages),
        }
        d["export_settings"] = asdict(self.export_settings)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PosterDocument":
        """从 JSON dict 构造；容忍未知字段（向前兼容），拒绝丢失关键字段。"""
        if not isinstance(d, dict):
            raise ValueError("PosterDocument JSON 必须为对象")
        d = dict(d)
        # 必备标识字段
        for key in ("id", "name", "layout_id", "theme_id", "canvas_id"):
            if key not in d:
                raise ValueError(f"PosterDocument 缺少关键字段：{key}")
        # schema_version 缺失 → 视为 v1（最老兼容）
        schema_version = d.get("schema_version", 1)
        if not isinstance(schema_version, int):
            raise ValueError("schema_version 必须为整数")
        # sub 结构
        ss = SongSource.from_dict(d.pop("song_source", {}) or {})
        page_policy_raw = d.pop("page_policy", {}) or {}
        pp = PagePolicy(
            mode=page_policy_raw.get("mode", "legacy-fixed-2"),
            min_pages=page_policy_raw.get("min_pages"),
            max_pages=page_policy_raw.get("max_pages"),
            manual_pages=list(page_policy_raw.get("manual_pages", []) or []),
        )
        es_raw = d.pop("export_settings", {}) or {}
        es = ExportSettings(
            format=es_raw.get("format", "png"),
            jpeg_quality=es_raw.get("jpeg_quality", 92),
            single_page=bool(es_raw.get("single_page", False)),
            dpi=es_raw.get("dpi", 144),
        )
        # 主字段过滤：只保留 dataclass 声明的字段
        dataclass_keys = {f for f in cls.__dataclass_fields__ if f != "song_source" and f != "page_policy" and f != "export_settings"}
        kwargs = {k: d[k] for k in dataclass_keys if k in d}
        kwargs["schema_version"] = schema_version
        kwargs["song_source"] = ss
        kwargs["page_policy"] = pp
        kwargs["export_settings"] = es
        obj = cls(**kwargs)
        return obj


def resolve_artist_source(
    artists: List[str],
    active_songs: List[Any],
) -> List[str]:
    """解析 SOURCE_ARTIST → song_id 列表。

    大小写不敏感、空白裁剪；命中 song.artists 任一项即纳入。
    active_songs 只接受 status=active 的歌曲对象（at_status 保证）。
    返回按 active_songs 顺序排列的 song_id 列表。
    """
    if not artists:
        raise ValueError("SOURCE_ARTIST 必须提供非空 artists 列表")
    targets = {a.strip().lower() for a in artists if a and a.strip()}
    if not targets:
        raise ValueError("SOURCE_ARTIST artists 全部为空")
    selected: List[str] = []
    for song in active_songs:
        # 兼容 artists: list[str]
        if any(str(a).strip().lower() in targets for a in getattr(song, "artists", [])):
            selected.append(song.id)
    return selected


def resolve_all_active(active_songs: List[Any]) -> List[str]:
    """解析 SOURCE_ALL_ACTIVE → song_id 列表，按 active_songs 顺序。"""
    return [s.id for s in active_songs]
